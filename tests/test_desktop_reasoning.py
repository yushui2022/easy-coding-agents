import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
import httpx
from openai import AsyncOpenAI
from eca.config import Settings
from eca.desktop_rpc import DesktopRPC
from eca.provider import Provider
from eca import reasoning


class DesktopReasoningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.temp.name)
        (self.root/'eca.toml').write_text('[agent]\nproject_memory=false\nauto_compact=false\n')
        self.rpc = DesktopRPC(lambda _: None)
        await self.rpc.dispatch('initialize', {'protocol': 1})
        self.model = dict(model='deepseek-flash', base_url='http://localhost:1234/v1',
                          api_format='openai', api_key='local-secret', thinking_mode='fast', reasoning_effort='')
        await self.rpc.dispatch('project.open', {'path': str(self.root), 'model': self.model})
        self.owner = self.rpc.runtime.agent.state['id']

    async def asyncTearDown(self):
        await self.rpc.close()
        self.temp.cleanup()

    async def test_independent_effort_defaults_and_restore(self):
        parent = self.rpc.runtime.agent
        budget, tools, permission = parent.budget, parent.tools, parent.settings.permission
        args = {'session_id': self.owner}
        await self.rpc.dispatch('model.reasoning', {**args, 'effort': 'max'})
        side = await self.rpc.dispatch('sidechat.open', {**args, 'connection_id': 'saved-a'})
        sideargs = {**args, 'id': side['id']}
        await self.rpc.dispatch('sidechat.reasoning', {**sideargs, 'effort': 'low'})
        self.assertEqual(parent.settings.reasoning_effort, 'max')
        self.assertEqual(self.rpc.side_chats.entries[side['id']]['agent'].settings.reasoning_effort, 'low')
        self.assertIs(parent.budget, budget)
        self.assertIs(parent.tools, tools)
        self.assertEqual(parent.settings.permission, permission)
        await self.rpc.dispatch('project.close', {})
        await self.rpc.dispatch('project.open', {'path': str(self.root), 'model': self.model})
        self.assertEqual(self.rpc.runtime.agent.settings.reasoning_effort, 'max')
        reopened = await self.rpc.dispatch('sidechat.open', args)
        self.assertEqual(reopened['reasoning']['value'], 'low')
        value = await self.rpc.dispatch('model.reasoning', {**args, 'effort': 'default'})
        self.assertEqual(value['settings']['reasoning']['value'], 'default')
        self.assertEqual(self.rpc.runtime.agent.settings.thinking_mode, 'default')
        self.assertNotIn('local-secret', json.dumps(self.rpc.runtime.agent.state))
        # Identity includes protocol and endpoint, not just a model label.
        await self.rpc.dispatch('model.select', {'model': {**self.model, 'base_url': 'http://localhost:5678/v1'}})
        self.assertEqual(self.rpc.snapshot()['settings']['reasoning']['value'], 'none')
        unchanged = await self.rpc.dispatch('sidechat.snapshot', {**args, 'id': reopened['id']})
        self.assertEqual(unchanged['reasoning']['value'], 'low')
        self.assertEqual(unchanged['model'], 'deepseek-flash')

    async def test_stale_invalid_busy_and_model_switch(self):
        args = {'session_id': self.owner}
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('model.reasoning', {'session_id': 'stale', 'effort': 'high'})
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('model.reasoning', {**args, 'effort': 'ultra'})
        self.assertEqual(self.rpc.runtime.agent.settings.thinking_mode, 'fast')
        class Wait:
            async def complete(self, *_): await asyncio.Event().wait()
            async def close(self): pass
        await self.rpc.runtime.agent.provider.close()
        self.rpc.runtime.agent.provider = Wait()
        main = await self.rpc.dispatch('task.start', {'prompt': 'wait'})
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('model.reasoning', {**args, 'effort': 'high'})
        side = await self.rpc.dispatch('sidechat.open', args)
        # Main task is running; the side's idle settings can change independently.
        await self.rpc.dispatch('sidechat.reasoning', {**args, 'id': side['id'], 'effort': 'medium'})
        await self.rpc.dispatch('task.cancel', {'run_id': main['run_id']})
        await self.rpc.finishing
        await self.rpc.dispatch('model.select', {'model': {**self.model, 'model': 'custom-model', 'thinking_mode': 'default'}})
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('model.reasoning', {**args, 'effort': 'high'})

    async def test_api_payload_omit_off_and_effort(self):
        captured = []
        def handle(request):
            captured.append(json.loads(request.content))
            chunk = dict(id='test', object='chat.completion.chunk', created=0, model='deepseek-flash',
                         choices=[dict(index=0, delta={'content': 'ok'}, finish_reason='stop')])
            return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                                  text='data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n')
        for effort in ('default', 'none', 'low', 'medium', 'high', 'max'):
            settings = reasoning.with_effort(Settings(self.root, **self.model), effort)
            settings.validate()
            provider = Provider(settings)
            provider.client = AsyncOpenAI(api_key='fixture', max_retries=0,
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
            try:
                await provider.complete([{'role': 'user', 'content': 'hello'}], [], lambda *_: None)
                self.assertNotIn('thinking', captured[-1])  # No legacy preset overriding selection.
                if effort == 'default':
                    self.assertNotIn('reasoning_effort', captured[-1])
                else:
                    self.assertEqual(captured[-1]['reasoning_effort'], effort)
            finally:
                await provider.close()

    async def test_capabilities_are_model_and_protocol_specific(self):
        models = [
            {'model': 'deepseek-flash', 'api_format': 'openai'},
            {'model': 'gpt-6-astra', 'api_format': 'responses'},
            {'model': 'gpt-5', 'api_format': 'responses'},
            {'model': 'claude-sonnet-4', 'api_format': 'anthropic'},
            {'model': 'arbitrary-local', 'api_format': 'openai'},
        ]
        caps = await self.rpc.dispatch('model.capabilities', {'models': models})
        self.assertIn('max', caps[0]['options'])
        self.assertNotIn('none', caps[1]['options'])
        self.assertNotIn('max', caps[2]['options'])
        self.assertEqual(caps[3]['options'], ['default'])
        self.assertEqual(caps[4]['options'], ['default'])
