"""Multi-module SQLite maintenance fixtures; external checks stay outside workspaces."""
COMMON = {
    'shop/__init__.py': '',
    'shop/db.py': '''import sqlite3
def connect(path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS products (sku TEXT PRIMARY KEY, stock INTEGER NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, sku TEXT, qty INTEGER, status TEXT)")
    db.commit()
    return db
''',
    'shop/catalog.py': '''def stock(db, sku):
    return db.execute("SELECT stock FROM products WHERE sku=?", (sku,)).fetchone()[0]
def seed(db, sku, quantity):
    with db:
        db.execute("INSERT INTO products VALUES (?,?)", (sku, quantity))
''',
    'shop/orders.py': '''def place(db, ident, sku, quantity):
    if type(quantity) is not int or quantity <= 0: raise ValueError('quantity')
    with db:
        row = db.execute("SELECT stock FROM products WHERE sku=?", (sku,)).fetchone()
        if row is None or row[0] < quantity: raise ValueError('stock')
        db.execute("UPDATE products SET stock=stock-? WHERE sku=?", (quantity, sku))
        db.execute("INSERT INTO orders VALUES (?,?,?,'open')", (ident, sku, quantity))
    return ident
def cancel(db, ident):
    with db:
        db.execute("UPDATE orders SET status='cancelled' WHERE id=?", (ident,))
''',
    'shop/api.py': '''from .orders import place, cancel
from .catalog import stock
def dispatch(db, action, body):
    if action == 'place': return {'id': place(db, body['id'], body['sku'], body['quantity'])}
    if action == 'cancel':
        cancel(db, body['id'])
        return {'ok': True}
    if action == 'stock': return {'stock': stock(db, body['sku'])}
    raise ValueError('action')
''',
    'test_shop.py': '''import unittest
from shop.db import connect
from shop.catalog import seed, stock
from shop.api import dispatch
class ShopTests(unittest.TestCase):
    def test_purchase(self):
        db = connect(':memory:')
        try:
            seed(db, 'book', 10)
            self.assertEqual(dispatch(db, 'place', {'id':'a','sku':'book','quantity':2}), {'id':'a'})
            self.assertEqual(stock(db, 'book'), 8)
        finally: db.close()
''',
    'README.md': 'Shop maintenance fixture. Standard-library SQLite; use shop.api.dispatch as the application boundary.\n',
}

TASKS = {
    'shop_migration': 'Upgrade shop.db.connect to schema version 1 using PRAGMA user_version. Both new and legacy databases must have products.reserved INTEGER NOT NULL DEFAULT 0. Legacy databases have the current products/orders schemas and user_version=0. Migrate atomically without deleting or rebuilding user data; preserve existing products, stocks and orders. Repeated connect must be safe and keep existing reserved values. Add catalog.available(db, sku) returning stock minus reserved, and dispatch(db, "available", {"sku": ...}) returning {"available": integer}. Preserve stock and purchase API behavior. Do not automatically modify or downgrade databases with user_version greater than 1; raise ValueError instead.',
    'shop_idempotency': 'Make place idempotent by order id. An identical retry returns the same id without reducing stock again, including after database reopen. Reusing an id with different sku or quantity raises ValueError with no changes. Keep strict positive integer quantities, insufficient-stock rejection, public interfaces and existing tests.',
    'shop_cancel': 'Implement cancellation: an open order restores its quantity exactly once and becomes cancelled; repeated cancellation changes nothing. Unknown ids raise ValueError. Preserve purchase validation and public interfaces. Cancellation must survive database reopen. Keep existing tests.',
    'shop_batch': 'Add shop.orders.place_many(db, items) returning a list of ids, and dispatch(db, "batch", items) returning {"ids": [...]} in input order. The dispatch body IS the items list itself, not a dict wrapping items. Each item has id, sku, quantity. The entire batch commits atomically or leaves no changes when any item fails, including duplicate ids, invalid quantities, missing products and insufficient stock. place_many(db, []) returns []; dispatch(db, "batch", []) returns {"ids": []}. Preserve existing single purchase behavior and tests.',
}
CASES = {name: (dict(COMMON), task + ' Keep every existing test file byte-for-byte unchanged, including imports and formatting. Add regression tests in NEW test_*.py files only, then run the complete test suite.')
         for name, task in TASKS.items()}

