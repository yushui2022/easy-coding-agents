"""Offline contract and repair-loop integration checks."""
import unittest

from benchmark import agent_eval as evaluation
from benchmark.agent_cases import verify
from benchmark.project_cases import COMMON, CASES
import test_agent_eval
from test_runtime import FakeProvider, call


IDEMPOTENCY = '''    old = db.execute("SELECT sku,qty FROM orders WHERE id=?", (ident,)).fetchone()
    if old is not None:
        if old != (sku, quantity): raise ValueError('conflict')
        return ident
'''
CANCEL = '''def cancel(db, ident):
    with db:
        row = db.execute("SELECT sku,qty,status FROM orders WHERE id=?", (ident,)).fetchone()
        if row is None: raise ValueError('missing')
        if row[2] == 'cancelled': return
        db.execute("UPDATE products SET stock=stock+? WHERE sku=?", (row[1],row[0]))
        db.execute("UPDATE orders SET status='cancelled' WHERE id=?", (ident,))
'''
BATCH = '''
def place_many(db, items):
    ids = []
    with db:
        for item in items:
            ident, sku, qty = item['id'], item['sku'], item['quantity']
            if type(qty) is not int or qty <= 0: raise ValueError('quantity')
            changed = db.execute("UPDATE products SET stock=stock-? WHERE sku=? AND stock>=?", (qty,sku,qty))
            if changed.rowcount != 1: raise ValueError('stock')
            db.execute("INSERT INTO orders VALUES (?,?,?,'open')", (ident,sku,qty))
            ids.append(ident)
    return ids
'''


class ProjectEvaluationTests(unittest.IsolatedAsyncioTestCase):
    setUp = test_agent_eval.EvaluationTests.setUp
    tearDown = test_agent_eval.EvaluationTests.tearDown
    def test_project_oracles(self):
        for name in CASES:
            root = self.root / name
            originals, _ = evaluation.fixture(name, root)
            checks, _ = verify(name, root, originals)
            self.assertFalse(checks['external_assertions'], name)
            code = COMMON['shop/orders.py']
            if name == 'shop_migration':
                db_code = '''import sqlite3
def connect(path):
    db = sqlite3.connect(path)
    try:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > 1: raise ValueError('future version')
        with db:
            db.execute('BEGIN')
            db.execute('CREATE TABLE IF NOT EXISTS products (sku TEXT PRIMARY KEY, stock INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, sku TEXT, qty INTEGER, status TEXT)')
            if version == 0:
                db.execute('ALTER TABLE products ADD COLUMN reserved INTEGER NOT NULL DEFAULT 0')
                db.execute('PRAGMA user_version=1')
        return db
    except BaseException:
        db.close()
        raise
'''
                (root / 'shop/db.py').write_text(db_code, encoding='utf-8')
                (root / 'shop/catalog.py').write_text(COMMON['shop/catalog.py'].replace('INSERT INTO products VALUES', 'INSERT INTO products (sku,stock) VALUES') + '\ndef available(db, sku):\n    row=db.execute("SELECT stock,reserved FROM products WHERE sku=?", (sku,)).fetchone()\n    return row[0]-row[1]\n', encoding='utf-8')
                api = COMMON['shop/api.py'].replace('import stock', 'import stock, available').replace("    if action == 'place':", "    if action == 'available': return {'available': available(db, body['sku'])}\n    if action == 'place':")
                (root / 'shop/api.py').write_text(api, encoding='utf-8')
            elif name == 'shop_idempotency':
                code = code.replace('    with db:', IDEMPOTENCY + '    with db:', 1)
            elif name == 'shop_cancel':
                code = code[:code.index('def cancel')] + CANCEL
            else:
                code += BATCH
                api = COMMON['shop/api.py'].replace('import place, cancel', 'import place, cancel, place_many')
                api = api.replace("    if action == 'place':", "    if action == 'batch': return {'ids': place_many(db, body)}\n    if action == 'place':")
                (root / 'shop/api.py').write_text(api, encoding='utf-8')
            (root / 'shop/orders.py').write_text(code, encoding='utf-8')
            checks, output = verify(name, root, originals)
            self.assertTrue(all(checks.values()), (name, checks, output))
            if name == 'shop_migration':
                # A successful migration can silently break the transaction
                # behavior of callers that use `with db:` for rollback.
                (root / 'shop/db.py').write_text(db_code.replace(
                    'sqlite3.connect(path)', 'sqlite3.connect(path, isolation_level=None)'), encoding='utf-8')
                checks, output = verify(name, root, originals)
                self.assertFalse(checks['external_assertions'])
                self.assertIn('rejected duplicate order consumed stock', output)
                (root / 'shop/db.py').write_text(db_code.replace(
                    "            db.execute('BEGIN')\n", ''), encoding='utf-8')
                checks, output = verify(name, root, originals)
                self.assertFalse(checks['external_assertions'])
                self.assertIn('failed migration left partial schema changes', output)
                (root / 'shop/db.py').write_text(db_code, encoding='utf-8')
            # Weakened public tests cannot hide acceptance failures.
            (root / 'test_shop.py').write_text('', encoding='utf-8')
            checks, _ = verify(name, root, originals)
            self.assertFalse(checks['original_tests_preserved'])

    async def test_real_workflow_preserves_first_failure_then_repairs(self):
        options = evaluation.parser().parse_args(['--model','fixture','--verify','--repair-attempts','1'])
        provider = FakeProvider([
            {'role':'assistant','content':'done without fixing'},
            call('read', {'path':'AGENTS.md'}, 'guidance'),
            call('read', {'path':'stats.py'}, 'read'),
            call('write', {'path':'stats.py','content':'def mean(values):\n    if not values: raise ValueError()\n    return sum(values)/len(values)\n'}, 'fix'),
            {'role':'assistant','content':'fixed'},
        ])
        result = await evaluation.run_case('bug', self.root / 'repair', options, 'offline', lambda _: provider)
        self.assertTrue(result['passed'], result)
        self.assertFalse(result['first_verification_passed'])
        self.assertEqual(result['repair_rounds'], 1)
        self.assertEqual([r['status'] for r in result['verification']['rounds']], ['failed','passed'])
        self.assertEqual(result['human_interventions'], 0)

    async def test_zero_budget_keeps_failure(self):
        options = evaluation.parser().parse_args(['--model','fixture','--verify'])
        provider = FakeProvider([{'role':'assistant','content':'done'}])
        result = await evaluation.run_case('bug', self.root / 'no-repair', options, 'offline', lambda _: provider)
        self.assertFalse(result['passed'])
        self.assertEqual(result['repair_rounds'], 0)
        self.assertEqual(result['verification']['status'], 'failed')
