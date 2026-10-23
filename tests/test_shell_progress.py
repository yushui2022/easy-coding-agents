import asyncio
import json
import sys
import unittest

from eca.tools import run_process

PY = [sys.executable, '-c']


class ShellProgress(unittest.IsolatedAsyncioTestCase):
    """A long command must show signs of life instead of looking frozen."""

    async def test_output_is_reported_while_the_command_runs(self):
        seen = []
        script = "import time,sys\nfor i in range(5):\n print('line',i); sys.stdout.flush(); time.sleep(.3)\n"
        raw = await run_process(PY + [script], '.', timeout=30, on_progress=lambda stream, tail: seen.append((stream, tail)))
        result = json.loads(raw)
        self.assertEqual(result['exit_code'], 0)
        self.assertGreaterEqual(len(seen), 2, seen)
        self.assertEqual(seen[-1][0], 'stdout')
        self.assertIn('line', seen[-1][1])
        # Later reports must supersede earlier ones rather than repeat them.
        self.assertGreater(len(seen[-1][1]), len(seen[0][1]))

    async def test_a_quiet_command_reports_nothing(self):
        seen = []
        await run_process(PY + ["print('done')"], '.', timeout=30, on_progress=lambda stream, tail: seen.append(tail))
        self.assertEqual(seen, [])

    async def test_timeout_keeps_what_was_already_printed(self):
        script = "import time,sys\nprint('started'); sys.stdout.flush(); time.sleep(30)\n"
        raw = await run_process(PY + [script], '.', timeout=1)
        result = json.loads(raw)
        self.assertTrue(result['timed_out'])
        self.assertIn('started', result['stdout'])

    async def test_child_cannot_read_the_protocol_pipe(self):
        # stdin is closed, so a command that reads it gets EOF immediately
        # instead of hanging until the timeout (or eating JSON-RPC input).
        script = "import sys; print('stdin=' + repr(sys.stdin.read()))"
        raw = await run_process(PY + [script], '.', timeout=10)
        result = json.loads(raw)
        self.assertEqual(result['exit_code'], 0)
        self.assertIn("stdin=''", result['stdout'])

    async def test_progress_never_reaches_the_returned_output(self):
        script = "import time,sys\nfor i in range(3):\n print('x'); sys.stdout.flush(); time.sleep(.6)\n"
        raw = await run_process(PY + [script], '.', timeout=30, on_progress=lambda *_: None)
        self.assertEqual(json.loads(raw)['stdout'].count('x'), 3)


if __name__ == '__main__':
    unittest.main()
