import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from eca.agent import Agent
from eca.config import Settings
from eca.recovery import inspect_resume
from eca.store import Store
from test_runtime import FakeProvider, yes

DONE = {'role': 'assistant', 'content': 'Review complete; no actions replayed.'}


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name)
        self.store = Store(self.root)
        self.state = self.store.create()
        self.settings = Settings(self.root, project_memory=False, auto_compact=False)
        self.agent = Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None, FakeProvider([DONE]))

    async def asyncTearDown(self):
        await self.agent.close()
        self.store.close()
        self.tmp.cleanup()

    async def test_changed_missing_unreadable_files_and_stale_verification(self):
        for name in ['changed.py', 'missing.py', 'same.py']:
            path = self.root / name
            path.write_bytes(b'original')
            self.agent.tools.remember_file(path, b'original')
        fingerprint = self.agent.memory().fingerprint()
        self.state['verification'] = dict(status='passed', fingerprint=fingerprint)
        self.state['verification_suite'] = dict(status='passed', fingerprint=fingerprint)
        (self.root / 'changed.py').write_bytes(b'user change')
        (self.root / 'missing.py').unlink()
        self.state['file_versions']['.env'] = 'not a hash'
        self.state['file_versions']['../outside.txt'] = 'not a hash'
        self.state['file_versions']['large.py'] = 'not a hash'
        (self.root / 'large.py').write_bytes(b'x' * (1024 * 1024 + 1))
        report = inspect_resume(self.agent)
        self.assertEqual(report['files'], dict(changed=1, missing=1, matching=1, unverified=3))
        self.assertEqual(report['verification'], 'stale')
        self.assertEqual(report['verification_suite'], 'stale')
        self.assertNotIn('user change', json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'changed since'):
            self.agent.tools.check_file_version(self.root/'changed.py', b'user change')

    async def test_timeout_checkpoint_survives_reopen_and_no_automatic_tools(self):
        self.state['tasks'] = [dict(content='Migrate database', status='in_progress')]
        self.agent.provider = FakeProvider([TimeoutError('private provider body')])
        with self.assertRaises(TimeoutError):
            await self.agent.run('Keep old orders and migrate schema')
        checkpoint = self.store.peek(self.state['id'])['checkpoint']
        self.assertEqual(checkpoint['original_request_excerpt'], 'Keep old orders and migrate schema')
        self.assertEqual(checkpoint['tasks'][0]['status'], 'in_progress')
        self.assertNotIn('private provider body', json.dumps(checkpoint))
        restored = self.store.load(self.state['id'])
        await self.agent.close()
        self.agent = Agent(self.settings, self.store, restored, yes, yes, lambda *_: None, FakeProvider([DONE]))
        with patch.object(self.agent.tools, 'execute', AsyncMock(side_effect=AssertionError('no replay'))) as execute:
            await self.agent.run('Continue')
            execute.assert_not_called()
        self.assertIn('Recovery inspection', str(self.agent.provider.contexts))
        self.assertIn('Keep old orders', str(self.agent.provider.contexts))

    async def test_abrupt_process_exit_retains_unknown_action_and_effect(self):
        await self.agent.close()
        self.store.close()
        script = '''import os, sys
from pathlib import Path
from eca.store import Store
root=Path(sys.argv[1]); store=Store(root); state=store.create()
state['messages']=[{'role':'user','content':'Create marker once'},
 {'role':'assistant','content':None,'tool_calls':[{'id':'one','type':'function','function':{'name':'shell','arguments':'{}'}}]}]
state['status']='running'; store.save(state)
store.begin(state['id'],'one','shell',{'command':'marker operation'})
(root/'marker.txt').write_text('one effect',encoding='utf-8')
os._exit(17)
'''
        result = await asyncio.to_thread(subprocess.run, [sys.executable, '-B', '-c', script, str(self.root)],
                                        capture_output=True, timeout=30)
        self.store = Store(self.root)
        self.assertEqual(result.returncode, 17, result.stderr)
        state = self.store.load('latest')
        self.agent = Agent(self.settings, self.store, state, yes, yes, lambda *_: None, FakeProvider([DONE]))
        self.assertEqual(state['status'], 'interrupted')
        self.assertIn('outcome unknown', state['messages'][-1]['content'])
        with patch.object(self.agent.tools, 'execute', AsyncMock(side_effect=AssertionError('no replay'))) as execute:
            await self.agent.run('Continue after crash')
            execute.assert_not_called()
        self.assertEqual((self.root/'marker.txt').read_text(), 'one effect')
        self.assertEqual(state['resume_report']['uncertain_actions'][0]['tool'], 'shell')

    async def test_context_limit_preserves_checkpoint_and_recovers_after_budget_change(self):
        self.settings.context_chars = 1
        with self.assertRaises(ValueError):
            await self.agent.run('Complete the pending task without replaying completed effects')
        self.assertEqual(self.state['checkpoint']['status'], 'error')
        self.settings.context_chars = 100000
        await self.agent.run('Continue with the corrected context budget')
        self.assertEqual(self.state['status'], 'idle')
        self.assertIn('Complete the pending task', str(self.agent.provider.contexts))
        self.assertIn('resume_report', self.state)
