import json
import os
import tempfile
import unittest
from pathlib import Path

from eca.config import Settings
from eca.store import Store
from eca.tools import Tools


async def yes(*_):
    return True


class ShellLiveOutput(unittest.IsolatedAsyncioTestCase):
    """The shell tool reports progress so a long command never looks frozen."""

    def setUp(self):
        base = Path(os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.tmp.name).resolve()
        self.settings = Settings(self.root)
        self.store = Store(self.root)
        self.state = self.store.create()
        self.seen = []
        self.tools = Tools(self.settings, self.state, yes, yes, lambda event, data: self.seen.append((event, data)))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    async def test_running_command_reports_its_tail(self):
        raw = await self.tools.shell("Write-Output 'first'; Start-Sleep -Milliseconds 1500; Write-Output 'second'", timeout=30)
        result = json.loads(raw)
        self.assertEqual(result['exit_code'], 0)
        self.assertIn('second', result['stdout'])
        progress = [data for event, data in self.seen if event == 'tool_progress']
        self.assertTrue(progress, f'no progress events; saw {[event for event, _ in self.seen]}')
        self.assertEqual(progress[0]['tool'], 'shell')
        self.assertIn('first', progress[-1]['tail'])

    async def test_progress_reports_stay_out_of_the_tool_result(self):
        raw = await self.tools.shell("Write-Output 'only-once'", timeout=30)
        result = json.loads(raw)
        self.assertEqual(result['stdout'].count('only-once'), 1)
        self.assertNotIn('tool_progress', raw)


if __name__ == '__main__':
    unittest.main()
