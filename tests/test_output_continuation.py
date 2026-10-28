"""A response cut at the output token limit keeps its streamed text and continues.

Before this, the whole response was discarded and the model was told to split the
work up, so long answers looked like they hit an invisible wall.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import httpx
from openai import AsyncOpenAI

from eca.agent import Agent
from eca.config import Settings
from eca.errors import OutputLimitError
from eca.provider import Provider
from eca.store import Store
from test_runtime import FakeProvider, yes

DONE = {'role': 'assistant', 'content': 'done'}


class OutputContinuationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name)
        self.settings = Settings(self.root, project_memory=False, auto_compact=False, max_turns=8)
        self.store = Store(self.root)
        self.provider = FakeProvider([])
        self.agent = Agent(self.settings, self.store, self.store.create(), yes, yes, lambda *_: None, self.provider)

    async def asyncTearDown(self):
        await self.agent.close()
        self.store.close()
        self.tmp.cleanup()

    def texts(self):
        return [m['content'] for m in self.agent.state['messages'] if m['role'] == 'assistant' and m.get('content')]

    async def test_streamed_text_is_kept_and_continued_in_one_answer(self):
        self.provider.responses = iter([OutputLimitError('第一段已经写出来的正文'),
                                        {'role': 'assistant', 'content': '，第二段接着写完。'}])
        await self.agent.run('写一段长文')
        self.assertEqual(self.agent.state['status'], 'idle')
        self.assertEqual(self.texts(), ['第一段已经写出来的正文，第二段接着写完。'])
        self.assertIn('Continue from the exact point', str(self.provider.contexts[-1][0]))
        self.assertEqual([m for m in self.agent.state['messages'] if m['role'] == 'tool'], [])

    async def test_truncated_tool_call_keeps_text_and_asks_for_smaller_steps(self):
        self.provider.responses = iter([OutputLimitError('准备写文件', pending_tools=True),
                                        {'role': 'assistant', 'content': 'done'}])
        await self.agent.run('写文件')
        self.assertTrue(any(t.startswith('准备写文件') for t in self.texts()))
        self.assertIn('smaller pieces', str(self.provider.contexts[-1][0]))
        self.assertEqual([m for m in self.agent.state['messages'] if m['role'] == 'tool'], [])

    async def test_configured_cap_applies_to_continuations(self):
        self.settings.output_recovery_limit = 2
        self.provider.responses = iter([OutputLimitError('a'), OutputLimitError('b'), OutputLimitError('c')])
        with self.assertRaises(OutputLimitError):
            await self.agent.run('x')
        self.assertEqual(len(self.provider.contexts), 3)


class ProviderPartialTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await self.provider.close()

    async def make(self, chunks):
        events = ''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks) + 'data: [DONE]\n\n'

        async def handler(request):
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, text=events)

        self.provider = Provider(Settings(Path.cwd(), api_key='test'))
        self.provider.client = AsyncOpenAI(api_key='test', http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        return self.provider

    async def test_streamed_text_survives_the_limit(self):
        provider = await self.make([
            {'choices': [{'index': 0, 'delta': {'content': 'abc'}, 'finish_reason': None}]},
            {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'length'}]}])
        with self.assertRaises(OutputLimitError) as caught:
            await provider.complete([], [], lambda *_: None)
        self.assertEqual(caught.exception.partial, 'abc')
        self.assertFalse(caught.exception.pending_tools)

    async def test_incomplete_tool_call_is_flagged(self):
        provider = await self.make([
            {'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'id': 'c1', 'type': 'function',
                                                               'function': {'name': 'write', 'arguments': '{"path"'}}]},
                          'finish_reason': None}]},
            {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'length'}]}])
        with self.assertRaises(OutputLimitError) as caught:
            await provider.complete([], [], lambda *_: None)
        self.assertEqual(caught.exception.partial, '')
        self.assertTrue(caught.exception.pending_tools)
