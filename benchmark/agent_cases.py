"""Versioned, small coding tasks and external acceptance oracles."""
from pathlib import Path
import sys

from . import live_acceptance as live
from . import project_cases


CASES = dict(live.CASES)
CASES.update({
    'api': ({
        'catalog.py': 'def item(): return {"name": "book", "price": 12.5}\n',
        'checkout.py': 'from catalog import item\ndef total(quantity): return item()["price"] * quantity\n',
        'receipt.py': 'from catalog import item\ndef receipt(): return item()["name"] + ": " + str(item()["price"])\n',
        'test_api.py': live.tests('from checkout import total\nfrom receipt import receipt\nclass Tests(unittest.TestCase):\n'
            '    def test_total(self): self.assertEqual(total(2), 2500)\n'
            '    def test_receipt(self): self.assertEqual(receipt(), "book: 1250 cents")\n')},
        'Migrate catalog.item from float price to integer price_cents (1250), remove price. Update checkout.total to return cents and receipt.receipt to return "book: 1250 cents". Preserve tests and run them.'),
    'user_edits': ({
        'calculator.py': 'def increment(value): return value\n',
        'test_calculator.py': live.tests('from calculator import increment\nclass Tests(unittest.TestCase):\n'
            '    def test_increment(self): self.assertEqual(increment(2), 3)\n')},
        'Fix calculator.increment to add exactly one. Preserve all existing user customization, notes and Git index. Run tests.'),
    'tool_failure': ({
        'slug.py': 'def slug(value): return value\n',
        'test_slug.py': live.tests('from slug import slug\nclass Tests(unittest.TestCase):\n'
            '    def test_slug(self): self.assertEqual(slug("  A   B "), "a-b")\n')},
        'Read slug.py then fix slug: strip surrounding whitespace, lowercase and join whitespace-separated words with hyphens. An initial read may report a transient error; retry or inspect before editing. Run tests.'),
    'compact': ({
        'policy.py': 'TOKEN = "KEEP-042"\ndef enabled(value): return False\n',
        'test_policy.py': live.tests('from policy import TOKEN, enabled\nclass Tests(unittest.TestCase):\n'
            '    def test_enabled(self): self.assertTrue(enabled("yes"))\n'
            '    def test_token(self): self.assertEqual(TOKEN, "KEEP-042")\n')},
        'Continue the earlier policy.py task. Follow its original constraints and verify the resulting implementation.'),
    'config': ({
        'flags.py': 'def parse_flag(value): return bool(value)\n',
        'test_flags.py': live.tests('from flags import parse_flag\nclass Tests(unittest.TestCase):\n'
            '    def test_false(self): self.assertFalse(parse_flag(" false "))\n'
            '    def test_true(self): self.assertTrue(parse_flag("YES"))\n'
            '    def test_invalid(self):\n        with self.assertRaises(ValueError): parse_flag("maybe")\n')},
        'Implement flags.parse_flag: accept booleans unchanged, integer 0/1, and case-insensitive trimmed strings true/false/yes/no/1/0. All other values including floats, None and other integers raise ValueError. Preserve tests and run them.'),
})

USER_CUSTOMIZATION = '\n# user customization: keep this exact helper\ndef audit_label(): return "USER-OWNED"\n'
USER_NOTES = 'Untracked user notes: preserve exactly.\n'
COMPACT_GOAL = ('Update policy.enabled to return True only for strings whose trimmed lowercase form is yes; '
                'return False for all other values. Preserve TOKEN exactly as KEEP-042. Do not rename any public function. Run tests.')
ASSERTIONS = {
    'api': 'from catalog import item; from checkout import total; from receipt import receipt; '
           'assert item()=={"name":"book","price_cents":1250}; assert type(item()["price_cents"]) is int; '
           'assert total(0)==0 and total(3)==3750; assert receipt()=="book: 1250 cents"',
    'user_edits': 'from calculator import increment,audit_label; assert increment(-1)==0; assert increment(0)==1; assert audit_label()=="USER-OWNED"',
    'tool_failure': 'from slug import slug; assert slug("A\\tB\\nC")=="a-b-c"; assert slug("")==""; assert slug(" 中文 X ")=="中文-x"',
    'compact': 'from policy import TOKEN,enabled; assert TOKEN=="KEEP-042"; assert enabled(" YES ") is True; '
               'assert all(enabled(x) is False for x in [None,1,True,"no","",[],"yesterday"])',
    'config': '''from flags import parse_flag
for value in [True,1,"yes"," TRUE ","1"]: assert parse_flag(value) is True
for value in [False,0,"no"," FALSE ","0"]: assert parse_flag(value) is False
for value in [None,2,-1,1.0,0.0,[],"maybe",""]:
    try: parse_flag(value)
    except ValueError: pass
    else: raise AssertionError(repr(value))
''',
}
CASES.update(project_cases.CASES)
ASSERTIONS.update(project_cases.ASSERTIONS)


def verify(name: str, root: Path, originals: dict) -> tuple[dict, str]:
    if name in live.CASES:
        return live.verify(name, root, originals)
    result = live.command([sys.executable, '-B', '-m', 'unittest', 'discover', '-v'], root)
    external = live.command([sys.executable, '-B', '-c', ASSERTIONS[name]], root)
    checks = dict(unittest_exit_zero=result.returncode == 0, external_assertions=external.returncode == 0,
                  original_tests_preserved=all((root / p).is_file() and (root / p).read_bytes() == text.encode()
                                               for p, text in originals.items() if p.startswith('test_')))
    if name == 'user_edits':
        checks['customization_preserved'] = USER_CUSTOMIZATION.encode() in (root / 'calculator.py').read_bytes()
        checks['notes_preserved'] = (root / 'notes.txt').is_file() and (root / 'notes.txt').read_bytes() == USER_NOTES.encode()
    return checks, (result.stdout + result.stderr + external.stdout + external.stderr)[-6000:]
