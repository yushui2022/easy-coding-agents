"""Recovery and acceptance evidence without paid model requests."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from eca.agent import Agent
from eca.cli import App, parser, async_main
from eca.config import Settings
from eca.errors import OutputLimitError
from eca.store import Store
from eca.verification import command_status
from test_runtime import FakeProvider, call, yes, no


OK = json.dumps({'exit_code': 0, 'timed_out': False, 'stdout': '2 passed', 'stderr': ''})
DONE = {'role': 'assistant', 'content': 'done'}


class UpgradeTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_recovery_does_not_replay_completed_mutation(self):
        self.settings.permission = 'accept-edits'
        self.provider.responses = iter([call('write', {'path': 'one.py', 'content': 'x=1'}), OutputLimitError(), DONE])
        await self.agent.run('implement')
        self.assertEqual(self.agent.state['status'], 'idle')
        self.assertEqual(len(self.agent.changes.list()), 1)
        self.assertEqual(len([m for m in self.agent.state['messages'] if m['role'] == 'tool']), 1)
        self.assertIn('Split remaining edits', str(self.provider.contexts[-1]))

    async def test_recovery_bounded_and_disconnection_not_retried(self):
        self.settings.output_recovery_limit = 2
        self.provider.responses = iter([OutputLimitError()] * 4)
        with self.assertRaises(OutputLimitError):
            await self.agent.run('implement')
        self.assertEqual(len(self.provider.contexts), 3)
        self.provider.contexts.clear()
        self.provider.responses = iter([RuntimeError('disconnected'), DONE])
        with self.assertRaises(RuntimeError):
            await self.agent.run('continue')
        self.assertEqual(len(self.provider.contexts), 1)

    async def test_recovery_respects_last_turn(self):
        self.settings.max_turns = 1
        self.provider.responses = iter([OutputLimitError(), DONE])
        await self.agent.run('implement')
        self.assertEqual(self.agent.state['status'], 'limit')
        self.assertEqual(len(self.provider.contexts), 1)

    async def test_progress_survives_compaction_and_resume_without_changing_prefix(self):
        for i in range(20):
            self.agent.observe('read', {'path': f'{i}.py'}, 'historical contents')
        self.agent.state['messages'] = [{'role': 'user', 'content': 'work'}, DONE]
        self.provider.responses = iter([{'role': 'assistant', 'content': 'short summary'}, DONE])
        await self.agent.compact()
        self.assertEqual(len(self.store.load(self.agent.state['id'])['progress']), 12)
        prefix = self.agent.system_prompt()
        await self.agent.run('continue')
        self.assertIn('19.py', self.provider.contexts[-1][0][-1]['content'])
        self.assertNotIn('historical contents', self.agent.progress_context())
        self.assertEqual(prefix, self.agent.system_prompt())

    async def test_verify_pass_then_external_edit_is_stale(self):
        path = self.root / 'source.py'
        path.write_text('a=1')
        with patch('eca.tools.run_process', AsyncMock(return_value=OK)):
            self.assertTrue(await self.agent.verify('pytest -q'))
        self.assertEqual(self.agent.verification_status()['status'], 'passed')
        path.write_text('a=2')
        self.assertEqual(self.agent.verification_status()['status'], 'stale')
        self.assertEqual(len(self.provider.contexts), 0)

    async def test_verify_denied_modes_and_isolation_never_execute(self):
        with patch('eca.tools.run_process', AsyncMock(return_value=OK)) as process:
            self.agent.tools.approve = no
            self.assertFalse(await self.agent.verify('pytest'))
            self.agent.tools.approve = yes
            for mode in ('plan', 'chat'):
                self.settings.mode = mode
                self.assertFalse(await self.agent.verify('pytest'))
            self.settings.mode = 'code'
            self.agent.state['isolated'] = True
            self.assertFalse(await self.agent.verify('pytest'))
            process.assert_not_awaited()

    async def test_verify_zero_tests_timeout_failure_and_unknown_snapshot(self):
        for output, status in [
            ({'exit_code': 0, 'timed_out': False, 'stdout': 'no tests ran in 0.01s'}, 'no_tests'),
            ({'exit_code': 0, 'timed_out': True}, 'failed'),
            ({'exit_code': 1, 'timed_out': False}, 'failed')]:
            with patch('eca.tools.run_process', AsyncMock(return_value=json.dumps(output))):
                self.assertFalse(await self.agent.verify('pytest'))
            self.assertEqual(self.agent.state['verification']['status'], status)
        with patch('eca.tools.run_process', AsyncMock(return_value=OK)), patch.object(self.agent.memory(), 'fingerprint', return_value=None):
            self.assertFalse(await self.agent.verify('pytest'))
        self.assertEqual(self.agent.state['verification']['status'], 'unconfirmed_snapshot')

    async def test_cancel_verification_repairs_history_without_replay(self):
        with patch('eca.tools.run_process', AsyncMock(side_effect=asyncio.CancelledError)) as process:
            with self.assertRaises(asyncio.CancelledError):
                await self.agent.verify('pytest')
            process.assert_awaited_once()
        state = self.store.load(self.agent.state['id'])
        self.assertEqual(state['verification']['status'], 'interrupted')
        self.assertEqual(state['messages'][-1]['role'], 'tool')
        self.assertFalse(self.agent.busy)

    async def test_cli_exit_code_separates_idle_from_verified(self):
        # App uses this test's already locked Store; no second project writer.
        app = App.__new__(App)
        app.agent, app.state, app.settings = self.agent, self.agent.state, self.settings
        from eca.runtime import Runtime
        app.runtime = Runtime(self.agent)
        app.args = parser().parse_args(['-p', 'work', '--allow-shell', '--verify-command', 'pytest'])
        app.streaming = False
        app.emit = lambda *_: None
        self.provider.responses = iter([DONE, DONE])
        with patch('eca.tools.run_process', AsyncMock(return_value=OK)):
            self.assertEqual(await app.run_task('work'), 0)
        with patch('eca.tools.run_process', AsyncMock(return_value='Denied')):
            self.assertEqual(await app.run_task('work'), 3)
        self.assertEqual(app.state['status'], 'idle')

    async def test_cli_requires_explicit_shell_authorization(self):
        with self.assertRaisesRegex(ValueError, '--allow-shell'):
            await async_main(parser().parse_args(['-p', 'work', '--verify-command', 'pytest']))

    def test_unstructured_or_boolean_exit_is_not_success(self):
        for result in ('tests passed', '[]', '{"exit_code":false,"timed_out":false}'):
            self.assertEqual(command_status('pytest', result), 'failed')
