import asyncio
import json
import os
import sys
import unittest
from unittest.mock import patch

from eca.agent import Agent
from eca.config import Settings
from eca.responses import input_items
from eca.workspaces import workspace
import test_runtime as fixtures
from test_runtime import FakeProvider, yes


LSP_FIXTURE = '''import sys,json
from pathlib import Path
mode=sys.argv[1]
p=Path('starts');p.write_text(str(int(p.read_text())+1) if p.exists() else '1')
def send(m):
 b=json.dumps(dict(jsonrpc='2.0',**m)).encode();sys.stdout.buffer.write(('Content-Length: %s\\r\\n\\r\\n'%len(b)).encode()+b);sys.stdout.buffer.flush()
while True:
 h={}
 while True:
  line=sys.stdin.buffer.readline()
  if not line: sys.exit()
  if line==b'\\r\\n': break
  k,v=line.decode().split(':',1);h[k.lower()]=v.strip()
 m=json.loads(sys.stdin.buffer.read(int(h['content-length'])))
 method=m.get('method')
 if method=='exit': break
 if method in ['textDocument/didOpen','textDocument/didChange']:
  doc=m['params']['textDocument'];v=doc['version']
  text=doc.get('text') or m['params'].get('contentChanges',[{}])[0].get('text','')
  if mode=='silent': continue
  send({'method':'textDocument/publishDiagnostics','params':{'uri':doc['uri'],'version':v-1,'diagnostics':[{'message':'stale'}]}})
  if mode=='stale': continue
  payload={'uri':doc['uri'],'diagnostics':[{'message':text}]}
  if mode!='unversioned': payload['version']=v
  send({'method':'textDocument/publishDiagnostics','params':payload})
  continue
 if 'id' not in m or method is None: continue
 if method=='initialize': result={'capabilities':{'diagnosticProvider':{}} if mode=='pull' else {}}
 elif method=='textDocument/diagnostic': result={'kind':'full','items':[]}
 elif method=='shutdown': result=None
 else: result={'method':method}
 send({'id':m['id'],'result':result})
'''


