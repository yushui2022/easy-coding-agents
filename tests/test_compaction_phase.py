import unittest

from eca.desktop_rpc import DesktopRPC


class CompactionPhase(unittest.TestCase):
    """Compaction must stay visible even though it is a model call.

    Request events normally report 'waiting_model'. A summarisation request is
    reported as 'compacting' instead, because the transcript legitimately shows
    nothing new while it streams.
    """

    def setUp(self):
        self.rpc = DesktopRPC(lambda value: None)

    def start(self, ident):
        self.rpc.emit('request_start', {'id': ident})

    def end(self, ident):
        self.rpc.emit('request_end', {'id': ident, 'usage': {}, 'status': 'ok', 'elapsed_ms': 1})

    def test_summarisation_request_reports_compaction(self):
        self.rpc.emit('compacting', {'older_messages': 12})
        self.start('summary')
        self.assertEqual(self.rpc.activity['phase'], 'compacting')

    def test_phase_returns_to_model_wait_after_compaction(self):
        self.rpc.emit('compacting', {'older_messages': 12})
        self.start('summary')
        self.end('summary')
        self.assertFalse(self.rpc.compacting)
        self.start('answer')
        self.assertEqual(self.rpc.activity['phase'], 'waiting_model')

    def test_ordinary_requests_are_never_labelled_as_compaction(self):
        self.start('answer')
        self.assertEqual(self.rpc.activity['phase'], 'waiting_model')

    def test_compaction_does_not_reach_the_transcript_stream(self):
        # The summary is internal work: it must not be appended to live output.
        self.rpc.emit('compacting', {'older_messages': 3})
        self.assertEqual(self.rpc.stream, '')


if __name__ == '__main__':
    unittest.main()
