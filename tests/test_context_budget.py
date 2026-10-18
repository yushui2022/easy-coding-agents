import json
import os
from pathlib import Path
import tempfile
import unittest

from eca.agent import Agent
from eca.config import Settings
from eca.context import ContextBudget, estimate_tokens, summary_request
from eca.store import Store
from test_runtime import FakeProvider, call, yes


class ContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        base = Path(os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.tmp.name)
        self.settings = Settings(self.root, project_memory=False)
        self.store = Store(self.root)
        self.state = self.store.create()
        self.provider = FakeProvider([])
        self.agent = Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None, self.provider)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_unicode_tools_and_reservations(self):
        english = [{'role': 'user', 'content': 'a' * 1000}]
        chinese = [{'role': 'user', 'content': '中' * 1000}]
        self.assertGreater(estimate_tokens(chinese, []), estimate_tokens(english, []))
        budget = self.agent.context_budget
        huge_tool = [{'description': 'x' * (budget.input_limit * 4)}]
        self.assertTrue(budget.fits(english, []))
        self.assertFalse(budget.fits(english, huge_tool))
        self.assertEqual(budget.input_limit, 32768 - 8192 - 1024)

    def test_calibration_includes_anthropic_cache_and_resets_on_model_change(self):
        self.settings.api_format = 'anthropic'
        messages = [{'role': 'user', 'content': 'hello'}]
        budget = self.agent.context_budget
        budget.observe(messages, [], dict(input_tokens=100, cache_read_input_tokens=500, cache_creation_input_tokens=200))
        self.assertGreaterEqual(budget.estimate(messages, []), 880)
        factor = budget.factor
        budget.observe(messages, [], {'input_tokens': 1})
        budget.observe(messages, [], {'input_tokens': True})
        self.assertEqual(budget.factor, factor)
        self.settings.model = 'different'
        self.assertEqual(budget.factor, 1)

    def test_openai_cache_is_not_double_counted(self):
        messages = [{'role': 'user', 'content': 'hello'}]
        budget = self.agent.context_budget
        budget.observe(messages, [], {'prompt_tokens': 1000, 'prompt_cache_hit_tokens': 800})
        self.assertLessEqual(budget.estimate(messages, []), 1101)
        self.assertGreaterEqual(budget.estimate(messages, []), 1100)

    def test_configuration_and_profile_budget(self):
        (self.root / 'eca.toml').write_text('''[agent]
context_window_tokens = 16000
context_reserve_tokens = 500
[model_profiles.small]
model = "local"
base_url = "http://localhost:1234/v1"
api_format = "openai"
api_key_env = "TEST_UNUSED_KEY"
max_output_tokens = 1000
context_window_tokens = 8000
context_reserve_tokens = 300
''', encoding='utf-8')
        settings = Settings.load(self.root)
        self.assertEqual(settings.context_window_tokens, 16000)
        selected = settings.select_profile('small')
        self.assertEqual(ContextBudget(selected).input_limit, 6700)
        for invalid in (0, True, -1, '8000'):
            settings.context_window_tokens = invalid
            with self.assertRaises(ValueError):
                settings.validate()
        settings.context_window_tokens = settings.max_output_tokens
        with self.assertRaises(ValueError):
            settings.validate()

    def test_summary_keeps_goals_checkpoint_and_valid_json(self):
        history = [{'role': 'user', 'content': 'Keep user edits'},
                   {'role': 'tool', 'content': 'evidence' * 10000},
                   {'role': 'user', 'content': 'Also preserve API compatibility'}]
        request = summary_request(self.agent.context_budget, history, history, 'Changed a.py; tests not run', [], 3000)
        payload = json.loads(request[1]['content'])
        self.assertEqual(payload['original_request'], 'Keep user edits')
        self.assertEqual(payload['latest_request'], 'Also preserve API compatibility')
        self.assertIn('tests not run', payload['previous_summary'])
        self.assertTrue(payload['incomplete'])
        self.assertLessEqual(len(json.dumps(request, ensure_ascii=False)), 3000)
        self.assertIn('Checks and evidence', request[0]['content'])
        self.assertEqual(len(history[1]['content']), 80000)

    async def test_token_trigger_compacts_even_below_character_budget(self):
        self.settings.mode = 'chat'
        self.settings.context_window_tokens = 6000
        self.settings.max_output_tokens = 1000
        self.state['messages'] = [{'role': 'user', 'content': 'Preserve API'},
                                  {'role': 'assistant', 'content': '中' * 4000}]
        self.provider.responses = iter([{'role': 'assistant', 'content': 'Goal: preserve API. No tests run.'},
                                        {'role': 'assistant', 'content': 'done'}])
        await self.agent.run('Continue')
        self.assertEqual(len(self.provider.contexts), 2)
        self.assertEqual(self.state['context_start'], 2)
        self.assertEqual(len(self.state['messages']), 4)
        self.assertEqual(self.store.load(self.state['id'])['summary'], self.state['summary'])
        for messages, tools in self.provider.contexts:
            self.assertTrue(self.agent.context_budget.fits(messages, tools))

    async def test_oversized_summary_leaves_previous_checkpoint_unchanged(self):
        self.state.update(summary='previous', context_start=0)
        self.state['messages'] = [{'role': 'user', 'content': 'goal'}, {'role': 'assistant', 'content': 'answer'}]
        self.provider.responses = iter([{'role': 'assistant', 'content': '中' * 20000}])
        with self.assertRaisesRegex(ValueError, 'token budget'):
            await self.agent.compact()
        self.assertEqual(self.state['summary'], 'previous')
        self.assertEqual(self.state['context_start'], 0)
        self.assertEqual(len(self.state['messages']), 2)

    async def test_preflight_blocks_request_before_provider_or_usage_record(self):
        with self.assertRaisesRegex(ValueError, 'input token budget'):
            await self.agent.model_complete([{'role': 'user', 'content': '中' * 20000}], [], lambda *_: None)
        self.assertEqual(self.provider.contexts, [])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM usage_requests').fetchone()[0], 0)

    async def test_automatic_compaction_retains_paired_tools_and_anchor(self):
        self.state['messages'] = [{'role': 'user', 'content': 'Fix bug'}, call('read', {'path': 'a'}, 'old'),
                                  {'role': 'tool', 'tool_call_id': 'old', 'content': '中' * 12000},
                                  call('read', {'path': 'b'}, 'recent'),
                                  {'role': 'tool', 'tool_call_id': 'recent', 'content': 'recent evidence'}]
        self.provider.responses = iter([{'role': 'assistant', 'content': 'Read a. No edits or tests yet.'}])
        await self.agent._compact(automatic=True)
        context = self.agent.context()
        self.assertEqual([m['role'] for m in context], ['system', 'user', 'assistant', 'tool'])
        self.assertEqual(context[1]['content'], 'Fix bug')
        self.assertEqual(context[-1]['tool_call_id'], context[-2]['tool_calls'][0]['id'])
        self.assertEqual(len(self.state['messages']), 5)