class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.RuntimeTests.setUp
    tearDown = fixtures.RuntimeTests.tearDown

    async def asyncTearDown(self):
        await self.tools.close()

    def lsp(self, mode='push'):
        script = self.root/'fixture.py'
        script.write_text(LSP_FIXTURE, encoding='utf-8')
        self.settings.lsp_servers = {'fixture':dict(command=sys.executable, args=['-B',str(script),mode],
                                                  timeout=8, diagnostic_timeout=1)}
        (self.root/'a.py').write_text('first', encoding='utf-8')

    async def test_lsp_reuses_process_syncs_edits_and_rejects_stale_diagnostics(self):
        self.lsp()
        first = json.loads(await self.tools.lsp('fixture','diagnostics','a.py'))['result']
        self.assertEqual(first['items'][0]['message'],'first')
        self.assertEqual(first['freshness'],'versioned')
        client = self.tools.language_servers.clients['fixture']
        (self.root/'a.py').write_text('second', encoding='utf-8')
        second = json.loads(await self.tools.lsp('fixture','diagnostics','a.py'))['result']
        self.assertEqual(second['items'][0]['message'],'second')
        self.assertEqual((self.root/'starts').read_text(),'1')
        self.assertTrue(client.alive)
        await self.tools.close()
        self.assertFalse(client.alive)
        self.assertEqual(self.tools.language_servers.status(), {'fixture':'disconnected'})

    async def test_lsp_missing_diagnostics_is_pending_not_clean(self):
        self.lsp('stale')
        result = json.loads(await self.tools.lsp('fixture','diagnostics','a.py'))['result']
        self.assertEqual(result['status'],'pending')
        self.assertNotIn('items',result)

    async def test_lsp_pull_and_unversioned_are_distinguished(self):
        self.lsp('pull')
        result = json.loads(await self.tools.lsp('fixture','diagnostics','a.py'))['result']
        self.assertEqual(result,dict(status='reported',source='pull',items=[],truncated=False))
        self.settings.lsp_servers['fixture']['args'][-1] = 'unversioned'
        result = json.loads(await self.tools.lsp('fixture','diagnostics','a.py'))['result']
        self.assertEqual(result['freshness'],'unversioned')
        self.assertEqual((self.root/'starts').read_text(),'2')

    async def test_lsp_cancellation_closes_process_and_can_restart(self):
        self.lsp('silent')
        self.settings.lsp_servers['fixture']['diagnostic_timeout'] = 5
        await self.tools.lsp('fixture','hover','a.py')
        manager = self.tools.language_servers
        client = manager.clients['fixture']
        job = asyncio.create_task(self.tools.lsp('fixture','diagnostics','a.py'))
        await asyncio.sleep(0.05)
        job.cancel()
        with self.assertRaises(asyncio.CancelledError): await job
        self.assertFalse(client.alive)
        self.assertFalse(manager.clients)
        await self.tools.lsp('fixture','hover','a.py')
        self.assertEqual((self.root/'starts').read_text(),'2')

    def agent(self):
        self.settings.project_memory = self.settings.auto_compact = False
        self.settings.permission = 'accept-edits'
        return Agent(self.settings,self.store,self.state,yes,yes,lambda *_:None,FakeProvider([]))

    async def test_queue_bound_and_initialization_failure_do_not_cancel_siblings(self):
        agent = self.agent()
        self.settings.subagent_concurrency = 1
        active, peak, created = 0, 0, 0
        class Child(FakeProvider):
            async def complete(child, *_):
                nonlocal active, peak
                active += 1
                peak = max(peak,active)
                await asyncio.sleep(0.02)
                active -= 1
                return {'role':'assistant','content':'done'},{}
        def factory(_):
            nonlocal created
            created += 1
            if created == 2:
                raise ValueError('fixture failure')
            return Child([])
        with patch('eca.agent.Provider',factory):
            result = json.loads(await agent.parallel([{'task':str(i)} for i in range(3)]))
        self.assertEqual(peak,1)
        self.assertEqual([r['status'] for r in result],['idle','error','idle'])
        self.assertIn('ValueError',result[1]['stop_reason'])
        await agent.close()

    async def test_cancel_queued_tasks_and_peek_does_not_repair_running(self):
        agent = self.agent()
        self.settings.subagent_concurrency = 1
        started = asyncio.Event()
        class Child(FakeProvider):
            async def complete(child, *_):
                started.set()
                await asyncio.sleep(30)
        with patch('eca.agent.Provider',lambda _:Child([])):
            job = asyncio.create_task(agent.parallel([{'task':str(i)} for i in range(3)]))
            await started.wait()
            ids = self.state['children']
            self.assertEqual([self.store.peek(i)['status'] for i in ids],['running','queued','queued'])
            with self.assertRaisesRegex(ValueError,'completed'):
                await agent.merge(ids[0],['a.py'])
            self.assertEqual(self.store.peek(ids[0])['status'],'running')
            job.cancel()
            with self.assertRaises(asyncio.CancelledError): await job
        self.assertEqual([self.store.peek(i)['status'] for i in ids],['interrupted']*3)
        await agent.close()

    async def test_preparation_failure_preserves_failed_child_identity(self):
        agent = self.agent()
        (self.root/'a.py').write_text('source')
        original = type(self.root).write_bytes
        def fail(path, data):
            if 'workspaces' in path.parts:
                raise OSError('fixture disk failure')
            return original(path,data)
        with patch.object(type(self.root),'write_bytes',fail):
            with self.assertRaises(OSError): await agent.parallel([{'task':'one'},{'task':'two'}])
        self.assertEqual([self.store.peek(i)['status'] for i in self.state['children']],['error','error'])
        self.assertEqual((self.root/'a.py').read_text(),'source')
        await agent.close()

    def profiles(self):
        (self.root/'eca.toml').write_text('''[agent]
model_profile="fast"
[model_profiles.fast]
model="fixture-fast"
base_url="http://localhost:9001/v1"
api_format="openai"
api_key_env="ECA_TEST_PROFILE_ONE"
reasoning_effort="low"
stream_usage=false
[model_profiles.deep]
model="fixture-deep"
base_url="http://localhost:9002/v1"
api_format="responses"
api_key_env="ECA_TEST_PROFILE_TWO"
''', encoding='utf-8')

    def test_profiles_isolate_credentials_and_optional_settings(self):
        self.profiles()
        with patch.dict(os.environ,{'ECA_TEST_PROFILE_ONE':'first-secret','ECA_TEST_PROFILE_TWO':'second-secret'}):
            fast = Settings.load(self.root)
            deep = fast.select_profile('deep')
        self.assertEqual((fast.model_profile,fast.api_key,fast.stream_usage),('fast','first-secret',False))
        self.assertEqual((deep.api_format,deep.api_key,deep.reasoning_effort,deep.stream_usage),('responses','second-secret','',True))
        self.assertNotIn('secret',repr(deep))
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(fast.select_profile('deep').api_key,'')
        self.assertEqual(Settings.load(self.root,model='explicit').model_profile,'')

    async def test_cli_profile_switch_resume_and_offline_review_without_credentials(self):
        from eca.cli import App, parser
        from eca.store import Store
        self.profiles()
        self.store.close()
        app = None
        try:
            with patch.dict(os.environ,{'ECA_TEST_PROFILE_ONE':'first-secret','ECA_TEST_PROFILE_TWO':'second-secret'}):
                args = parser().parse_args(['--cwd',str(self.root),'-p','fixture'])
                app = App(Settings.load(self.root),args)
                await app.command('/model @deep')
                await app.command('/new')
                ident = app.state['id']
                self.assertEqual(app.state['model_profile'], 'deep')
                self.assertEqual(app.agent.settings.api_key,'second-secret')
                self.assertNotIn('second-secret',json.dumps(app.store.peek(ident)))
                await app.close()
                app = None
                args = parser().parse_args(['--cwd',str(self.root),'--resume',ident,'-p','fixture'])
                app = App(Settings.load(self.root),args)
                self.assertEqual(app.settings.model_profile,'deep')
                self.assertEqual(app.settings.api_format,'responses')
                await app.close()
                app = None
            args = parser().parse_args(['--cwd',str(self.root),'--resume',ident,'--changes'])
            app = App(Settings(self.root),args)
            self.assertEqual(app.state['model_profile'],'deep')
            self.assertEqual(app.settings.api_key,'')
        finally:
            if app:
                await app.close()
            self.store = Store(self.root)

    def test_responses_foreign_reasoning_is_not_sent_to_another_model(self):
        message = dict(role='assistant',content=None,response_scope='old',
                       response_items=[dict(type='reasoning',encrypted_content='opaque')],
                       tool_calls=[dict(id='tool1',function=dict(name='read',arguments='{}'))])
        converted = input_items([message],scope='new')
        self.assertEqual(converted,[dict(type='function_call',call_id='tool1',name='read',arguments='{}')])

    async def test_compaction_excludes_opaque_replay_data_but_preserves_archive(self):
        agent = self.agent()
        agent.provider = FakeProvider([{'role':'assistant','content':'A useful summary.'}])
        self.state['messages'] = [dict(role='user',content='task'),dict(role='assistant',content='answer',
            response_scope='fixture', response_items=[dict(type='reasoning', encrypted_content='opaque_payload')])]
        await agent.compact()
        self.assertNotIn('opaque_payload',json.dumps(agent.provider.contexts))
        self.assertIn('opaque_payload',json.dumps(self.state['messages']))
        await agent.close()
