import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from openai import AsyncOpenAI, BadRequestError
from eca.agent import Agent
from eca.config import Settings
from eca.errors import ContextLimitError, context_rejection
from eca.provider import Provider
from eca.store import Store
from test_runtime import FakeProvider, yes

DONE = dict(role='assistant', content='done')
SUMMARY = dict(role='assistant', content='Goal: preserve code. Completed: read only. Pending: report. No writes executed.')


class ContextRejectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_strict_http_signals_and_attempt_accounting(self):
        settings = Settings(Path.cwd(), api_key='fixture', network_retries=3)
        provider = Provider(settings)
        provider.client = AsyncOpenAI(api_key='fixture', max_retries=0, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(400, json={
                'error': {'code': 'context_length_exceeded', 'message': 'private-provider-body'}}))))
        events = []
        try:
            with self.assertRaises(ContextLimitError) as caught:
                await provider.complete([dict(role='user', content='work')], [], lambda e,d: events.append((e,d)))
            self.assertNotIn('private-provider-body', str(caught.exception))
            self.assertEqual(sum(e == 'request_start' for e,d in events), 1)
            self.assertEqual([d['status'] for e,d in events if e == 'request_end'], ['failed'])
        finally: await provider.close()
        for status, body in [(413, {}), (401, {'code':'context_length_exceeded'}),
                             (400, {'message':'context might be long'}), (400, {'code':'invalid_api_key'})]:
            self.assertFalse(context_rejection(status, body))

    async def test_anthropic_rejection_and_visible_output_not_recovered(self):
        provider = Provider(Settings(Path.cwd(), api_format='anthropic', api_key='fixture'))
        from eca.anthropic import AnthropicProvider
        provider.native = AnthropicProvider(provider.settings)
        provider.native.client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(400, json={'error': {'type':'invalid_request_error', 'message':'prompt is too long: private'}})))
        try:
            with self.assertRaises(ContextLimitError):
                await provider.complete([dict(role='user',content='work')], [], lambda *_: None)
        finally: await provider.close()
        provider = Provider(Settings(Path.cwd()))
        async def partial(messages, tools, emit):
            emit('text', 'partial')
            raise BadRequestError('rejected', response=httpx.Response(400, request=httpx.Request('POST','https://example.invalid')),
                                  body={'code':'context_length_exceeded'})
        with patch.object(provider, '_complete', partial), self.assertRaises(BadRequestError):
            await provider.complete([], [], lambda *_: None)
        await provider.close()

    async def exercise(self, responses, expected_error=None):
        with tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir())) as directory:
            store = Store(Path(directory))
            state = store.create('chat')
            state['messages'] = [dict(role='user', content='Preserve all source files.'),
                                 dict(role='assistant', content='Historical notes. ' * 2000)]
            store.save(state)
            provider = FakeProvider(responses)
            agent = Agent(Settings(Path(directory), mode='chat', auto_compact=False, project_memory=False, max_turns=4),
                          store, state, yes, yes, lambda *_: None, provider)
            original = json.dumps(state['messages'])
            try:
                with patch.object(agent.tools, 'execute', AsyncMock(side_effect=AssertionError('no replay'))) as execute:
                    if expected_error:
                        with self.assertRaises(expected_error): await agent.run('Continue and report')
                        self.assertEqual(state.get('context_start', 0), 0)
                    else:
                        await agent.run('Continue and report')
                        self.assertEqual(state['status'], 'idle')
                        self.assertGreater(state['context_start'], 0)
                        self.assertLess(len(str(provider.contexts[-1])), len(str(provider.contexts[0])))
                    execute.assert_not_called()
                self.assertEqual(json.dumps(state['messages'][:2]), original)
                return len(provider.contexts)
            finally:
                await agent.close()
                store.close()

    async def test_rejection_compacts_once_without_replaying_and_preserves_archive(self):
        self.assertEqual(await self.exercise([ContextLimitError(), SUMMARY, DONE]), 3)

    async def test_summary_rejection_stops_without_overwriting_checkpoint(self):
        self.assertEqual(await self.exercise([ContextLimitError(), ContextLimitError()], ContextLimitError), 2)

    async def test_generic_transport_failure_does_not_compact(self):
        self.assertEqual(await self.exercise([RuntimeError('generic')], RuntimeError), 1)
