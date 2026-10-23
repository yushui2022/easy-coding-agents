"""Read other agents' local session history, read-only.

Codex keeps rollout JSONL under ``~/.codex/sessions`` (tens of gigabytes on a
working machine), Claude Code under ``~/.claude/projects``, and WorkBuddy under
``~/.workbuddy`` (index in SQLite, transcripts under ``projects``). Nothing here
writes to those folders, imports a session into ECA, or resumes one: this is a
viewer. Every read is bounded so a 100 MB rollout cannot be pulled into memory.
"""
import json
import os
import re
import sqlite3
from pathlib import Path

MAX_MESSAGES = 200
MAX_CHARS = 40_000
MAX_LINE = 2_000_000
MAX_FILES = 20_000
SOURCES = ('codex', 'claude', 'workbuddy')


def roots():
    home = Path(os.path.expanduser('~'))
    return {
        'codex': Path(os.environ.get('ECA_CODEX_HOME') or home / '.codex'),
        'claude': Path(os.environ.get('ECA_CLAUDE_HOME') or home / '.claude'),
        'workbuddy': Path(os.environ.get('ECA_WORKBUDDY_HOME') or home / '.workbuddy'),
    }


def _text_from_blocks(blocks):
    """Flatten a content block list to text, naming non-text parts briefly."""
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        return ''
    parts = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = block.get('type')
        if kind in ('text', 'input_text', 'output_text'):
            parts.append(str(block.get('text') or ''))
        elif kind == 'thinking':
            continue
        elif kind in ('tool_use', 'tool_call'):
            parts.append(f"[工具: {block.get('name') or 'call'}]")
        elif kind == 'tool_result':
            parts.append('[工具结果]')
    return '\n'.join(part for part in parts if part.strip())


def _trim(text, limit=200):
    flat = ' '.join(str(text).split())
    return flat[:limit]


def _codex_title(path):
    """Prefer the first real user message; fall back to the rollout timestamp."""
    text = _first_user_text(path, max_lines=400)
    if text:
        return text
    match = re.match(r'rollout-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})', path.stem)
    if match:
        return f'{match.group(1)} {match.group(2)}:{match.group(3)}'
    return path.stem
def _looks_like_context(text):
    """Agents inject synthetic blocks as 'user' messages; they are not the person."""
    head = str(text).lstrip()[:120]
    return head.startswith('<')


def _claude_file(root, ident):
    base = root / 'projects'
    if not base.exists():
        return None
    for path in base.glob(f'*/{ident}.jsonl'):
        return path
    return None


def _workbuddy_file(root, ident):
    base = root / 'projects'
    if not base.exists():
        return None
    for path in base.glob(f'*/{ident}.jsonl'):
        return path
    return None


def _first_user_text(path, kinds=('user',), max_lines=200):
    """Cheap title probe: stop as soon as a user message appears."""
    try:
        with path.open('r', encoding='utf-8', errors='replace') as handle:
            for index, line in enumerate(handle):
                if index > max_lines:
                    break
                if len(line) > MAX_LINE:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                # Claude keeps role/message at the top; Codex nests both in payload.
                payload = record.get('payload') if isinstance(record.get('payload'), dict) else {}
                message = record.get('message') if isinstance(record.get('message'), dict) else {}
                role = payload.get('role') or record.get('role') or message.get('role')
                if role != 'user':
                    continue
                if message:
                    text = _text_from_blocks(message.get('content'))
                elif payload:
                    text = _text_from_blocks(payload.get('content'))
                else:
                    text = _text_from_blocks(record.get('content'))
                if text.strip() and not _looks_like_context(text):
                    return _trim(text)
    except OSError:
        pass
    return ''


def _workbuddy_index(root):
    """Session titles live in SQLite; transcripts are separate JSONL files."""
    rows = {}
    database = root / 'workbuddy.db'
    if not database.exists():
        return rows
    try:
        con = sqlite3.connect(f'file:{database.as_posix()}?mode=ro', uri=True)
        for ident, title, custom, cwd, updated in con.execute(
                'select id, title, custom_title, cwd, updated_at from sessions'):
            rows[str(ident)] = {'title': custom or title or '', 'cwd': cwd or '', 'updated': updated}
        con.close()
    except sqlite3.Error:
        pass
    return rows


def list_sessions(limit=200, sources=None):
    """Newest first. Only cheap metadata is read: first lines and one SQLite table."""
    roots_ = roots()
    wanted = [name for name in SOURCES if name in (sources or SOURCES)]
    found = []
    budget = [MAX_FILES]

    def spend():
        budget[0] -= 1
        return budget[0] > 0

    for source in wanted:
        root = roots_[source]
        if not root.exists():
            continue
        if source == 'claude':
            for path in (root / 'projects').glob('*/*.jsonl'):
                if not spend():
                    break
                try:
                    stat = path.stat()
                except OSError:
                    continue
                found.append({'source': source, 'id': path.stem,
                              'title': _first_user_text(path) or path.stem,
                              'cwd': '', 'updated': int(stat.st_mtime), 'size': stat.st_size})
        elif source == 'codex':
            for path in (root / 'sessions').glob('*/*/*/rollout-*.jsonl'):
                if not spend():
                    break
                try:
                    stat = path.stat()
                except OSError:
                    continue
                found.append({'source': source, 'id': path.stem,
                              'title': _codex_title(path),
                              'cwd': '', 'updated': int(stat.st_mtime), 'size': stat.st_size})
        else:
            index = _workbuddy_index(root)
            for path in (root / 'projects').glob('*/*.jsonl'):
                if not spend():
                    break
                try:
                    stat = path.stat()
                except OSError:
                    continue
                meta = index.get(path.stem, {})
                found.append({'source': source, 'id': path.stem,
                              'title': _trim(meta.get('title') or '') or _first_user_text(path) or path.stem,
                              'cwd': meta.get('cwd') or '', 'updated': int(stat.st_mtime), 'size': stat.st_size})

    found.sort(key=lambda row: row['updated'], reverse=True)
    return found[:limit]


