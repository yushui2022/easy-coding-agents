"""Preview-only LSP edits followed by explicit, conflict-checked application."""
import difflib
import asyncio
import json
from urllib.parse import urlsplit
from urllib.request import url2pathname
import uuid


def offset(text, position):
    if not isinstance(position, dict) or set(position) != {'line', 'character'}:
        raise ValueError('Invalid LSP position')
    line, char = position['line'], position['character']
    lines = text.splitlines(keepends=True)
    if not lines or text.endswith(('\n', '\r')):
        lines.append('')
    if type(line) is not int or type(char) is not int or line < 0 or char < 0 or line >= len(lines):
        raise ValueError('LSP position outside document')
    value = lines[line].rstrip('\r\n')
    units = 0
    for index in range(len(value)+1):
        if units == char:
            return sum(map(len, lines[:line])) + index
        if index < len(value):
            units += len(value[index].encode('utf-16-le')) // 2
    raise ValueError('LSP position splits a surrogate pair or exceeds the line')


def edits(text, rows):
    if not isinstance(rows, list) or len(rows) > 2000:
        raise ValueError('Too many LSP edits')
    spans = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'range', 'newText'} or not isinstance(row['newText'], str):
            raise ValueError('Only plain text edits are supported')
        start, end = offset(text, row['range']['start']), offset(text, row['range']['end'])
        if start > end:
            raise ValueError('Reversed LSP edit')
        spans.append((start, end, row['newText']))
    spans.sort()
    for previous, current in zip(spans, spans[1:]):
        if current[0] < previous[1] or current[0] == previous[0]:
            raise ValueError('Overlapping LSP edits')
    for start, end, value in reversed(spans):
        text = text[:start] + value + text[end:]
    if len(text.encode('utf-8')) > 2_000_000 or '\x00' in text:
        raise ValueError('Invalid resulting text file')
    return text


async def preview(tools, server, path, new_name, line=1, character=0):
    if not new_name.strip() or len(new_name) > 256 or any(c.isspace() for c in new_name):
        raise ValueError('Supply a nonempty symbol name without whitespace (max 256 characters)')
    from .workspaces import source_files
    snapshot, size = {}, 0
    for target in source_files(tools):
        if target.stat().st_size > 2_000_000:
            raise ValueError('Rename snapshot file exceeds 2 MB; narrow project root')
        raw = target.read_bytes()
        size += len(raw)
        if size > 20_000_000 or len(snapshot) >= 2000:
            raise ValueError('Rename snapshot exceeds 20 MB / 2000 files; narrow project root')
        snapshot[target] = raw
    from .lsp import LSPManager
    if tools.language_servers is None:
        tools.language_servers = LSPManager(tools)
    response = await tools.language_servers.query(server, 'rename', path, line, character, new_name)
    if response.startswith('Denied'):
        return response
    result = json.loads(response)['result']
    if not result:
        return 'No rename edits returned.'
    if not isinstance(result, dict) or set(result) - {'changes', 'documentChanges'} or len(result) != 1:
        raise ValueError('Unsupported workspace edit shape')
    rows = []
    if 'changes' in result:
        rows = [(uri, None, items) for uri, items in result['changes'].items()]
    else:
        for item in result['documentChanges']:
            if set(item) != {'textDocument', 'edits'}:
                raise ValueError('Resource operations and annotated edits are not supported')
            doc = item['textDocument']
            rows.append((doc['uri'], doc.get('version'), item['edits']))
    if not 1 <= len(rows) <= 100:
        raise ValueError('Rename must affect 1..100 files')
    changes, seen, diff = [], set(), ''
    client = tools.language_servers.clients.get(server)
    for uri, version, items in rows:
        parsed = urlsplit(uri)
        if parsed.scheme != 'file' or parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError('Only local file URIs are supported')
        target = tools.path(url2pathname(parsed.path))
        if target in seen or target not in snapshot:
            raise ValueError('Duplicate or untracked rename target')
        seen.add(target)
        before = snapshot[target]
        if target.read_bytes() != before:
            raise ValueError('File changed during rename request; request a fresh preview')
        if version is not None and (not client or client.documents.get(uri, (None,))[0] != version):
            raise ValueError('Unknown or stale LSP document version')
        document = client.documents.get(uri) if client else None
        if document and document[1] != before.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n'):
            raise ValueError('Language server document differs from the rename snapshot')
        after = edits(before.decode('utf-8'), items)
        name = target.relative_to(tools.settings.root).as_posix()
        diff += ''.join(difflib.unified_diff(before.decode('utf-8').splitlines(True), after.splitlines(True), fromfile='a/'+name, tofile='b/'+name))
        changes.append((name, before, after))
    if len(diff) > min(100000, tools.settings.output_limit-1000):
        raise ValueError('Rename diff exceeds preview limit; narrow the rename scope')
    ident = uuid.uuid4().hex[:12]
    payload = json.dumps({'preview_id': ident, 'diff': diff, 'files': [c[0] for c in changes],
                       'notice': 'Preview only. Apply with lsp_apply; normal file approval still required.'}, ensure_ascii=False)
    if len(payload) > tools.settings.output_limit:
        raise ValueError('Serialized preview exceeds output limit')
    tools.rename_previews = {ident: (server, changes)}
    return payload


