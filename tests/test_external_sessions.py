import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eca import external_sessions


def write(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.codex = root / 'codex'
        self.claude = root / 'claude'
        self.workbuddy = root / 'workbuddy'
        self.env = patch.dict(os.environ, {'ECA_CODEX_HOME': str(self.codex),
                                           'ECA_CLAUDE_HOME': str(self.claude),
                                           'ECA_WORKBUDDY_HOME': str(self.workbuddy)})
        self.env.start()

        # Claude: queue noise, a user message, an assistant turn with thinking.
        write(self.claude / 'projects' / 'c--Users-x' / 'sess-claude.jsonl', [
            {'type': 'queue-operation', 'operation': 'enqueue', 'content': 'ignore me'},
            {'type': 'user', 'timestamp': '2026-10-20T10:00:00Z',
             'message': {'role': 'user', 'content': 'claude 里问的第一个问题'}},
            {'type': 'assistant', 'timestamp': '2026-10-20T10:00:01Z',
             'message': {'role': 'assistant', 'content': [
                 {'type': 'thinking', 'thinking': 'secret reasoning'},
                 {'type': 'text', 'text': 'claude 的回答'}]}},
        ])

        # Codex: session_meta, event noise, then response items.
        write(self.codex / 'sessions' / '2026' / '10' / '22' / 'rollout-a.jsonl', [
            {'type': 'session_meta', 'payload': {'id': 'codex-1'}},
            {'type': 'event_msg', 'payload': {'type': 'token_count'}},
            {'type': 'response_item', 'timestamp': '2026-10-21T09:00:00Z',
             'payload': {'type': 'message', 'role': 'developer', 'content': [
                 {'type': 'input_text', 'text': 'system instructions'}]}},
            {'type': 'response_item', 'timestamp': '2026-10-21T09:00:05Z',
             'payload': {'type': 'message', 'role': 'user', 'content': [
                 {'type': 'input_text', 'text': 'codex 里问的问题'}]}},
            {'type': 'response_item', 'timestamp': '2026-10-21T09:00:06Z',
             'payload': {'type': 'message', 'role': 'assistant', 'content': [
                 {'type': 'output_text', 'text': 'codex 的回答'}]}},
        ])

        # WorkBuddy: SQLite index plus a transcript next to it.
        self.workbuddy.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.workbuddy / 'workbuddy.db')
        con.execute('create table sessions (id text, cwd text, title text, custom_title text, updated_at int)')
        con.execute('insert into sessions values (?,?,?,?,?)',
                    ('sess-buddy', 'C:/work/项目', 'WorkBuddy 标题', None, 1000))
        con.commit()
        con.close()
        write(self.workbuddy / 'projects' / 'c--work' / 'sess-buddy.jsonl', [
            {'type': 'message', 'role': 'user', 'timestamp': '2026-10-19T08:00:00Z',
             'content': [{'type': 'input_text', 'text': 'workbuddy 的问题'}]},
            {'type': 'file-history-snapshot', 'snapshot': {}},
            {'type': 'message', 'role': 'assistant',
             'content': [{'type': 'text', 'text': 'workbuddy 的回答'}]},
        ])

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class Conversion(unittest.TestCase):
    """Imported history must be plain text: no fake tool calls, no unmarked trust."""

    def test_roles_are_preserved_and_nothing_else_is_added(self):
        converted = external_sessions.to_eca_messages([
            {'role': 'user', 'text': '问题'}, {'role': 'assistant', 'text': '回答'}])
        self.assertEqual([item['role'] for item in converted], ['user', 'assistant'])
        self.assertEqual([item['content'] for item in converted], ['问题', '回答'])
        for item in converted:
            self.assertEqual(set(item), {'role', 'content'}, 'no tool_calls or foreign keys leak through')

    def test_only_the_tail_is_kept_within_the_caps(self):
        many = [{'role': 'user', 'text': f'message {index}'} for index in range(200)]
        converted = external_sessions.to_eca_messages(many, limit=10)
        self.assertEqual(len(converted), 10)
        self.assertEqual(converted[-1]['content'], 'message 199')

    def test_total_characters_are_capped(self):
        many = [{'role': 'assistant', 'text': 'x' * 5000} for _ in range(20)]
        converted = external_sessions.to_eca_messages(many, limit=60, max_chars=12000)
        self.assertLessEqual(sum(len(item['content']) for item in converted), 15000)

    def test_empty_messages_are_dropped(self):
        self.assertEqual(external_sessions.to_eca_messages(
            [{'role': 'user', 'text': '   '}, {'role': 'assistant', 'text': ''}]), [])


class Listing(Fixture):
    def test_lists_all_three_sources_newest_first(self):
        rows = external_sessions.list_sessions()
        self.assertEqual({row['source'] for row in rows}, {'claude', 'codex', 'workbuddy'})
        self.assertEqual(rows, sorted(rows, key=lambda row: row['updated'], reverse=True))

    def test_titles_come_from_the_first_real_user_message(self):
        by_source = {row['source']: row for row in external_sessions.list_sessions()}
        self.assertEqual(by_source['claude']['title'], 'claude 里问的第一个问题')
        self.assertEqual(by_source['codex']['title'], 'codex 里问的问题')
        self.assertEqual(by_source['workbuddy']['title'], 'WorkBuddy 标题')
        self.assertEqual(by_source['workbuddy']['cwd'], 'C:/work/项目')

    def test_sources_can_be_filtered(self):
        rows = external_sessions.list_sessions(sources=['codex'])
        self.assertEqual([row['source'] for row in rows], ['codex'])


class Reading(Fixture):
    def test_claude_transcript_skips_noise_and_thinking(self):
        result = external_sessions.read_session('claude', 'sess-claude')
        self.assertEqual([message['role'] for message in result['messages']], ['user', 'assistant'])
        self.assertEqual(result['messages'][1]['text'], 'claude 的回答')
        self.assertNotIn('secret reasoning', json.dumps(result, ensure_ascii=False))

    def test_codex_transcript_keeps_only_real_roles(self):
        result = external_sessions.read_session('codex', 'rollout-a')
        self.assertEqual([message['role'] for message in result['messages']], ['user', 'assistant'])
        self.assertEqual(result['messages'][0]['at'], '2026-10-21T09:00:05Z')

    def test_workbuddy_transcript_reads_message_records(self):
        result = external_sessions.read_session('workbuddy', 'sess-buddy')
        self.assertEqual([message['text'] for message in result['messages']],
                         ['workbuddy 的问题', 'workbuddy 的回答'])

    def test_missing_session_is_reported_not_raised(self):
        result = external_sessions.read_session('claude', 'does-not-exist')
        self.assertEqual(result['messages'], [])
        self.assertIn('not found', result['error'])

    def test_unknown_source_is_rejected(self):
        with self.assertRaises(ValueError):
            external_sessions.read_session('cursor', 'x')

    def test_transcripts_are_bounded(self):
        big = self.claude / 'projects' / 'c--Users-x' / 'sess-big.jsonl'
        write(big, [{'type': 'user', 'message': {'role': 'user', 'content': 'x' * 5000}}] * 400)
        result = external_sessions.read_session('claude', 'sess-big')
        self.assertLessEqual(len(result['messages']), external_sessions.MAX_MESSAGES)
        self.assertTrue(result['truncated'])


if __name__ == '__main__':
    unittest.main()
