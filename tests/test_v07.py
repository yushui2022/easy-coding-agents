import asyncio
import json
import sys
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace as NS

from eca.agent import Agent
from eca.config import Settings
from eca.responses import input_items, complete
from eca.workspaces import workspace
import test_runtime as fixtures
from test_runtime import FakeProvider, yes, no, call


class UpgradeTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.RuntimeTests.setUp
    tearDown = fixtures.RuntimeTests.tearDown

    def agent(self):
        self.settings.project_memory = False
        self.settings.auto_compact = False
        self.settings.permission = 'accept-edits'
        return Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None, FakeProvider([]))

    async def test_parallel_actual_overlap_isolation_merge_undo_and_conflict(self):
        (self.root/'a.py').write_text('uncommitted', encoding='utf-8')
        (self.root/'.env').write_text('SECRET=excluded', encoding='utf-8')
        entered, release = [], asyncio.Event()
        class Child(FakeProvider):
            def __init__(self, settings):
                super().__init__([call('write', {'path':'a.py', 'content': settings.root.name}),
                                  {'role':'assistant','content':'done'}])
                self.settings = settings
            async def complete(child, messages, tools, emit):
                if not child.contexts:
                    entered.append(child.settings.root)
                    if len(entered) == 2:
                        release.set()
                    await asyncio.wait_for(release.wait(), 3)
                    self.assertEqual((child.settings.root/'a.py').read_text(), 'uncommitted')
                    self.assertFalse((child.settings.root/'.env').exists())
                    self.assertNotIn('shell', [s['function']['name'] for s in tools])
                return await super().complete(messages, tools, emit)
        agent = self.agent()
        with patch('eca.agent.Provider', Child):
            results = json.loads(await agent.parallel([{'task':'one','mode':'code'}, {'task':'two','mode':'code'}]))
        self.assertEqual(len(entered), 2)
        self.assertEqual([x['status'] for x in results], ['idle','idle'])
        self.assertEqual((self.root/'a.py').read_text(), 'uncommitted')
        first, second = [r['session'] for r in results]
        await agent.merge(first, ['a.py'])
        self.assertEqual((self.root/'a.py').read_text(), first)
        with self.assertRaisesRegex(ValueError, 'conflict'):
            await agent.merge(second, ['a.py'])
        agent.changes.undo(agent.changes.list()[0]['id'])
        self.assertEqual((self.root/'a.py').read_text(), 'uncommitted')
        child_state = self.store.load(first)
        resumed = Agent(self.settings, self.store, child_state, yes, yes, lambda *_:None, FakeProvider([]), child=True)
        self.assertEqual(resumed.settings.root, workspace(self.store, child_state))
        self.assertIn('Denied', await resumed.tools.execute('shell', {'command':'echo unsafe'}))
        self.assertIn('Denied', await resumed.tools.execute('delegate_parallel', {'tasks':[{'task':'nested'}]}))
        await resumed.close()
        await agent.close()

    async def test_parallel_cancel_all_and_persist_states(self):
        started = asyncio.Event()
        class Slow(FakeProvider):
            def __init__(self, settings): super().__init__([])
            async def complete(self, *_):
                started.set()
                await asyncio.sleep(30)
        agent = self.agent()
        with patch('eca.agent.Provider', Slow):
            job = asyncio.create_task(agent.parallel([{'task':'one'}, {'task':'two'}]))
            await started.wait()
            job.cancel()
            with self.assertRaises(asyncio.CancelledError): await job
        self.assertEqual([self.store.load(i)['status'] for i in self.state['children']], ['interrupted','interrupted'])
        await agent.close()

    async def test_parallel_mode_limit_and_merge_preflight(self):
        agent = self.agent()
        self.settings.mode = 'plan'
        self.assertIn('Denied', await agent.parallel([{'task':'no','mode':'code'}]))
        self.assertNotIn('children', self.state)
        with self.assertRaises(ValueError): await agent.parallel([{'task':'x'}]*4)
        await agent.close()

    async def test_parallel_write_approvals_show_diff_and_serialize_prompts(self):
        agent = self.agent()
        self.settings.permission = 'ask'
        events, active, approvals = [], 0, 0
        agent.emit = lambda event, data: events.append((event,data))
        async def approve(message, detail):
            nonlocal active, approvals
            self.assertEqual(active, 0)
            self.assertEqual(events[-1], ('diff',detail))
            active += 1
            await asyncio.sleep(0.01)
            active -= 1
            approvals += 1
            return True
        agent.tools.approve = approve
        def factory(_):
            return FakeProvider([call('write', {'path':'new.py','content':'created'}), {'role':'assistant','content':'done'}])
        with patch('eca.agent.Provider', factory):
            result = json.loads(await agent.parallel([{'task':'a','mode':'code'}, {'task':'b','mode':'code'}]))
        self.assertEqual(approvals,2)
        self.assertEqual([r['status'] for r in result], ['idle','idle'])
        await agent.close()

    async def test_lsp_real_framing_utf16_and_no_apply_edit(self):
        script = self.root/'server.py'
        script.write_text('''import sys,json
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
 if m.get('method')=='exit': break
 if 'method' not in m: continue
 if 'id' not in m: continue
 if m['method']=='initialize': result={'capabilities':{}}
 elif m['method']=='shutdown': result=None
 else:
  send({'id':99,'method':'workspace/applyEdit','params':{'edit':{}}})
  result={'position':m['params'].get('position'),'method':m['method']}
 send({'id':m['id'],'result':result})
''', encoding='utf-8')
        (self.root/'code.py').write_text('x = 1', encoding='utf-8')
        self.settings.lsp_servers = {'py':dict(command=sys.executable, args=['-B',str(script)])}
        result = json.loads(await self.tools.lsp('py','definition','code.py',2,4))
        self.assertEqual(result['result']['position'], {'line':1,'character':4})
        await self.tools.close()
        self.tools.approve = no
        self.assertIn('Denied', await self.tools.lsp('py','symbols','code.py'))
        self.assertEqual((self.root/'code.py').read_text(), 'x = 1')

    def test_config_new_protocol_and_lsp(self):
        (self.root/'eca.toml').write_text('[agent]\napi_format="responses"\nreasoning_effort="low"\n[lsp_servers.py]\ncommand="pyright-langserver"\nargs=["--stdio"]\n', encoding='utf-8')
        settings = Settings.load(self.root)
        self.assertEqual(settings.api_format, 'responses')
        self.assertEqual(settings.reasoning_effort, 'low')
        self.assertIn('py',settings.lsp_servers)

    def test_snapshot_respects_git_ignore_and_dirty_bytes(self):
        import shutil
        import subprocess
        from eca.workspaces import source_files
        if not shutil.which('git'):
            self.skipTest('Git unavailable')
        subprocess.run(['git','init','-q',str(self.root)], check=True, capture_output=True)
        (self.root/'.gitignore').write_text('cache/\n.env\n', encoding='utf-8')
        (self.root/'cache').mkdir()
        (self.root/'cache'/'large.bin').write_bytes(b'ignored')
        (self.root/'source.py').write_text('staged', encoding='utf-8')
        subprocess.run(['git','add','source.py'], cwd=self.root, check=True, capture_output=True)
        (self.root/'source.py').write_text('dirty', encoding='utf-8')
        sources = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in source_files(self.tools)}
        self.assertEqual(sources['source.py'], b'dirty')
        self.assertNotIn('cache/large.bin',sources)

    async def test_responses_reasoning_tool_pairing_usage_and_incomplete(self):
        class Item(NS):
            def model_dump(self, **_): return vars(self)
        items = [Item(type='reasoning', id='r', encrypted_content='opaque', summary=[]),
                 Item(type='function_call', id='f', call_id='c', name='read', arguments='{"path":"a"}')]
        usage = Item(input_tokens=10, output_tokens=5, input_tokens_details={'cached_tokens':3})
        response = NS(status='completed', output=items, usage=usage)
        class Stream:
            closed = False
            def __aiter__(self): return self.events()
            async def events(self): yield NS(type='response.completed', response=response)
            async def close(self): self.closed = True
        stream = Stream()
        client = NS(responses=NS(create=AsyncMock(return_value=stream)))
        message, u = await complete(client, self.settings, [{'role':'user','content':'hi'}], [], lambda *_:None, lambda _:None)
        self.assertTrue(stream.closed)
        self.assertEqual(u['prompt_tokens_details']['cached_tokens'],3)
        converted = input_items([message, {'role':'tool','tool_call_id':'c','content':'a'}])
        self.assertEqual(converted[0]['encrypted_content'], 'opaque')
        self.assertEqual(converted[-1]['call_id'], 'c')
        self.assertFalse(client.responses.create.call_args.kwargs['store'])
        response.status = 'incomplete'
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            await complete(client, self.settings, [], [], lambda *_:None, lambda _:None)

    async def test_responses_sdk_http_stream_and_ledger(self):
        import httpx
        from openai import AsyncOpenAI
        from eca.provider import Provider
        agent = self.agent()
        self.settings.api_format = 'responses'
        self.settings.api_key = 'fixture'
        self.settings.reasoning_effort = 'low'
        self.settings.pricing = {self.settings.model:dict(input='2', output='8', cache_read='1', currency='USD')}
        seen = []
        def handler(request):
            seen.append(json.loads(request.content))
            self.assertEqual(request.url.path, '/v1/responses')
            response = dict(id='resp_fixture', object='response', created_at=0, status='completed',
                model=self.settings.model, output=[dict(type='message', id='msg_fixture', role='assistant',
                status='completed', content=[dict(type='output_text', text='verified', annotations=[])])],
                usage=dict(input_tokens=10, output_tokens=5, total_tokens=15,
                           input_tokens_details=dict(cached_tokens=3), output_tokens_details=dict(reasoning_tokens=2)))
            body = 'data: '+json.dumps(dict(type='response.output_text.delta', delta='verified', item_id='msg_fixture', output_index=0, content_index=0))+'\n\n'
            body += 'data: '+json.dumps(dict(type='response.completed', response=response))+'\n\n'
            return httpx.Response(200, headers={'content-type':'text/event-stream'}, text=body)
        provider = Provider(self.settings)
        provider.client = AsyncOpenAI(api_key='fixture', base_url='http://fixture/v1',
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_retries=0)
        agent.provider = provider
        try:
            await agent.run('test response')
            self.assertEqual(self.state['messages'][-1]['content'], 'verified')
            self.assertEqual(seen[0]['reasoning'], {'effort':'low'})
            self.assertEqual(agent.ledger.summary(self.state)['priced_subtotals'], {'USD':'0.000057'})
        finally:
            await agent.close()

    async def test_lsp_headless_approval_is_separate_and_scoped(self):
        from eca.cli import App, parser
        app = App.__new__(App)
        app.args = parser().parse_args(['-p','test','--allow-shell','--allow-lsp','py'])
        self.assertTrue(await app.approve('Start language server?', json.dumps({'server':'py'})))
        self.assertFalse(await app.approve('Start language server?', json.dumps({'server':'other'})))