async def apply(tools, preview_id):
    from .tools import atomic_write
    entry = getattr(tools, 'rename_previews', {}).get(preview_id)
    if not entry:
        raise ValueError('Unknown/expired rename preview')
    server, changes = entry
    def preflight():
        for name, before, after in changes:
            target = tools.path(name)
            if target != tools.settings.root / name:
                raise ValueError('Rename path changed since preview')
            if target.read_bytes() != before:
                raise ValueError('File changed since rename preview; no edits applied')
            tools.check_file_version(target, before)
    preflight()
    for name, before, after in changes:
        rules = tools.file_guidance(tools.path(name))
        if rules:
            return 'Read applicable rules, then retry: ' + rules
    diff = ''.join(''.join(difflib.unified_diff(before.decode('utf-8').splitlines(True), after.splitlines(True), fromfile='a/'+name, tofile='b/'+name)) for name, before, after in changes)
    tools.emit('diff', diff)
    if tools.settings.permission != 'accept-edits' and await tools.approve('Apply LSP rename?', diff) is not True:
        return 'Denied: rename unchanged.'
    preflight()
    applied = []
    # No awaits between final preflight and writes. OS failures can still leave a
    # partial result; each write is individually journaled, never called atomic.
    try:
        for name, before, after in changes:
            target = tools.path(name)
            if target.read_bytes() != before:
                raise ValueError('Concurrent change during rename')
            ident = tools.changes.prepare(name, before, after.encode('utf-8')) if tools.changes else None
            atomic_write(target, after)
            if ident is not None:
                tools.changes.mark(ident, 'applied')
            tools.remember_file(target, after.encode('utf-8'))
            applied.append(name)
    except (OSError, ValueError) as exc:
        tools.rename_previews.clear()
        return json.dumps({'status': 'partial', 'applied': applied, 'error': str(exc), 'notice': 'Inspect /changes; no automatic rollback.'})
    tools.rename_previews.clear()
    diagnostics = {}
    try:
        async with asyncio.timeout(30):
            for name in applied:
                try:
                    diagnostics[name] = json.loads(await tools.language_servers.query(server, 'diagnostics', name))
                except (OSError, ValueError, TimeoutError):
                    diagnostics[name] = {'status': 'unavailable'}
    except TimeoutError:
        pass
    for name in applied:
        diagnostics.setdefault(name, {'status': 'unavailable', 'notice': 'Diagnostic time budget exhausted'})
    return json.dumps({'status': 'applied', 'files': applied, 'diagnostics': diagnostics,
                       'notice': 'Diagnostics are server reports, not test success. Pending/unavailable reports remain unverified.'}, ensure_ascii=False)
