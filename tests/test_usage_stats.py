import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from eca.store import Store
from eca.usage import UsageLedger


class UsageStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.ledger = UsageLedger(self.store)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def row(self, ident, tokens, model='m', age_days=0):
        created = time.time() - age_days * 86400
        self.ledger.db.execute(
            "INSERT INTO usage_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (ident, 'session', 'session', model, 'openai', 'chat', 'ok', created, '{}', '{}',
             json.dumps(tokens) if tokens is not None else 'null', None))

    def test_empty_ledger_is_all_zero(self):
        stats = self.ledger.statistics()
        self.assertEqual((stats['total_tokens'], stats['requests'], stats['active_days']), (0, 0, 0))
        self.assertIsNone(stats['peak'])
        self.assertEqual(stats['days'], [])

    def test_totals_peak_and_models(self):
        self.row(1, {'input': 100, 'output': 20}, model='alpha', age_days=2)
        self.row(2, {'input': 10, 'output': 5}, model='alpha', age_days=2)
        self.row(3, {'input': 7}, model='beta', age_days=0)
        stats = self.ledger.statistics()
        self.assertEqual(stats['total_tokens'], 142)
        self.assertEqual(stats['requests'], 3)
        self.assertEqual(stats['active_days'], 2)
        self.assertEqual(stats['peak']['tokens'], 135)
        self.assertEqual([row['model'] for row in stats['models'][:2]], ['alpha', 'beta'])

    def test_streak_counts_consecutive_days_only(self):
        for ident, age in ((1, 0), (2, 1), (3, 2), (4, 5)):
            self.row(ident, {'input': 5}, age_days=age)
        stats = self.ledger.statistics()
        self.assertEqual(stats['current_streak'], 3)
        self.assertEqual(stats['longest_streak'], 3)

    def test_unreported_tokens_are_skipped_not_guessed(self):
        self.row(1, None)
        self.row(2, {'input': 4})
        stats = self.ledger.statistics()
        self.assertEqual(stats['requests'], 2)
        self.assertEqual(stats['total_tokens'], 4)

    def test_pending_requests_are_ignored(self):
        self.ledger.db.execute(
            "INSERT INTO usage_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ('pending', 'session', 'session', 'm', 'openai', 'chat', 'pending', time.time(), '{}', '{}', 'null', None))
        self.assertEqual(self.ledger.statistics()['requests'], 0)


if __name__ == '__main__':
    unittest.main()
