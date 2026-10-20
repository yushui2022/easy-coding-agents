import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from eca.activity import StreamActivity, tool_target
from eca.config import Settings
from eca.provider import Provider


class ActivityTests(unittest.TestCase):
    def test_rate_excludes_wait_and_tail_and_uses_reported_tokens(self):
        now = [0.0]
        events = []
        activity = StreamActivity('r', lambda *e: events.append(e), lambda: now[0])
        now[0] = 40.0  # a slow first response is not generation time
        activity.observe(reasoning='private thought')
        self.assertIsNone(activity.snapshot()['tokens_per_second'])
        now[0] = 42.0
        activity.observe(text='hello world')
        snapshot = activity.snapshot()
        self.assertEqual(snapshot['first_response_ms'], 40000)
        self.assertEqual(snapshot['generation_ms'], 2000)
        self.assertEqual(snapshot['throughput_source'], 'estimate')
        self.assertNotIn('private thought', str(events))
        now[0] = 100.0  # delayed usage packet doesn't reduce output speed
        final = activity.snapshot({'completion_tokens': 100})
        self.assertEqual(final['tokens_per_second'], 50.0)
        self.assertEqual(final['throughput_source'], 'provider')
        self.assertEqual(final['output_tokens'], 100)
        self.assertIsNone(StreamActivity('retry', lambda *_: None).snapshot()['tokens_per_second'])

    def test_incremental_counts_are_independent_of_chunk_boundaries_and_throttled(self):
        now = [1.0]
        events = []
        activity = StreamActivity('r', lambda *e: events.append(e), lambda: now[0])
        for c in '中文abc' * 100:
            now[0] += .001
            activity.observe(arguments=c, tool='read')
        self.assertLessEqual(len(events), 3)
        other = StreamActivity('r', lambda *_: None)
        other.observe(arguments='中文abc' * 100, tool='read')
        self.assertEqual(activity.snapshot()['estimated_output_tokens'], other.snapshot()['estimated_output_tokens'])
        self.assertEqual(activity.snapshot()['tool_argument_chars'], 500)
        self.assertIsNone(other.snapshot({'completion_tokens': 10})['tokens_per_second'])
        self.assertEqual(activity.snapshot({'completion_tokens': True})['throughput_source'], 'estimate')

    def test_subject_is_bounded_and_does_not_expose_contents_or_url_credentials(self):
        self.assertEqual(tool_target({'path': 'src/中文 file.py', 'content': 'private content'}),
                         'src/中文 file.py')
        self.assertEqual(tool_target({'path': 'src', 'pattern': 'TODO'}), 'src · TODO')
        self.assertEqual(tool_target({'server': 'docs', 'tool': 'lookup', 'arguments': {'private': 'hidden'}}), 'docs · lookup')
        self.assertNotIn('password123', tool_target({'url': 'https://user:password123@example.com/a?token=password123'}))
        self.assertLessEqual(len(tool_target({'command': 'echo ' * 10000})), 180)
        self.assertEqual(tool_target({'content': 'x' * 10000, 'api_key': 'secret'}), '')


    def test_hidden_reasoning_usage_is_not_divided_by_visible_text_time(self):
        now = [1.0]
        activity = StreamActivity('r', lambda *_: None, lambda: now[0])
        activity.observe(phase='thinking')
        now[0] = 10
        activity.observe(text='answer')
        now[0] = 11
        activity.observe(text=' continued')
        self.assertIsNotNone(activity.snapshot()['tokens_per_second'])
        final = activity.snapshot({'completion_tokens': 10000})
        self.assertIsNone(final['tokens_per_second'])
        self.assertEqual(final['throughput_unavailable_reason'], 'unobserved_reasoning')
        activity.opaque_reasoning = False
        self.assertIsNone(activity.snapshot({'completion_tokens': 10000,
            'completion_tokens_details': {'reasoning_tokens': 9000}})['tokens_per_second'])


class AdapterActivityTests(unittest.IsolatedAsyncioTestCase):
    async def test_responses_tool_arguments_and_text_reach_shared_telemetry(self):
        class Stream:
            async def __aiter__(self):
                yield NS(type='response.output_item.added', output_index=0, item=NS(type='reasoning'))
                yield NS(type='response.output_item.added', output_index=1, item=NS(type='function_call', name='read'))
                yield NS(type='response.function_call_arguments.delta', output_index=1, delta='{"path":')
                yield NS(type='response.function_call_arguments.delta', output_index=1, delta='"a.py"}')
                yield NS(type='response.output_text.delta', delta='Reading file')
                usage = NS(model_dump=lambda: {'input_tokens': 20, 'output_tokens': 10})
                item = NS(type='function_call', name='read', call_id='c', arguments='{"path":"a.py"}',
                          model_dump=lambda **_: dict(type='function_call', name='read', call_id='c', arguments='{"path":"a.py"}'))
                yield NS(type='response.completed', response=NS(status='completed', output=[item], usage=usage))
            close = AsyncMock()
        provider = Provider(Settings(Path.cwd(), api_format='responses', api_key='fixture', network_retries=0))
        provider.client = NS(responses=NS(create=AsyncMock(return_value=Stream())), close=AsyncMock())
        events = []
        try:
            await provider.complete([], [], lambda *e: events.append(e))
        finally:
            await provider.close()
        phases = [d['phase'] for e, d in events if e == 'model_activity']
        self.assertEqual(phases, ['thinking', 'tool_arguments', 'responding'])
        self.assertNotIn('model_delta', [e for e, _ in events])
        end = events[-1][1]
        self.assertEqual(end['tool_argument_chars'], len('{"path":"a.py"}'))
        self.assertEqual(end['text_chars'], len('Reading file'))
        self.assertEqual(end['output_tokens'], 10)

    async def test_cancel_keeps_partial_counters_without_fabricating_usage(self):
        ready = asyncio.Event()
        provider = Provider(Settings(Path.cwd(), network_retries=0))
        async def complete(_, __, emit):
            emit('model_delta', {'reasoning': 'private thought'})
            ready.set()
            await asyncio.Event().wait()
        provider._complete = complete
        events = []
        task = asyncio.create_task(provider.complete([], [], lambda *e: events.append(e)))
        await asyncio.wait_for(ready.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(events[-1][1]['status'], 'cancelled')
        self.assertIsNone(events[-1][1]['output_tokens'])
        self.assertEqual(events[-1][1]['reasoning_chars'], 15)
        self.assertNotIn('private thought', str(events))
