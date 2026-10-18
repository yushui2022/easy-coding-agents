import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from eca.agent import Agent
from eca.config import Settings
from eca.store import Store
from eca.workflow import verified_run, suite_status
from eca.cli import parser, async_main
from test_runtime import FakeProvider, yes

DONE = {'role': 'assistant', 'content': 'done'}
OK = json.dumps({'exit_code': 0, 'timed_out': False, 'stdout': '2 passed'})
FAIL = json.dumps({'exit_code': 1, 'timed_out': False, 'stdout': 'assertion failed'})


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name)
        self.store = Store(self.root)
        self.provider = FakeProvider([DONE] * 10)
        self.agent = Agent(Settings(self.root, project_memory=False, auto_compact=False),
                           self.store, self.store.create(), yes, yes, lambda *_: None, self.provider)

    async def asyncTearDown(self):
        await self.agent.close()
        self.store.close()
        self.tmp.cleanup()

    async def test_multiple_checks_and_external_change(self):
        with patch('eca.tools.run_process', AsyncMock(return_value=OK)) as process:
            self.assertTrue(await verified_run(self.agent, 'work', ['pytest', 'python -B check.py']))
            self.assertEqual(process.await_count, 2)
        self.assertEqual(suite_status(self.agent)['status'], 'passed')
        (self.root / 'new.py').write_text('changed')
        self.assertEqual(suite_status(self.agent)['status'], 'stale')

    async def test_default_stops_at_failure_without_repair(self):
        with patch('eca.tools.run_process', AsyncMock(return_value=FAIL)) as process:
            self.assertFalse(await verified_run(self.agent, 'work', ['pytest', 'build']))
            process.assert_awaited_once()
        self.assertEqual(len(self.provider.contexts), 1)

    async def test_repair_restarts_all_checks_and_preserves_rounds(self):
        with patch('eca.tools.run_process', AsyncMock(side_effect=[OK, FAIL, OK, OK])) as process:
            self.assertTrue(await verified_run(self.agent, 'preserve feature', ['pytest', 'build'], 1))
            self.assertEqual(process.await_count, 4)
        suite = self.store.load(self.agent.state['id'])['verification_suite']
        self.assertEqual([r['status'] for r in suite['rounds']], ['failed', 'passed'])
        self.assertIn('preserve feature', str(self.provider.contexts[-1]))
        self.assertEqual(len(self.provider.contexts), 2)

    async def test_repair_budget_exhaustion(self):
        outputs = [json.dumps({'exit_code': 1, 'timed_out': False, 'stdout': str(i)}) for i in range(3)]
        with patch('eca.tools.run_process', AsyncMock(side_effect=outputs)) as process:
            self.assertFalse(await verified_run(self.agent, 'work', ['pytest'], 2))
            self.assertEqual(process.await_count, 3)
        self.assertEqual(len(self.provider.contexts), 3)
        self.assertEqual(suite_status(self.agent)['status'], 'failed')

    async def test_identical_failure_without_source_progress_stops_early(self):
        with patch('eca.tools.run_process', AsyncMock(return_value=FAIL)) as process:
            self.assertFalse(await verified_run(self.agent, 'work', ['pytest'], 3))
            self.assertEqual(process.await_count, 2)
        suite = self.store.load(self.agent.state['id'])['verification_suite']
        self.assertEqual(suite['stop_reason'], 'repeated_failure_same_source')
        self.assertEqual(len(self.provider.contexts), 2)
        self.assertTrue(suite['rounds'][0]['checks'][0]['failure_signature'])

    async def test_regression_is_retained_and_all_checks_rerun(self):
        with patch('eca.tools.run_process', AsyncMock(side_effect=[OK, FAIL, FAIL, OK, OK])):
            self.assertTrue(await verified_run(self.agent, 'work', ['pytest', 'build'], 2))
        rounds = self.agent.state['verification_suite']['rounds']
        self.assertTrue(rounds[1]['checks'][0]['regression'])
        self.assertFalse(rounds[0]['checks'][1]['regression'])
        self.assertEqual(len(rounds[-1]['checks']), 2)

    async def test_same_diagnostics_on_changed_source_does_not_stop_early(self):
        count = 0
        async def command(*args, **kwargs):
            nonlocal count
            count += 1
            return FAIL if count < 3 else OK
        original_run = self.agent.run
        async def run(prompt):
            if count:
                (self.root / 'revision.py').write_text(str(count))
            await original_run(prompt)
        with patch.object(self.agent, 'run', run), patch('eca.tools.run_process', command):
            self.assertTrue(await verified_run(self.agent, 'work', ['pytest'], 3))
        self.assertEqual(count, 3)

    async def test_missing_fingerprint_does_not_claim_stagnation(self):
        with patch.object(self.agent.memory(), 'fingerprint', return_value=None), patch(
                'eca.tools.run_process', AsyncMock(return_value=FAIL)) as process:
            self.assertFalse(await verified_run(self.agent, 'work', ['pytest'], 2))
            self.assertEqual(process.await_count, 3)
        self.assertEqual(self.agent.state['verification_suite']['stop_reason'], 'repair_budget_exhausted')

    async def test_uncertain_or_denied_commands_never_repair(self):
        for output in ['Denied', json.dumps({'exit_code': 1, 'timed_out': True}),
                       json.dumps({'exit_code': -1, 'timed_out': False})]:
            with patch('eca.tools.run_process', AsyncMock(return_value=output)) as process:
                self.assertFalse(await verified_run(self.agent, 'work', ['pytest'], 3))
                process.assert_awaited_once()
        self.assertEqual(len(self.provider.contexts), 3)

    async def test_cancel_keeps_evidence_and_resume_never_replays(self):
        with patch('eca.tools.run_process', AsyncMock(side_effect=[OK, asyncio.CancelledError])) as process:
            with self.assertRaises(asyncio.CancelledError):
                await verified_run(self.agent, 'work', ['pytest', 'build'], 2)
            self.assertEqual(process.await_count, 2)
        restored = self.store.load(self.agent.state['id'])
        self.assertEqual(restored['verification_suite']['status'], 'interrupted')
        self.assertEqual(len(restored['verification_suite']['rounds'][0]['checks']), 1)
        self.assertEqual(restored['messages'][-1]['role'], 'tool')

    async def test_incomplete_model_does_not_run_checks(self):
        self.agent.settings.max_turns = 0
        with patch('eca.tools.run_process', AsyncMock(return_value=OK)) as process:
            self.assertFalse(await verified_run(self.agent, 'work', ['pytest'], 1))
            process.assert_not_awaited()
        self.assertEqual(suite_status(self.agent)['status'], 'task_incomplete')

    async def test_suite_fails_when_snapshot_changes_between_checks(self):
        # Each check can pass independently against a different source revision.
        with patch('eca.tools.run_process', AsyncMock(return_value=OK)), patch.object(
                self.agent.memory(), 'fingerprint', side_effect=['a', 'a', 'a', 'b', 'b', 'a']):
            self.assertFalse(await verified_run(self.agent, 'work', ['pytest', 'build'], 1))
        self.assertEqual(suite_status(self.agent)['status'], 'unconfirmed_snapshot')
        self.assertEqual(len(self.provider.contexts), 1)

    async def test_invalid_flags_fail_before_model(self):
        for flags in [['--repair-attempts', '1'], ['--repair-attempts', '-1'],
                      ['--repair-attempts', '4'], ['--verify-command', 'pytest', '--doctor']]:
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                await async_main(parser().parse_args(['-p', 'work', '--allow-shell', *flags]))

    async def test_plan_repair_refused_before_any_model_call(self):
        self.agent.settings.mode = 'plan'
        with self.assertRaises(ValueError):
            await verified_run(self.agent, 'work', ['pytest'], 1)
        self.assertEqual(self.provider.contexts, [])
