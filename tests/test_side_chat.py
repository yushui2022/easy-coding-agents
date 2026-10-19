import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from eca.desktop_rpc import DesktopRPC
from test_runtime import FakeProvider, call


class SideChatTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root=Path(self.temp.name)
        (self.root/'eca.toml').write_text('[agent]\nproject_memory=false\nauto_compact=false\n')
        self.rpc=DesktopRPC(lambda _:None)
        await self.rpc.dispatch('initialize',{'protocol':1})
        await self.rpc.dispatch('project.open',{'path':str(self.root)})
        self.owner=self.rpc.runtime.agent.state['id']
        self.side=await self.rpc.dispatch('sidechat.open',{'session_id':self.owner,'selection':'Selected context'})
        self.entry=self.rpc.side_chats.entries[self.side['id']]
        self.args={'session_id':self.owner,'id':self.side['id']}

    async def asyncTearDown(self):
        await self.rpc.close()
        self.temp.cleanup()

    async def fake(self, responses):
        a=self.entry['agent']
        await a.provider.close()
        a.provider=FakeProvider(responses)

    async def test_tools_denied_context_separate_budget_and_persistence(self):
        await self.fake([call('write',{'path':'bad.txt','content':'no'}),{'role':'assistant','content':'Read only'}])
        await self.rpc.dispatch('sidechat.send',{**self.args,'prompt':'Explain'})
        await self.entry['task']
        self.assertFalse((self.root/'bad.txt').exists())
        a=self.entry['agent']
        self.assertIn('Denied',a.state['messages'][2]['content'])
        self.assertEqual({s['function']['name'] for s in a.tool_schemas()},{'read','glob','grep'})
        self.assertEqual(self.rpc.runtime.agent.state['messages'],[])
        self.assertEqual(self.rpc.runtime.agent.budget.status()['requests'],2)
        self.assertEqual(self.rpc.runtime.agent.ledger.summary(self.rpc.runtime.agent.state)['requests'],2)
        self.assertEqual(len(self.rpc.snapshot()['sessions']),1)
        for name in ('shell','lsp_apply','mcp_call','process_start','delegate','todo'):
            self.assertIn('Denied',await a.tools.execute(name,{}))
        await self.rpc.dispatch('project.close',{})
        await self.rpc.dispatch('project.open',{'path':str(self.root)})
        reopened=await self.rpc.dispatch('sidechat.open',{'session_id':self.owner})
        self.assertEqual(reopened['id'],self.side['id'])
        self.assertEqual(reopened['messages'][-1]['content'],'Read only')
        self.assertEqual(reopened['context']['selection'],'Selected context')

    async def test_cancel_is_independent_and_rejects_duplicate_stale_requests(self):
        class Wait:
            async def complete(self,*_): await asyncio.Event().wait()
            async def close(self): pass
        await self.entry['agent'].provider.close();self.entry['agent'].provider=Wait()
        await self.rpc.runtime.agent.provider.close();self.rpc.runtime.agent.provider=Wait()
        main=await self.rpc.dispatch('task.start',{'prompt':'main'})
        side=await self.rpc.dispatch('sidechat.send',{**self.args,'prompt':'side'})
        await asyncio.sleep(.02)
        with self.assertRaises(ValueError): await self.rpc.dispatch('sidechat.send',{**self.args,'prompt':'duplicate'})
        with self.assertRaises(ValueError): await self.rpc.dispatch('session.switch',{})
        with self.assertRaises(ValueError): await self.rpc.dispatch('sidechat.cancel',{**self.args,'run_id':'stale'})
        await self.rpc.dispatch('sidechat.cancel',{**self.args,'run_id':side['run_id']})
        await self.entry['task']
        self.assertTrue(self.rpc.runtime.busy)
        await self.rpc.dispatch('task.cancel',{'run_id':main['run_id']})
        await self.rpc.finishing
        self.assertFalse(self.rpc.side_chats.busy)

    async def test_read_project_and_protected_paths(self):
        (self.root/'a.txt').write_text('hello')
        a=self.entry['agent']
        self.assertIn('hello',await a.tools.execute('read',{'path':'a.txt'}))
        self.assertIn('Protected',await a.tools.execute('read',{'path':'.env'}))
        self.assertIn('outside',await a.tools.execute('read',{'path':'../outside'}))
        with self.assertRaises(ValueError):await self.rpc.dispatch('sidechat.snapshot',{'session_id':'wrong','id':self.side['id']})

    async def test_stream_delta_turn_reset_and_secret_redaction(self):
        a=self.entry['agent'];a.emit('turn',1);a.emit('text','你好')
        first=self.rpc.side_chats.snapshot(self.entry)
        a.emit('text','🌲')
        args={**self.args,'stream_run_id':first['run_id'],'stream_id':first['stream_id'],'stream_offset':first['stream_offset'],'message_count':first['message_total']}
        value=await self.rpc.dispatch('sidechat.snapshot',args)
        self.assertEqual(value['stream_delta'],'🌲');self.assertNotIn('messages',value)
        a.emit('turn',2);a.emit('text','不同的一轮内容')
        value=await self.rpc.dispatch('sidechat.snapshot',args)
        self.assertEqual(value['stream'],'不同的一轮内容')
        self.rpc.secrets.add('private-test-value')
        a.emit('text','private-test-value')
        self.assertNotIn('private-test-value',str(await self.rpc.dispatch('sidechat.snapshot',args)))
