"""Durable request caps shared by a root session and all its descendants."""
class SharedBudget:
    def __init__(self, store, state, limit):
        self.db = store.db
        self.root = state.get('billing_root', state['id'])
        self.limit = limit
        self.db.execute('CREATE TABLE IF NOT EXISTS budget_attempts (id TEXT PRIMARY KEY, root TEXT NOT NULL)')
        self.db.commit()

    def reserve(self, ident):
        # Synchronous transaction: concurrent children cannot pass the final slot together.
        with self.db:
            count = self.db.execute('SELECT count(*) FROM budget_attempts WHERE root=?', (self.root,)).fetchone()[0]
            if self.limit and count >= self.limit:
                raise ValueError('Shared session request budget exhausted; no new model request sent')
            self.db.execute('INSERT INTO budget_attempts VALUES (?,?)', (ident, self.root))

    def status(self):
        used = self.db.execute('SELECT count(*) FROM budget_attempts WHERE root=?', (self.root,)).fetchone()[0]
        return {'requests': used, 'limit': self.limit or None,
                'remaining': max(0, self.limit-used) if self.limit else None,
                'note': 'Shared session request attempts, including retries and summaries; not a currency spending cap.'}
