import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from eca.code_index import CodeIndex
from eca.config import Settings
from eca.tools import Tools
from test_runtime import yes


class RelationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.tools = Tools(Settings(self.root), {}, yes, yes, lambda *_: None)
        self.index = CodeIndex(self.tools)

    def write(self, path, text):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding='utf-8')

    def query(self, query='submit', **kw):
        return json.loads(self.index.query(query, **kw))

    def git(self, *args):
        return subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', *args],
                              cwd=self.root, check=True, capture_output=True)

    def test_relations_distinguish_calls_imports_definitions_and_comments(self):
        self.write('service.py', 'def submit(): return 1\n')
        self.write('tests/test_service.py', 'from service import submit\ndef test_submit():\n    assert submit() == 1\n')
        self.write('notes.py', '# submit()\ntext = "submit()"\n')
        self.write('unrelated.py', 'other.submit()\n')
        result = self.query(related=True)
        self.assertEqual(result['results'][0]['path'], 'service.py')
        self.assertNotIn('notes.py', [r['path'] for r in result['results']])
        test = next(r for r in result['results'] if r['is_test'])
        self.assertEqual([(r['line'], r['kind']) for r in test['references']], [(1, 'import'), (3, 'call')])
        self.assertIn('same-name', result['notice'])
        self.assertIn('unrelated.py', [r['path'] for r in result['results']])

    def test_scope_is_directory_boundary_not_like_pattern(self):
        for folder in ('src', 'src2', 'src_'):
            self.write(folder + '/unit.py', 'def submit(): pass\n')
        for options in ({}, {'outline': True}, {'related': True}):
            self.assertEqual([r['path'] for r in self.query(path='src/', **options)['results']], ['src/unit.py'])
            self.assertEqual([r['path'] for r in self.query(path='src_', **options)['results']], ['src_/unit.py'])
        for path in ('../src', '/src', '/', 'C:/src', 'src/../src2'):
            with self.assertRaises(ValueError):
                self.query(path=path)

    def test_warm_cache_only_reads_returned_files_and_rename_removes_old_rows(self):
        for i in range(100):
            self.write(f'unit_{i}.py', f'def method_{i}(): pass\n')
        first = self.query('method_42', related=True)
        warm = self.query('method_42', related=True)
        self.assertEqual(first['index']['updated'], 100)
        self.assertEqual(warm['index']['updated'], 0)
        self.assertEqual(warm['index']['reused'], 100)
        self.assertEqual(warm['index']['files_read'], 1)
        (self.root/'unit_42.py').rename(self.root/'renamed.py')
        changed = self.query('method_42', related=True)
        self.assertEqual(changed['index']['removed'], 1)
        self.assertEqual(changed['results'][0]['path'], 'renamed.py')
        (self.root/'renamed.py').unlink()
        self.assertEqual(self.query('method_42', related=True)['results'], [])

    def test_branch_switch_removes_old_calls_without_reset(self):
        self.git('init', '-q')
        self.write('.gitignore', '.eca/\n')
        self.write('main.py', 'submit()\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'first')
        first = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        self.assertTrue(self.query(related=True)['results'])
        self.git('checkout', '-qb', 'next')
        self.write('main.py', 'cancel()\n')
        self.git('commit', '-qam', 'second')
        self.assertEqual(self.query(related=True)['results'], [])
        self.assertTrue(self.query('cancel', related=True)['results'])
        self.git('checkout', '-q', first)
        self.assertTrue(self.query(related=True)['results'])
        self.assertEqual(self.query('cancel', related=True)['results'], [])

    def test_invalid_python_replaces_stale_relations(self):
        self.write('main.py', 'submit()\n')
        self.assertTrue(self.query(related=True)['results'])
        self.write('main.py', 'submit(\n')
        self.assertEqual(self.query(related=True)['results'], [])

    def test_syntax_failure_is_visible_and_preserves_lexical_definition(self):
        self.write('future.py', 'def submit[T](value: T) -> T:\n    return value\n')
        result = self.query(related=True)
        self.assertEqual(result['results'][0]['path'], 'future.py')
        if result['results'][0]['parse_status'] == 'syntax_error':
            self.assertEqual(result['index']['syntax_fallback_files'], 1)
            self.assertEqual(result['results'][0]['matched_symbols'][0]['kind'], 'lexical')

    def test_relation_caps_are_visible(self):
        self.write('many.py', 'submit()\n' * 1001)
        result = self.query(related=True)
        self.assertTrue(result['results'][0]['structure_truncated'])
        self.assertTrue(result['results'][0]['references_truncated'])
        self.assertEqual(len(result['results'][0]['references']), 20)

