"""Evaluation harness checks, always offline; no Provider network calls."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest

from benchmark import agent_eval as evaluation
from benchmark.agent_cases import CASES, USER_CUSTOMIZATION, verify
from test_runtime import FakeProvider, call


FIXES = {
    'api': {'catalog.py': 'def item(): return {"name":"book","price_cents":1250}\n',
            'checkout.py': 'from catalog import item\ndef total(quantity): return item()["price_cents"]*quantity\n',
            'receipt.py': 'from catalog import item\ndef receipt(): return item()["name"] + ": " + str(item()["price_cents"]) + " cents"\n'},
    'user_edits': {'calculator.py': 'def increment(value): return value+1\n' + USER_CUSTOMIZATION},
    'tool_failure': {'slug.py': 'def slug(value): return "-".join(value.lower().split())\n'},
    'compact': {'policy.py': 'TOKEN="KEEP-042"\ndef enabled(value): return isinstance(value,str) and value.strip().lower()=="yes"\n'},
    'config': {'flags.py': '''def parse_flag(value):
    if type(value) is bool: return value
    if type(value) is int and value in (0,1): return bool(value)
    if isinstance(value,str):
        value=value.strip().lower()
        if value in ('yes','true','1'): return True
        if value in ('no','false','0'): return False
    raise ValueError('invalid flag')
'''},
}


class EvaluationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        base = Path(os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_oracles_reject_initial_state_accept_fixes_and_detect_test_deletion(self):
        for name, fixes in FIXES.items():
            root = self.root / name
            originals, _ = evaluation.fixture(name, root)
            checks, _ = verify(name, root, originals)
            self.assertFalse(all(checks.values()), name)
            for filename, content in fixes.items():
                (root / filename).write_bytes(content.encode())
            checks, _ = verify(name, root, originals)
            self.assertTrue(all(checks.values()), (name, checks))
            next(root.glob('test_*.py')).unlink()
            checks, _ = verify(name, root, originals)
            self.assertFalse(checks['original_tests_preserved'], name)

    async def test_full_offline_runner_counts_requests_and_verifies_actual_files(self):
        options = evaluation.parser().parse_args(['--model', 'fixture'])
        provider = FakeProvider([call('read', {'path': 'AGENTS.md'}, 'guidance'),
            call('read', {'path': 'stats.py'}, 'read'),
            call('write', {'path': 'stats.py', 'content': 'def mean(values):\n    if not values: raise ValueError()\n    return sum(values)/len(values)\n'}, 'fix'),
            call('shell', {'command': evaluation.TEST_COMMAND}, 'test'),
            {'role': 'assistant', 'content': 'done'}])
        result = await evaluation.run_case('bug', self.root / 'bug-01', options, 'offline-credential', lambda _: provider)
        self.assertTrue(result['passed'], result['checks'])
        self.assertEqual(result['usage']['requests'], 5)
        self.assertEqual(result['human_interventions'], 0)
        self.assertNotIn('offline-credential', json.dumps(result))

    async def test_provider_error_is_failure_not_success_or_raw_error_disclosure(self):
        options = evaluation.parser().parse_args(['--model', 'fixture'])
        provider = FakeProvider([RuntimeError('secret-provider-body')])
        result = await evaluation.run_case('bug', self.root / 'error-01', options, 'offline', lambda _: provider)
        self.assertFalse(result['passed'])
        self.assertEqual(result['error_type'], 'RuntimeError')
        self.assertNotIn('secret-provider-body', json.dumps(result))

    def test_aggregate_preserves_incomplete_runs_and_unknown_costs(self):
        result = dict(passed=True, usage=dict(requests=2, priced_subtotals={'USD':'0.01'}, incomplete_cost_requests=1))
        summary = evaluation.aggregate([result], 10)
        self.assertEqual(summary['incomplete'], 9)
        self.assertEqual(summary['passed'], 1)
        self.assertFalse(summary['cost_complete'])
        self.assertEqual(summary['priced_subtotals']['USD'], '0.01')
        self.assertFalse(evaluation.aggregate([], 10)['cost_complete'])

    def test_pairing_rejects_stray_duplicate_and_missing_results(self):
        assistant = call('read', {'path':'a'}, 'one')
        result = dict(role='tool', tool_call_id='one', content='ok')
        self.assertTrue(evaluation.paired([assistant, result]))
        for history in ([result], [assistant], [assistant, result, result], [assistant, assistant, result]):
            self.assertFalse(evaluation.paired(history))

    def test_ten_cases_source_fingerprint_and_empty_report(self):
        self.assertEqual(len(CASES), 14)
        snapshot = evaluation.source_snapshot()
        self.assertIn('eca/editing.py', snapshot['files'])
        self.assertNotIn('.env', snapshot['files'])
        manifest = dict(model='fixture', cases=list(CASES), repeats=1, source=snapshot)
        evaluation.report(self.root, manifest, [])
        result = json.loads((self.root / 'report.json').read_text('utf-8'))
        self.assertEqual(result['summary']['incomplete'], 14)
        self.assertIn('unknown', (self.root / 'report.md').read_text('utf-8'))