PRELUDE = '''import tempfile
from pathlib import Path
from shop.db import connect
from shop.catalog import seed, stock
from shop.api import dispatch
def buy(db, ident='a', sku='book', quantity=2):
    return dispatch(db, 'place', dict(id=ident, sku=sku, quantity=quantity))
def rejected(fn):
    try: fn()
    except (ValueError, __import__('sqlite3').IntegrityError): pass
    else: raise AssertionError('expected rejection')
with tempfile.TemporaryDirectory() as folder:
    path = str(Path(folder) / 'shop.sqlite')
    db = connect(path)
    seed(db, 'book', 10)
    seed(db, 'pen', 5)
    try:
        for invalid in [True, 0, -1, 1.5]:
            rejected(lambda: buy(db, ident='invalid', quantity=invalid))
        rejected(lambda: buy(db, ident='overdraw', quantity=100))
        rejected(lambda: buy(db, ident='unknown', sku='missing'))
        assert stock(db,'book')==10
        assert db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==0
        CASE
    finally: db.close()
'''
CHECKS = {
    'shop_migration': '''import sqlite3
from shop.catalog import available
assert db.execute('PRAGMA user_version').fetchone()[0]==1
assert available(db,'book')==10
assert dispatch(db,'available',{'sku':'book'})=={'available':10}
legacy = str(Path(folder)/'legacy.sqlite')
old = sqlite3.connect(legacy)
old.executescript("CREATE TABLE products (sku TEXT PRIMARY KEY, stock INTEGER NOT NULL); CREATE TABLE orders (id TEXT PRIMARY KEY, sku TEXT, qty INTEGER, status TEXT); INSERT INTO products VALUES ('old',7); INSERT INTO orders VALUES ('existing','old',3,'open');")
old.close()
old = connect(legacy)
try:
    assert old.execute('PRAGMA user_version').fetchone()[0]==1
    assert old.execute('SELECT * FROM orders').fetchall()==[('existing','old',3,'open')]
    assert old.execute('SELECT stock,reserved FROM products').fetchall()==[(7,0)]
    with old: old.execute('UPDATE products SET reserved=2')
finally: old.close()
old = connect(legacy)
try:
    assert available(old,'old')==5
    assert dispatch(old,'stock',{'sku':'old'})=={'stock':7}
    with old: old.execute('PRAGMA user_version=2')
finally: old.close()
try: connect(legacy)
except ValueError: pass
else: raise AssertionError('future schema accepted')
old=sqlite3.connect(legacy)
try:
    assert old.execute('PRAGMA user_version').fetchone()[0]==2
    assert old.execute('SELECT stock,reserved FROM products').fetchall()==[(7,2)]
finally: old.close()
# Migration must preserve transaction behavior of the unchanged purchase API.
buy(db, ident='duplicate-order')
before = stock(db, 'book')
try: buy(db, ident='duplicate-order')
except sqlite3.IntegrityError: pass
else: raise AssertionError('duplicate order unexpectedly accepted')
assert stock(db, 'book') == before, 'rejected duplicate order consumed stock'
assert db.execute("SELECT COUNT(*) FROM orders WHERE id='duplicate-order'").fetchone()[0] == 1
# Inject a database failure AFTER schema work, not before the first change.
# A context manager alone does not begin a transaction for SQLite DDL.
from unittest.mock import patch
interrupted_path = str(Path(folder)/'interrupted.sqlite')
real_connect = sqlite3.connect
raw = real_connect(interrupted_path)
raw.executescript("CREATE TABLE products (sku TEXT PRIMARY KEY, stock INTEGER NOT NULL); CREATE TABLE orders (id TEXT PRIMARY KEY, sku TEXT, qty INTEGER, status TEXT); INSERT INTO products VALUES ('saved',9);")
raw.close()
def interrupted_connect(*args, **kwargs):
    conn = real_connect(*args, **kwargs)
    conn.set_authorizer(lambda action, first, second, *_:
        sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_PRAGMA and first.lower() == 'user_version' and second is not None else sqlite3.SQLITE_OK)
    return conn
with patch('sqlite3.connect', interrupted_connect):
    try: connect(interrupted_path)
    except sqlite3.DatabaseError: pass
    else: raise AssertionError('migration failure was swallowed')
raw = real_connect(interrupted_path)
try:
    assert [r[1] for r in raw.execute('PRAGMA table_info(products)')] == ['sku','stock'], 'failed migration left partial schema changes'
    assert raw.execute('PRAGMA user_version').fetchone()[0] == 0
    assert raw.execute('SELECT * FROM products').fetchall() == [('saved',9)]
finally: raw.close()''',
    'shop_idempotency': '''assert buy(db)=={'id':'a'}
assert buy(db)=={'id':'a'} and stock(db,'book')==8
db.close(); db=connect(path)
assert buy(db)=={'id':'a'} and stock(db,'book')==8
for sku, qty in [('book',3),('pen',2)]:
    try: buy(db, sku=sku, quantity=qty)
    except ValueError: pass
    else: raise AssertionError('conflicting key accepted')
assert stock(db,'book')==8 and stock(db,'pen')==5
assert db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==1''',
    'shop_cancel': '''buy(db)
dispatch(db,'cancel',{'id':'a'})
assert stock(db,'book')==10
db.close(); db=connect(path)
dispatch(db,'cancel',{'id':'a'})
assert stock(db,'book')==10
assert db.execute("SELECT status FROM orders WHERE id='a'").fetchone()[0]=='cancelled'
try: dispatch(db,'cancel',{'id':'missing'})
except ValueError: pass
else: raise AssertionError('missing order accepted')''',
    'shop_batch': '''def item(ident, sku='book', qty=2): return dict(id=ident,sku=sku,quantity=qty)
assert dispatch(db,'batch',[])=={'ids':[]}
for bad in [item('x',qty=99),item('x',qty=True),item('x',qty=0),item('x',sku='missing'),item('a')]:
    rejected(lambda: dispatch(db,'batch',[item('a'),bad]))
    assert stock(db,'book')==10 and stock(db,'pen')==5
    assert db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==0
assert dispatch(db,'batch',[item('a'),item('b','pen',3)])=={'ids':['a','b']}
db.close(); db=connect(path)
assert stock(db,'book')==8 and stock(db,'pen')==2
assert db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==2''',
}
ASSERTIONS = {name: PRELUDE.replace('        CASE', '\n'.join('        ' + line for line in code.splitlines()))
              for name, code in CHECKS.items()}
