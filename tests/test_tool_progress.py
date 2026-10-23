import unittest

from eca.desktop_rpc import DesktopRPC


class ToolProgress(unittest.TestCase):
    """A running command's tail is for the screen, not for the model."""

    def setUp(self):
        self.rpc = DesktopRPC(lambda value: None)

    def test_tail_lands_on_the_activity_without_changing_the_phase(self):
        self.rpc.emit('tool', {'name': 'shell', 'args': {'command': 'npm test'}})
        self.rpc.emit('tool_progress', {'tool': 'shell', 'stream': 'stdout', 'tail': 'running 12 tests'})
        self.assertEqual(self.rpc.activity['phase'], 'executing')
        self.assertEqual(self.rpc.activity['tool'], 'shell')
        self.assertEqual(self.rpc.activity['output'], 'running 12 tests')
        self.assertEqual(self.rpc.activity['output_stream'], 'stdout')

    def test_tail_never_becomes_a_transcript_event(self):
        before = len(self.rpc.events)
        self.rpc.emit('tool', {'name': 'shell', 'args': {'command': 'npm test'}})
        mid = len(self.rpc.events)
        self.rpc.emit('tool_progress', {'tool': 'shell', 'stream': 'stdout', 'tail': 'line 1'})
        self.assertEqual(len(self.rpc.events), mid, 'progress must not be recorded as an event')
        self.assertGreaterEqual(mid, before)

    def test_tail_never_reaches_the_live_stream(self):
        self.rpc.emit('tool_progress', {'tool': 'shell', 'stream': 'stdout', 'tail': 'secret partial line'})
        self.assertEqual(self.rpc.stream, '')

    def test_result_clears_the_tail(self):
        self.rpc.emit('tool', {'name': 'shell', 'args': {'command': 'npm test'}})
        self.rpc.emit('tool_progress', {'tool': 'shell', 'stream': 'stdout', 'tail': 'line 1'})
        self.rpc.emit('result', {'content': '{}'})
        self.assertNotIn('output', self.rpc.activity)


if __name__ == '__main__':
    unittest.main()
