import json
import unittest
from unittest.mock import patch

import test_runtime as fixtures
from test_runtime import FakeProvider, call, yes, no
from eca.agent import Agent
from eca.changes import Changes


class DeletionTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.RuntimeTests.setUp
    tearDown = fixtures.RuntimeTests.tearDown

    def journal(self):
        self.tools.changes = Changes(self.store, self.state['id'], self.tools.path)
        return self.tools.changes

    async def test_delete_diff_accept_and_exact_byte_undo(self):
        changes = self.journal()
        path = self.root/'old.py'
        original = b'\xef\xbb\xbf# old\r\n'
        path.write_bytes(original)
        result = await self.tools.execute('delete', {'path':'old.py'})
        self.assertIn('Deleted', result)
        self.assertFalse(path.exists())
        ident = changes.list()[0]['id']
        self.assertIn('+++ /dev/null', changes.diff(ident))
        changes.accept(ident)
        changes.undo(ident)
        self.assertEqual(path.read_bytes(), original)

    async def test_denial_mode_protection_binary_and_missing_journal(self):
        path = self.root/'keep.txt'
        path.write_bytes(b'keep')
        self.tools.approve = no
        self.assertIn('Denied', await self.tools.execute('delete', {'path':'keep.txt'}))
        self.tools.approve = yes
        self.assertIn('journal', await self.tools.execute('delete', {'path':'keep.txt'}))
        self.journal()
        self.settings.mode = 'plan'
        self.assertIn('Denied', await self.tools.execute('delete', {'path':'keep.txt'}))
        self.settings.mode = 'code'
        for name in ['.env', '.', '../outside.txt']:
            self.assertIn('Error', await self.tools.execute('delete', {'path':name}))
        path.write_bytes(b'\x00binary')
        self.assertIn('Binary', await self.tools.execute('delete', {'path':'keep.txt'}))
        self.assertEqual(path.read_bytes(), b'\x00binary')
        self.assertEqual(self.tools.changes.list(), [])

    async def test_approval_race_preserves_new_bytes(self):
        changes = self.journal()
        path = self.root/'a.txt'
        path.write_bytes(b'before')
        async def approve(*_):
            path.write_bytes(b'user edit')
            return True
        self.tools.approve = approve
        self.assertIn('changed while', await self.tools.execute('delete', {'path':'a.txt'}))
        self.assertEqual(path.read_bytes(), b'user edit')
        self.assertEqual(changes.list(), [])

    async def test_empty_delete_undo_conflict_and_crash_recovery(self):
        changes = self.journal()
        path = self.root/'empty.txt'
        path.write_bytes(b'')
        await self.tools.delete('empty.txt')
        ident = changes.list()[0]['id']
        self.assertIn('Delete empty file', changes.diff(ident))
        path.write_bytes(b'user recreated')
        with self.assertRaisesRegex(ValueError, 'refusing'):
            changes.undo(ident)
        self.assertEqual(path.read_bytes(), b'user recreated')
        # Simulate crash after unlink but before the applied status commit.
        path.unlink()
        changes.mark(ident, 'prepared')
        changes.undo(ident)
        self.assertEqual(path.read_bytes(), b'')
        self.assertEqual(changes.get(ident)[-1], 'undone')

    async def test_guidance_precedes_delete(self):
        changes = self.journal()
        (self.root/'AGENTS.md').write_text('Read project rules first.', encoding='utf-8')
        (self.root/'keep.txt').write_bytes(b'keep')
        self.assertIn('applicable rules', await self.tools.delete('keep.txt'))
        self.assertTrue((self.root/'keep.txt').exists())
        self.assertEqual(changes.list(), [])

    async def test_journal_failure_does_not_delete(self):
        changes = self.journal()
        path = self.root/'keep.txt'
        path.write_bytes(b'original')
        with patch.object(changes, 'prepare', side_effect=OSError('disk full')):
            self.assertIn('disk full', await self.tools.execute('delete', {'path':'keep.txt'}))
        self.assertEqual(path.read_bytes(), b'original')

    async def test_failed_unlink_can_be_recovered_without_replay(self):
        changes = self.journal()
        path = self.root/'keep.txt'
        path.write_bytes(b'original')
        with patch.object(type(path), 'unlink', side_effect=PermissionError('file locked')):
            self.assertIn('file locked', await self.tools.execute('delete', {'path':'keep.txt'}))
        ident = changes.list()[0]['id']
        self.assertEqual(changes.get(ident)[-1], 'prepared')
        changes.undo(ident)
        self.assertEqual(path.read_bytes(), b'original')
        self.assertEqual(changes.get(ident)[-1], 'undone')

    async def test_isolated_delete_review_merge_conflict_and_undo(self):
        self.settings.project_memory = False
        self.settings.auto_compact = False
        self.settings.permission = 'accept-edits'
        path = self.root/'old.py'
        path.write_bytes(b'uncommitted\r\n')
        agent = Agent(self.settings, self.store, self.state, yes, yes, lambda *_:None, FakeProvider([]))
        try:
            with patch('eca.agent.Provider', lambda _: FakeProvider([
                call('delete', {'path':'old.py'}), {'role':'assistant','content':'done'}])):
                results = json.loads(await agent.parallel([{'task':'remove old','mode':'code'}]))
            child = results[0]['session']
            self.assertEqual(results[0]['changes'], [{'path':'old.py','status':'deleted'}])
            self.assertTrue(path.exists())
            path.write_bytes(b'new parent')
            with self.assertRaisesRegex(ValueError, 'conflict'):
                await agent.merge(child, ['old.py'])
            path.write_bytes(b'uncommitted\r\n')
            await agent.merge(child, ['old.py'])
            self.assertFalse(path.exists())
            agent.changes.undo(agent.changes.list()[0]['id'])
            self.assertEqual(path.read_bytes(), b'uncommitted\r\n')
            # Arbitrarily missing files cannot masquerade as authorized deletions.
            with self.assertRaisesRegex(ValueError, 'deletion record'):
                await agent.merge(child, ['never-existed.py'])
        finally:
            await agent.close()
