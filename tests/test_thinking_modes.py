import json
from pathlib import Path
import unittest
import httpx
from openai import AsyncOpenAI
from eca.config import Settings
from eca.provider import Provider


class ThinkingTests(unittest.IsolatedAsyncioTestCase):
    async def test_presets_progress_and_scoped_tool_replay(self):
        captured = []
        def handle(request):
            captured.append(json.loads(request.content))
            deltas = [{'reasoning_content': 'private reasoning'}, {'tool_calls': [
                {'index': 0, 'id': 'call-1', 'type': 'function', 'function': {'name': 'read', 'arguments': '{"path":'}}]},
                {'tool_calls': [{'index': 0, 'function': {'arguments': '"file.txt"}'}}]}, {}]
            chunks = [dict(id='r', object='chat.completion.chunk', created=0, model='deepseek-flash',
                           choices=[dict(index=0, delta=delta, finish_reason='tool_calls' if i == 3 else None)])
                      for i, delta in enumerate(deltas)]
            return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                text=''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n')
        provider = Provider(Settings(Path.cwd(), api_key='fixture', model='deepseek-flash',
                                     base_url='https://example.invalid/v1', thinking_mode='fast'))
        provider.client = AsyncOpenAI(api_key='fixture', max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        tools = [{'type': 'function', 'function': {'name': 'read', 'parameters': {'type': 'object'}}}]
        events = []
        try:
            message, _ = await provider.complete([dict(role='user', content='work')], tools, lambda e,d: events.append((e,d)))
            self.assertEqual(captured[-1]['thinking'], {'type': 'disabled'})
            self.assertNotIn('reasoning_effort', captured[-1])
            self.assertEqual(message['tool_calls'][0]['function']['arguments'], '{"path":"file.txt"}')
            self.assertNotIn('private reasoning', str(events))
            self.assertEqual([d['phase'] for e,d in events if e == 'model_activity'], ['thinking', 'tool_arguments'])
            end = next(d for e,d in events if e == 'request_end')
            self.assertIn('first_response_ms', end)
            self.assertEqual(end['reasoning_chars'], len('private reasoning'))
            for mode, effort in [('balanced', 'low'), ('deep', 'high')]:
                provider.settings.thinking_mode = mode
                await provider.complete([message], tools, lambda *_: None)
                self.assertEqual(captured[-1]['thinking'], {'type': 'enabled'})
                self.assertEqual(captured[-1]['reasoning_effort'], effort)
                self.assertEqual(captured[-1]['messages'][0]['reasoning_content'], 'private reasoning')
                self.assertNotIn('reasoning_scope', captured[-1]['messages'][0])
            provider.settings.model = 'deepseek-other'
            await provider.complete([message], tools, lambda *_: None)
            self.assertEqual(captured[-1]['messages'][0]['reasoning_content'], '')
            provider.settings.model = 'another-provider'
            provider.settings.thinking_mode = 'default'
            await provider.complete([message], tools, lambda *_: None)
            self.assertNotIn('thinking', captured[-1])
            self.assertNotIn('reasoning_content', captured[-1]['messages'][0])
        finally:
            await provider.close()