def _claude_messages(path, cap):
    with path.open('r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            if sum(cap['chars']) >= MAX_CHARS or cap['count'] >= MAX_MESSAGES:
                return
            if len(line) > MAX_LINE:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get('type') not in ('user', 'assistant'):
                continue
            message = record.get('message') or {}
            role = message.get('role') or record.get('type')
            text = _text_from_blocks(message.get('content'))
            if not text.strip():
                continue
            cap['count'] += 1
            cap['chars'].append(len(text))
            cap['messages'].append({'role': role, 'text': text[:4000],
                                    'at': record.get('timestamp') or ''})


def _codex_messages(path, cap):
    with path.open('r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            if sum(cap['chars']) >= MAX_CHARS or cap['count'] >= MAX_MESSAGES:
                return
            if len(line) > MAX_LINE:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            payload = record.get('payload') or {}
            if record.get('type') != 'response_item' or payload.get('type') != 'message':
                continue
            role = payload.get('role')
            if role not in ('user', 'assistant'):
                continue
            text = _text_from_blocks(payload.get('content'))
            if not text.strip():
                continue
            cap['count'] += 1
            cap['chars'].append(len(text))
            cap['messages'].append({'role': role, 'text': text[:4000],
                                    'at': record.get('timestamp') or ''})


def _workbuddy_messages(path, cap):
    with path.open('r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            if sum(cap['chars']) >= MAX_CHARS or cap['count'] >= MAX_MESSAGES:
                return
            if len(line) > MAX_LINE:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get('type') != 'message':
                continue
            role = record.get('role')
            if role not in ('user', 'assistant'):
                continue
            text = _text_from_blocks(record.get('content'))
            if not text.strip():
                continue
            stamp = record.get('timestamp')
            cap['count'] += 1
            cap['chars'].append(len(text))
            cap['messages'].append({'role': role, 'text': text[:4000],
                                    'at': stamp if isinstance(stamp, str) else ''})


def to_eca_messages(messages, limit=60, max_chars=60000):
    """Turn a foreign transcript into plain ECA messages.

    Deliberately text-only: a foreign tool call has no ECA tool result to pair
    with, and inventing one would fabricate an execution that never happened.
    The whole block is marked untrusted, because another agent's transcript can
    contain instructions that were never meant for this session.
    """
    kept, total = [], 0
    for message in reversed(messages):
        text = str(message.get('text') or '').strip()
        if not text:
            continue
        role = 'assistant' if message.get('role') == 'assistant' else 'user'
        if total + len(text) > max_chars and kept:
            break
        kept.append({'role': role, 'content': text[:8000]})
        total += len(text)
        if len(kept) >= limit:
            break
    kept.reverse()
    return kept


READERS = {'claude': _claude_messages, 'codex': _codex_messages, 'workbuddy': _workbuddy_messages}
LOOKUPS = {'claude': _claude_file, 'codex': None, 'workbuddy': _workbuddy_file}


def read_session(source, ident, max_messages=MAX_MESSAGES):
    """Bounded transcript read. Returns a dict, never raises for a bad id."""
    if source not in READERS:
        raise ValueError(f'Unknown session source {source!r}; use one of {", ".join(SOURCES)}')
    roots_ = roots()
    path = LOOKUPS[source](roots_[source], ident) if LOOKUPS[source] else None
    if source == 'codex':
        for candidate in (roots_[source] / 'sessions').glob(f'*/*/*/{ident}.jsonl'):
            path = candidate
            break
    if path is None or not path.exists():
        return {'source': source, 'id': ident, 'messages': [], 'truncated': False,
                'error': 'Session file not found'}
    cap = {'messages': [], 'count': 0, 'chars': []}
    try:
        READERS[source](path, cap)
    except OSError as error:
        return {'source': source, 'id': ident, 'messages': [], 'truncated': False,
                'error': f'Unreadable session file: {error.strerror or "I/O error"}'}
    messages = cap['messages'][:max(1, min(int(max_messages), MAX_MESSAGES))]
    for message in messages:
        # Injected context arrives as a "user" turn; say so instead of pretending
        # the person typed it.
        message['synthetic'] = message['role'] == 'user' and _looks_like_context(message['text'])
    return {'source': source, 'id': ident, 'messages': messages,
            'truncated': len(cap['messages']) > len(messages) or sum(cap['chars']) >= MAX_CHARS,
            'path_name': path.name}
