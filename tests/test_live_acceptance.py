"""Validate the acceptance oracle offline; these tests never instantiate Provider."""
import importlib.util
import os
from pathlib import Path
import tempfile

spec = importlib.util.spec_from_file_location('live_acceptance', Path(__file__).resolve().parents[1]/'benchmark/live_acceptance.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


def test_broken_fixtures_fail_and_fixed_fixtures_pass():
    base = Path(os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
    base.mkdir(parents=True, exist_ok=True)
    for name in ['bug', 'refactor', 'parallel', 'resume']:
        with tempfile.TemporaryDirectory(dir=base) as directory:
            root = Path(directory)
            originals, _ = live.CASES[name]
            for filename, content in originals.items():
                (root/filename).write_text(content, encoding='utf-8')
            checks, _ = live.verify(name, root, originals)
            assert not all(checks.values()), name
            fixes = {
                'bug': {'stats.py':'def mean(values):\n    if not values: raise ValueError()\n    return sum(values)/len(values)\n'},
                'refactor': {'text_utils.py':originals.get('names.py',''), 'greeting.py':'from text_utils import normalize_name\ndef greet(value): return "hello " + normalize_name(value)\n'},
                'parallel': {'numbers.py':'def double(x): return 2*x\n', 'labels.py':'def label(text): return text.strip().upper()\n'},
                'resume': {'left.py':'def left(): return "left"\n', 'right.py':'def right(): return "right"\n'},
            }
            for filename, content in fixes[name].items():
                (root/filename).write_text(content, encoding='utf-8')
            if name == 'refactor': (root/'names.py').unlink()
            checks, _ = live.verify(name, root, originals)
            assert all(checks.values()), (name, checks)
            testfile = next(root.glob('test_*.py'))
            testfile.unlink()
            checks, _ = live.verify(name, root, originals)
            assert not checks['original_tests_preserved']


def test_test_generation_oracle_requires_tests_that_catch_a_mutant():
    base = Path(os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        root = Path(directory)
        originals, _ = live.CASES['tests']
        (root/'clamp.py').write_bytes(originals['clamp.py'].encode())
        checks, _ = live.verify('tests', root, originals)
        assert not all(checks.values())
        (root/'test_clamp.py').write_text(live.tests(
            'from clamp import clamp\nclass Tests(unittest.TestCase):\n'
            '    def test_below(self): self.assertEqual(clamp(-1,0,2),0)\n'
            '    def test_above(self): self.assertEqual(clamp(3,0,2),2)\n'
            '    def test_inside(self): self.assertEqual(clamp(1,0,2),1)\n'
            '    def test_equal(self): self.assertEqual(clamp(1,2,2),2)\n'
            '    def test_reversed(self):\n        with self.assertRaises(ValueError): clamp(1,3,2)\n'),encoding='utf-8')
        checks, _ = live.verify('tests', root, originals)
        assert all(checks.values()), checks
        assert (root/'clamp.py').read_bytes() == originals['clamp.py'].encode()
