"""Regression cases for safe single-file edits, using no model API."""
import json
import unittest

from eca.agent import Agent
from eca.editing import plan_edits
from eca.tools import Tools
import test_runtime as fixtures
from test_runtime import FakeProvider, call, yes


class EditingTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.RuntimeTests.setUp
    tearDown = fixtures.RuntimeTests.tearDown

    def agent(self):
        self.settings.permission = 'accept-edits'
        self.settings.project_memory = False
        return Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None, FakeProvider([]))

    async def test_batch_one_journal_and_byte_exact_undo(self):
        agent = self.agent()
        path = self.root / 'code.py'
        original = '\ufeff# 中文\r\na = 1\r\nb = 2\r\n'.encode('utf-8')
        path.write_bytes(original)
        await agent.tools.read('code.py')
        result = await agent.tools.execute('edit_many', dict(path='code.py', edits=[
            dict(old='a = 1', new='a = 3'), dict(old='b = 2', new='b = 4')]))
        self.assertIn('Saved', result)
        self.assertEqual(path.read_bytes(), original.replace(b'a = 1', b'a = 3').replace(b'b = 2', b'b = 4'))
        self.assertEqual(len(agent.changes.list()), 1)
        agent.changes.undo(agent.changes.list()[0]['id'])
        self.assertEqual(path.read_bytes(), original)

    async def test_last_edit_failure_has_no_partial_write_or_journal(self):
        agent = self.agent()
        path = self.root / 'code.py'
        path.write_bytes(b'a=1\nb=2\n')
        result = await agent.tools.execute('edit_many', dict(path='code.py', edits=[
            dict(old='a=1', new='a=3'), dict(old='missing', new='b=4')]))
        self.assertIn('Edit 2', result)
        self.assertEqual(path.read_bytes(), b'a=1\nb=2\n')
        self.assertEqual(agent.changes.list(), [])

    async def test_overlap_and_sequential_dependency_rejected(self):
        for edits in ([dict(old='abc', new='a'), dict(old='bc', new='b')],
                      [dict(old='abc', new='xyz'), dict(old='xyz', new='done')]):
            with self.assertRaises(ValueError):
                plan_edits('abc', edits)

    async def test_stale_read_blocks_edit_write_and_delete_until_reread(self):
        agent = self.agent()
        path = self.root / 'a'
        path.write_text('old\ntarget', encoding='utf-8')
        await agent.tools.read('a', limit=1)
        path.write_text('user\ntarget', encoding='utf-8')
        for name, args in [('edit', dict(old='target', new='changed')), ('write', dict(content='overwrite')), ('delete', {})]:
            result = await agent.tools.execute(name, dict(path='a', **args))
            self.assertIn('changed since', result)
            self.assertEqual(path.read_text(), 'user\ntarget')
        self.assertEqual(agent.changes.list(), [])
        await agent.tools.read('a')
        self.assertIn('Saved', await agent.tools.edit('a', 'target', 'changed'))
        self.assertIn('Saved', await agent.tools.edit('a', 'changed', 'next'))

    async def test_read_version_survives_session_resume(self):
        path = self.root / 'a'
        path.write_text('before', encoding='utf-8')
        await self.tools.read('a')
        self.store.save(self.state)
        path.write_text('after', encoding='utf-8')
        restored = Tools(self.settings, self.store.load(self.state['id']), yes, yes, lambda *_: None)
        result = await restored.execute('edit', dict(path='a', old='after', new='oops'))
        self.assertIn('changed since', result)
        self.assertEqual(path.read_text(), 'after')

    async def test_approval_time_change_rejects_entire_batch(self):
        agent = self.agent()
        self.settings.permission = 'ask'
        path = self.root / 'a'
        path.write_text('a\nb', encoding='utf-8')
        async def approve(*_):
            path.write_text('user change', encoding='utf-8')
            return True
        agent.tools.approve = approve
        result = await agent.tools.execute('edit_many', dict(path='a', edits=[dict(old='a', new='A'), dict(old='b', new='B')]))
        self.assertIn('awaiting approval', result)
        self.assertEqual(path.read_text(), 'user change')
        self.assertEqual(agent.changes.list(), [])

    def test_multiline_trailing_space_fallback_and_exact_opt_out(self):
        content = 'before\n    a = 1  \n    b = 2\t\nafter\n'
        edits = [dict(old='    a = 1\n    b = 2\n', new='    a = 3\n    b = 4\n')]
        result, relaxed = plan_edits(content, edits)
        self.assertEqual(result, 'before\n    a = 3\n    b = 4\nafter\n')
        self.assertEqual(relaxed, 1)
        result, relaxed = plan_edits('\ufeff甲  \r\n乙\t\r\n尾\n', [dict(old='甲\n乙\n', new='丙\n丁\n')])
        self.assertEqual(result, '\ufeff丙\r\n丁\r\n尾\n')
        self.assertEqual(relaxed, 1)
        with self.assertRaises(ValueError):
            plan_edits(content, edits, 'exact')

    def test_ambiguous_fallback_and_overlapping_exact_rejected(self):
        for content, old in [('a  \nb \na\nb  \n', 'a\nb\n'), ('aaa', 'aa')]:
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                plan_edits(content, [dict(old=old, new='new')])

    def test_indentation_internal_spaces_and_single_line_not_relaxed(self):
        for content, old in [('  a\n  b\n', ' a\n b\n'), ('a = 1\nb = 2\n', 'a=1\nb=2\n'),
                             ('a\n', 'a  \n'), ('print("a b")\nx\n', 'print("ab")\nx\n')]:
            with self.assertRaises(ValueError):
                plan_edits(content, [dict(old=old, new='new')])

    def test_newline_mapping_preserves_untouched_mixed_endings(self):
        content = 'head\r\na\nb\r\nc\rtail'
        result, _ = plan_edits(content, [dict(old='a\r\nb\n', new='A\nB\n'), dict(old='tail', new='end')])
        self.assertEqual(result, 'head\r\nA\r\nB\r\nc\rend')

    def test_bad_nested_arguments_and_duplicate_ranges(self):
        for edits in ([], [None], [dict(old='', new='a')], [dict(old='a', new=2)],
                      [dict(old='a', new='b', extra=1)], [dict(old='a', new='b')] * 101,
                      [dict(old='a', new='b'), dict(old='a', new='c')]):
            with self.assertRaises(ValueError):
                plan_edits('a', edits)

    async def test_plan_mode_and_denied_approval_cannot_mutate(self):
        agent = self.agent()
        path = self.root / 'a'
        path.write_text('old', encoding='utf-8')
        self.settings.mode = 'plan'
        args = dict(path='a', edits=[dict(old='old', new='new')])
        self.assertIn('Denied', await agent.tools.execute('edit_many', args))
        self.settings.mode = 'code'
        self.settings.permission = 'ask'
        agent.tools.approve = fixtures.no
        self.assertIn('Denied', await agent.tools.execute('edit_many', args))
        self.assertEqual(path.read_text(), 'old')
        self.assertEqual(agent.changes.list(), [])

    async def test_agent_batch_tool_protocol_and_progress(self):
        agent = self.agent()
        (self.root / 'a').write_text('a\nb', encoding='utf-8')
        agent.provider = FakeProvider([call('read', dict(path='a'), 'read'),
            call('edit_many', dict(path='a', edits=[dict(old='a', new='A'), dict(old='b', new='B')]), 'batch'),
            dict(role='assistant', content='done')])
        await agent.run('Update both lines')
        self.assertEqual((self.root / 'a').read_text(), 'A\nB')
        self.assertEqual(self.state['status'], 'idle')
        self.assertTrue(any(m.get('tool_call_id') == 'batch' and 'Saved' in m['content'] for m in self.state['messages']))
        self.assertIn('edit_many', json.dumps(self.state['progress']))
