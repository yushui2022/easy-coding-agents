import asyncio
import os
from pathlib import Path
import tempfile
import unittest

from eca.impact import inspect_change, guidance
from eca.agent import Agent
from eca.config import Settings
from eca.store import Store
from test_runtime import FakeProvider, call, yes


class ImpactTests(unittest.IsolatedAsyncioTestCase):
    def test_transaction_modes_aliases_and_public_consumers(self):
        old = 'import sqlite3 as sql\ndef connect(path):\n    return sql.connect(path)\n'
        new = old.replace('sql.connect(path)', 'sql.connect(path, isolation_level=None)')
        result = inspect_change('shop/db.py', old, new)
        self.assertEqual(result['symbols'], ['connect'])
        self.assertIn('transaction_mode', result['risks'])
        old = 'from sqlite3 import connect as open_db\ndef db(path): return open_db(path)\n'
        self.assertIn('transaction_mode', inspect_change('db.py', old, old.replace('open_db(path)', 'open_db(path, autocommit=True)'))['risks'])
        old = 'import sqlite3\ndef db(path): return sqlite3.connect(path, 5, 0, "DEFERRED")\n'
        self.assertIn('transaction_mode', inspect_change('db.py', old, old.replace('"DEFERRED"', 'None'))['risks'])

    def test_comments_formatting_and_non_source_do_not_create_noise(self):
        old = 'def total(value): return value + 1\n'
        self.assertIsNone(inspect_change('total.py', old, '# comment\n'+old))
        self.assertIsNone(inspect_change('test_total.py', old, old.replace('+ 1', '+ 2')))
        self.assertIsNone(inspect_change('new.py', None, old))
        self.assertIsNone(inspect_change('huge.py', 'x'*256001, old))
        self.assertIsNone(inspect_change('broken.py', old, 'def'))
        self.assertEqual(inspect_change('total.py', old, None)['symbols'], ['total'])

    async def test_actual_write_hint_is_available_to_next_model_turn_and_persisted(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP')) as temp:
            root = Path(temp)
            old = 'import sqlite3\ndef connect(path): return sqlite3.connect(path)\n'
            (root/'db.py').write_text(old)
            store = Store(root)
            provider = FakeProvider([
                call('read', {'path':'db.py'}, 'read'),
                call('edit', {'path':'db.py', 'old':'sqlite3.connect(path)',
                              'new':'sqlite3.connect(path, isolation_level=None)'}, 'edit'),
                {'role':'assistant','content':'done'}])
            agent = Agent(Settings(root, project_memory=False, auto_compact=False),
                          store, store.create(), yes, yes, lambda *_:None, provider)
            try:
                await agent.run('Update the connection')
                self.assertIn('duplicate/invalid writes', str(provider.contexts[-1]))
                self.assertIn('rollback', guidance(agent.state['change_impact']))
                restored = store.peek(agent.state['id'])
                self.assertIn('transaction_mode', restored['change_impact'][0]['risks'])
                self.assertEqual(restored['status'], 'idle')
            finally:
                await agent.close()
                store.close()
