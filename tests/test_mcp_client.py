import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch

from eca.config import Settings
from eca.mcp_client import MCPTools
from eca.tools import Tools
from test_runtime import yes, no

CATALOG=[{'name':'echo','description':'fixture','inputSchema':{'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False}}]
INIT={'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'fixture','version':'1'}}


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'Install the MCP extra to run transport integration tests')
class MCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        base=Path(os.environ.get('ECA_TEST_TMP',tempfile.gettempdir()))
        base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base)
        self.root=Path(self.tmp.name).resolve()
        self.settings=Settings(self.root)
        script=self.root/'fixture.py'
        script.write_text('''import sys,json,time,os
from pathlib import Path
for line in sys.stdin:
    m=json.loads(line)
    if 'id' not in m: continue
    method=m['method']
    if method=='initialize': result=INIT
    elif method=='tools/list': result={'tools':CATALOG}
    elif method=='tools/call':
        Path('called').write_text('yes')
        text=m['params']['arguments']['text']
        if text=='slow': time.sleep(20)
        result={'content':[{'type':'text','text':os.environ.get('FIXTURE_SECRET',text)}],'isError':text=='error'}
    else: result={}
    print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
'''.replace('INIT',repr(INIT)).replace('CATALOG',repr(CATALOG)),encoding='utf-8')
        self.settings.mcp_servers={'fixture':{'command':sys.executable,'args':['-B',str(script)],'timeout':10}}

    def tearDown(self):
        self.tmp.cleanup()

    async def test_real_stdio_list_call_schema_error_and_secret_redaction(self):
        client=MCPTools(self.settings,yes)
        tools=json.loads(await client.invoke('fixture'))
        self.assertEqual(tools['tools'][0]['name'],'echo')
        invalid=await client.invoke('fixture','echo',{'wrong':'value'})
        self.assertIn('failed',invalid)
        self.assertFalse((self.root/'called').exists())
        result=json.loads(await client.invoke('fixture','echo',{'text':'hello'}))
        self.assertEqual(result['content'][0]['text'],'hello')
        self.assertTrue(json.loads(await client.invoke('fixture','echo',{'text':'error'}))['isError'])
        self.settings.mcp_servers['fixture']['env']={'FIXTURE_SECRET':'MCP_TEST_TOKEN'}
        with patch.dict(os.environ,{'MCP_TEST_TOKEN':'test-private-token'}):
            result=await client.invoke('fixture','echo',{'text':'secret'})
        self.assertNotIn('test-private-token',result)
        self.assertIn('[redacted]',result)

    async def test_persistent_transport_reused_and_closed(self):
        client=MCPTools(self.settings,yes,persistent=True)
        try:
            first=json.loads(await client.invoke('fixture'))
            worker=client.workers['fixture'][1]
            result=json.loads(await client.invoke('fixture','echo',{'text':'kept alive'}))
            self.assertIs(client.workers['fixture'][1],worker)
            self.assertEqual(result['content'][0]['text'],'kept alive')
            self.assertEqual(first['tools'][0]['name'],'echo')
        finally:
            await client.close()
        self.assertTrue(worker.done())
        self.assertEqual(client.workers,{})

    async def test_dead_connection_is_reported_and_next_explicit_call_reconnects(self):
        client=MCPTools(self.settings,yes,persistent=True)
        try:
            await client.invoke('fixture')
            self.assertTrue(client.connected('fixture'))
            worker=client.workers['fixture'][1]
            worker.cancel()
            await asyncio.gather(worker,return_exceptions=True)
            self.assertFalse(client.connected('fixture'))
            result=json.loads(await client.invoke('fixture','echo',{'text':'new explicit operation'}))
            self.assertEqual(result['content'][0]['text'],'new explicit operation')
            self.assertIsNot(worker,client.workers['fixture'][1])
        finally:
            await client.close()

    async def test_cancel_waiting_request_does_not_disconnect_active_operation(self):
        client=MCPTools(self.settings,yes,persistent=True)
        started, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
        # Exercise the real lock/dispatch/owner cancellation path, without making
        # it depend on SDK import time, process startup or a one-second file poll.
        # Actual stdio/HTTP transport behavior is covered by the other tests.
        async def owner(cfg, values, tool, arguments, queue=None):
            client.ready.add(asyncio.current_task())
            while True:
                operation, args, future = await queue.get()
                if operation == 'echo':
                    started.set()
                    await release.wait()
                if not future.done():
                    future.set_result({'content':[{'type':'text','text':args.get('text','ready')}]})
        async def queued_request():
            waiting.set()
            return await client.invoke('fixture')
        first=second=None
        try:
            with patch.object(client, '_operate', side_effect=owner):
                await client.invoke('fixture')
                worker = client.workers['fixture'][1]
                self.assertTrue(client.connected('fixture'))
                first=asyncio.create_task(client.invoke('fixture','echo',{'text':'slow'}))
                await asyncio.wait_for(started.wait(), 5)
                second=asyncio.create_task(queued_request())
                await asyncio.wait_for(waiting.wait(), 5)
                self.assertFalse(second.done())
                second.cancel()
                with self.assertRaises(asyncio.CancelledError): await second
                self.assertTrue(client.connected('fixture'))
                self.assertIs(client.workers['fixture'][1], worker)
                self.assertFalse(first.done())
                release.set()
                self.assertEqual(json.loads(await first)['content'][0]['text'], 'slow')
        finally:
            if first:
                first.cancel()
                await asyncio.gather(first,return_exceptions=True)
            if second:
                await asyncio.gather(second,return_exceptions=True)
            await client.close()

    async def test_resource_prompt_operations_with_real_stdio(self):
        script=self.root/'fixture.py'
        text=script.read_text('utf-8').replace("    else: result={}", """    elif method=='resources/list': result={'resources':[{'uri':'fixture://doc','name':'doc'}]}
    elif method=='resources/templates/list': result={'resourceTemplates':[{'uriTemplate':'fixture://{name}','name':'template'}]}
    elif method=='resources/read': result={'contents':[{'uri':m['params']['uri'],'text':'resource text'}]}
    elif method=='prompts/list': result={'prompts':[{'name':'review'}]}
    elif method=='prompts/get': result={'messages':[{'role':'user','content':{'type':'text','text':'untrusted prompt'}}]}
    else: result={}""")
        script.write_text(text,encoding='utf-8')
        client=MCPTools(self.settings,yes,persistent=True)
        try:
            self.assertEqual(json.loads(await client.invoke('fixture','@resources'))['resources'][0]['name'],'doc')
            self.assertEqual(json.loads(await client.invoke('fixture','@read',{'uri':'fixture://doc'}))['contents'][0]['text'],'resource text')
            self.assertEqual(json.loads(await client.invoke('fixture','@templates'))['resourceTemplates'][0]['name'],'template')
            self.assertEqual(json.loads(await client.invoke('fixture','@prompts'))['prompts'][0]['name'],'review')
            result=json.loads(await client.invoke('fixture','@prompt',{'name':'review'}))
            self.assertIn('untrusted',result['notice'])
        finally:
            await client.close()

    async def test_denial_and_plan_mode_do_not_connect(self):
        client=MCPTools(self.settings,no)
        with patch.object(client,'_operate',new_callable=AsyncMock) as operation:
            self.assertIn('Denied',await client.invoke('fixture'))
            operation.assert_not_awaited()
        self.settings.mode='plan'
        tools=Tools(self.settings,{},yes,yes,lambda *_:None)
        with patch.object(MCPTools,'invoke',new_callable=AsyncMock) as invoke:
            self.assertIn('Denied',await tools.execute('mcp_call',{'server':'fixture','tool':'echo','arguments':{}}))
            invoke.assert_not_awaited()

    async def test_stdio_timeout_does_not_replay(self):
        self.settings.mcp_servers['fixture']['timeout']=2
        result=await MCPTools(self.settings,yes).invoke('fixture','echo',{'text':'slow'})
        self.assertIn('failed',result)
        self.assertIn('No automatic retry',result)

    async def test_stdio_cancellation_propagates(self):
        task=asyncio.create_task(MCPTools(self.settings,yes).invoke('fixture','echo',{'text':'slow'}))
        for _ in range(100):
            if (self.root/'called').exists(): break
            await asyncio.sleep(.05)
        self.assertTrue((self.root/'called').exists())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task

    async def test_real_streamable_http(self):
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                message=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append(message['method'])
                if 'id' not in message:
                    self.send_response(202); self.end_headers(); return
                if message['method']=='initialize': result=INIT
                elif message['method']=='tools/list': result={'tools':CATALOG}
                else: result={'content':[{'type':'text','text':message['params']['arguments']['text']}],'isError':False}
                body=json.dumps({'jsonrpc':'2.0','id':message['id'],'result':result}).encode()
                self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        self.settings.mcp_servers={'fixture':{'transport':'http','url':f'http://127.0.0.1:{server.server_port}/mcp'}}
        try:
            result=json.loads(await MCPTools(self.settings,yes).invoke('fixture','echo',{'text':'http works'}))
            self.assertEqual(result['content'][0]['text'],'http works')
            self.assertEqual(received.count('tools/call'),1)
        finally:
            await asyncio.to_thread(server.shutdown)
            server.server_close(); thread.join(timeout=2)
