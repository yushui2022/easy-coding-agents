import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eca.config import Settings
from eca.model_limits import apply_defaults
from eca.errors import OutputLimitError
import test_runtime
from test_runtime import FakeProvider, yes
from eca.agent import Agent


class LimitTests(unittest.IsolatedAsyncioTestCase):
    setUp = test_runtime.RuntimeTests.setUp
    tearDown = test_runtime.RuntimeTests.tearDown

    def test_known_endpoint_and_explicit_override(self):
        values = {'model': 'deepseek-v4-pro', 'base_url': 'https://api.deepseek.com/v1'}
        apply_defaults(values, set())
        self.assertEqual(values['max_output_tokens'], 393216)
        self.assertEqual(values['context_window_tokens'], 1048576)
        values['max_output_tokens'] = 4096
        apply_defaults(values, {'max_output_tokens'})
        self.assertEqual(values['max_output_tokens'], 4096)
        for host in ('https://proxy.example/v1', 'https://api.deepseek.com.evil/v1', 'http://api.deepseek.com'):
            value = {'model': 'deepseek-v4-pro', 'base_url': host}
            apply_defaults(value, set())
            self.assertNotIn('max_output_tokens', value)

    def test_load_and_profile_defaults(self):
        (self.root/'eca.toml').write_text('[agent]\nmodel="deepseek-v4-pro"\nbase_url="https://api.deepseek.com/v1"\nmax_turns=0\noutput_recovery_limit=0\n')
        with patch.dict(os.environ, {}, clear=True):
            cfg = Settings.load(self.root)
        self.assertEqual(cfg.max_output_tokens, 393216)
        cfg.model_profiles = {'worker': {'model': 'deepseek-flash', 'base_url': 'https://api.deepseek.com/v1', 'api_format': 'openai', 'api_key_env': 'TEST_KEY'}}
        self.assertEqual(cfg.select_profile('worker').max_output_tokens, 393216)
        cfg.model_profiles['worker']['max_output_tokens'] = 100000
        cfg.validate()
        self.assertEqual(cfg.select_profile('worker').max_output_tokens, 100000)
        with patch.dict(os.environ, {}, clear=True):
            cfg = Settings.load(self.root, max_output_tokens=16384, context_window_tokens=65536)
        self.assertEqual(cfg.max_output_tokens, 16384)
        self.assertEqual(cfg.context_window_tokens, 65536)

    def test_cli_limits_and_defaults(self):
        from eca.cli import parser
        args = parser().parse_args(['--max-turns', '0', '--output-recovery-limit', '0',
                                    '--max-output-tokens', '16384', '--context-window-tokens', '65536'])
        self.assertEqual(args.max_turns, 0)
        self.assertEqual(args.output_recovery_limit, 0)
        self.assertEqual(args.max_output_tokens, 16384)
        self.assertEqual(args.context_window_tokens, 65536)
        self.assertEqual(Settings(self.root).max_turns, 0)
        self.assertEqual(Settings(self.root).output_recovery_limit, 0)

    async def test_unlimited_turns_and_recovery_can_finish(self):
        self.settings.max_turns = self.settings.output_recovery_limit = 0
        self.settings.project_memory = False
        provider = FakeProvider([OutputLimitError() for _ in range(4)] + [{'role':'assistant','content':'done'}])
        agent = Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None, provider)
        try:
            await agent.run('Finish the task')
            self.assertEqual(self.state['status'], 'idle')
            self.assertEqual(len(provider.contexts), 5)
            self.assertEqual(self.state['messages'][-1]['content'], 'done')
        finally:
            await agent.close()

    async def test_unlimited_loop_still_cancellable(self):
        self.settings.max_turns = self.settings.output_recovery_limit = 0
        self.settings.project_memory = False
        entered = asyncio.Event()
        class Waiting(FakeProvider):
            async def complete(self, *args):
                entered.set()
                await asyncio.Event().wait()
        agent = Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None, Waiting([]))
        task = asyncio.create_task(agent.run('work'))
        try:
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(self.state['status'], 'interrupted')
        finally:
            await agent.close()

    def test_invalid_limits(self):
        for key in ('max_turns','output_recovery_limit'):
            with self.assertRaises(ValueError):
                Settings(self.root, **{key:-1}).validate()
