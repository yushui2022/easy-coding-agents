import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from eca.agent import Agent
from eca.config import Settings
from eca.provider import Provider
from eca.store import Store
from eca.usage import UsageLedger, normalize, calculate
from test_runtime import FakeProvider, call, yes


class ExtensionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        base=Path(os.environ.get('ECA_TEST_TMP',tempfile.gettempdir()))
        base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base)
        self.root=Path(self.tmp.name).resolve()
        self.store=Store(self.root)
        self.settings=Settings(self.root,permission='accept-edits',project_memory=False,auto_compact=False)
        self.state=self.store.create()
        self.agent=Agent(self.settings,self.store,self.state,yes,yes,lambda *_:None,FakeProvider([]))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_decimal_cache_normalization_and_reasoning_not_double_counted(self):
        raw={'prompt_tokens':1000,'completion_tokens':200,'prompt_tokens_details':{'cached_tokens':400},
             'completion_tokens_details':{'reasoning_tokens':100}}
        tokens=normalize(raw,'openai')
        self.assertEqual(tokens,dict(input=600,cache_read=400,output=200))
        self.assertEqual(calculate(tokens,dict(input='2',cache_read='0.5',output='8')), '0.0030')
        self.assertIsNone(normalize({'prompt_tokens':True,'completion_tokens':2},'openai'))
        self.assertIsNone(normalize({'prompt_tokens':10,'completion_tokens':2,'prompt_cache_hit_tokens':11},'openai'))

    def test_anthropic_cache_creation_is_additive_and_missing_price_unknown(self):
        tokens=normalize(dict(input_tokens=10,output_tokens=5,cache_read_input_tokens=20,
                             cache_creation_input_tokens=30,cache_creation={'ephemeral_5m_input_tokens':10,'ephemeral_1h_input_tokens':20}),'anthropic')
        self.assertEqual(sum(tokens.values()),65)
        self.assertIsNone(calculate(tokens,{'input':'1','output':'2'}))
        self.assertIsNone(normalize({'input_tokens':12},'anthropic'))

    def test_missing_cache_split_and_legacy_history_are_explicit(self):
        self.settings.pricing={self.settings.model:{'currency':'USD','input':'2','output':'8','cache_read':'0.2'}}
        self.agent.ledger.begin('missing-cache',self.state,self.settings,'task')
        self.agent.ledger.finish('missing-cache',{'prompt_tokens':1000,'completion_tokens':20},'complete')
        report=self.agent.ledger.summary(self.state)
        self.assertEqual(report['incomplete_cost_requests'],1)
        self.assertEqual(report['priced_subtotals'],{})
        legacy=self.store.create()
        legacy['messages']=[{'role':'user','content':'interrupted before answer'}]
        old=Agent(self.settings,self.store,legacy,yes,yes,lambda *_:None,FakeProvider([]))
        self.assertTrue(old.ledger.summary(legacy)['historical_usage_untracked'])

    async def test_mcp_headless_approval_is_server_scoped(self):
        from eca.cli import App, parser
        app=App.__new__(App)
        app.args=parser().parse_args(['-p','fixture','--allow-shell','--allow-mcp','trusted'])
        self.assertTrue(await app.approve('Run MCP operation?',json.dumps({'server':'trusted'})))
        self.assertFalse(await app.approve('Run MCP operation?',json.dumps({'server':'other'})))

    def test_price_snapshot_persistence_and_unknown_requests(self):
        self.settings.pricing={self.settings.model:{'currency':'USD','input':'2','output':'8'}}
        ledger=self.agent.ledger
        ledger.begin('one',self.state,self.settings,'task')
        self.settings.pricing[self.settings.model]['input']='900'
        ledger.finish('one',{'prompt_tokens':1000,'completion_tokens':200},'complete')
        ledger.begin('two',self.state,self.settings,'compact')
        self.store.save(self.state)
        self.store.close(); self.store=Store(self.root)
        report=UsageLedger(self.store).summary(self.store.load(self.state['id']))
        self.assertEqual(report['priced_subtotals'],{'USD':'0.0036'})
        self.assertEqual(report['incomplete_usage_requests'],1)
        self.assertEqual(report['requests'],2)

    async def test_retries_and_cancelled_attempts_are_durable(self):
        provider=Provider(self.settings)
        provider._complete=AsyncMock(side_effect=[httpx.ConnectError('offline'),({'role':'assistant','content':'ok'},{'prompt_tokens':10,'completion_tokens':2})])
        self.agent.provider=provider
        with patch('eca.provider.asyncio.sleep',new_callable=AsyncMock):
            await self.agent.run('hello')
        report=self.agent.ledger.summary(self.state)
        self.assertEqual(report['requests'],2)
        self.assertEqual(report['incomplete_usage_requests'],1)
        provider._complete=AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await self.agent.run('cancel')
        self.assertEqual(self.agent.ledger.summary(self.state)['requests'],3)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM usage_requests WHERE status='cancelled'").fetchone()[0],1)

    async def test_compaction_accounted_separately(self):
        self.state['messages']=[{'role':'user','content':'old task'}]
        self.agent.provider=FakeProvider([{'role':'assistant','content':'summary'}])
        await self.agent.compact()
        self.assertEqual(self.store.db.execute('SELECT purpose FROM usage_requests').fetchone()[0],'compact')

    async def test_delegate_is_independent_bounded_and_read_only_by_default(self):
        child_provider=FakeProvider([call('write',{'path':'forbidden','content':'no'}),{'role':'assistant','content':'read only'}])
        self.settings.subagent_max_calls=1
        self.state['messages']=[{'role':'user','content':'private parent context'}]
        with patch('eca.agent.Provider',return_value=child_provider):
            report=json.loads(await self.agent.delegate('Inspect files'))
        self.assertFalse((self.root/'forbidden').exists())
        self.assertEqual(report['status'],'idle')
        child=self.store.load(report['session'])
        self.assertEqual(child['parent_id'],self.state['id'])
        self.assertNotIn('private parent context',json.dumps(child_provider.contexts))
        self.assertNotIn('delegate',[s['function']['name'] for s in child_provider.contexts[0][1]])
        self.assertIn('limit reached',await self.agent.delegate('again'))
        self.assertEqual(self.agent.ledger.summary(self.state)['requests'],2)

    async def test_code_child_snapshots_and_parent_permission_ceiling(self):
        self.settings.mode='plan'
        self.assertIn('Denied',await self.agent.delegate('write','code'))
        self.settings.mode='code'
        child_provider=FakeProvider([call('write',{'path':'child.txt','content':'child'}),{'role':'assistant','content':'done'}])
        with patch('eca.agent.Provider',return_value=child_provider):
            report=json.loads(await self.agent.delegate('write file','code'))
        self.assertEqual((self.root/'child.txt').read_text(),'child')
        child=self.store.load(report['session'])
        from eca.changes import Changes
        changes=Changes(self.store,child['id'],self.agent.tools.path)
        changes.undo(changes.list()[0]['id'])
        self.assertFalse((self.root/'child.txt').exists())

    async def test_child_timeout_and_parent_cancellation_cleanup(self):
        entered=asyncio.Event()
        class Slow(FakeProvider):
            async def complete(self,*args):
                entered.set()
                await asyncio.Future()
        self.settings.subagent_timeout=1
        with patch('eca.agent.Provider',return_value=Slow([])):
            result=json.loads(await self.agent.delegate('slow'))
        self.assertEqual(result['status'],'timeout')
        with patch('eca.agent.Provider',return_value=Slow([])):
            entered.clear()
            task=asyncio.create_task(self.agent.delegate('cancel'))
            await entered.wait(); task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        child=self.store.load(self.state['children'][-1])
        self.assertEqual(child['status'],'interrupted')

    def test_config_rejects_bad_pricing_and_mcp_credentials(self):
        for rates in [{'currency':'USD','input':-1},{'currency':'USD','input':'NaN'},{'input':'1'}]:
            self.settings.pricing={'m':rates}
            with self.assertRaises(ValueError): self.settings.validate()
        self.settings.pricing={}
        self.settings.mcp_servers={'remote':{'transport':'http','url':'https://example.com/mcp?token=secret'}}
        with self.assertRaises(ValueError): self.settings.validate()

    async def test_usage_cli_survives_broken_config(self):
        from eca.cli import async_main, parser
        self.agent.ledger.begin('pending',self.state,self.settings,'task')
        self.store.save(self.state)
        self.store.close()
        (self.root/'eca.toml').write_text('broken = [')
        try:
            with patch('builtins.print') as printed:
                self.assertEqual(await async_main(parser().parse_args(['--cwd',str(self.root),'--usage','--json'])),0)
            self.assertEqual(json.loads(printed.call_args.args[0])['requests'],1)
        finally:
            self.store=Store(self.root)
