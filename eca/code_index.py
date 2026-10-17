"""Bounded incremental source index. No code execution, embeddings or model calls."""
import ast
import hashlib
import json
import re
import sqlite3


def structure(path, text):
    symbols, imports = [], []
    if path.endswith('.py'):
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.append({'name': node.name, 'line': node.lineno, 'kind': type(node).__name__})
                elif isinstance(node, ast.Import):
                    imports.extend(n.name for n in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append('.' * node.level + (node.module or ''))
        except (SyntaxError, ValueError, RecursionError):
            pass
    else:
        for line, value in enumerate(text.splitlines(), 1):
            match = re.match(r'\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|interface|type|def|fn|func|struct|enum)\s+([\w$]+)', value)
            if match:
                symbols.append({'name': match[1], 'line': line, 'kind': 'lexical'})
            if re.match(r'\s*(?:import\b|from\b|use\b|#include\b)', value):
                imports.append(value.strip()[:200])
    return {'symbols': symbols[:100], 'imports': imports[:100]}


class IndexCancelled(Exception):
    """Cooperative worker cancellation; never publish a partial transaction."""


class CodeIndex:
    def __init__(self, tools, cancelled=None):
        self.tools = tools
        self.cancelled = cancelled

    def check_cancelled(self):
        if self.cancelled is not None and self.cancelled.is_set():
            raise IndexCancelled()

    def query(self, query='', limit=10, outline=False):
        if not 1 <= limit <= 50 or len(query) > 500:
            raise ValueError('Index limit must be 1..50; query at most 500 characters')
        if not outline and not re.findall(r'\w+', query, re.UNICODE):
            raise ValueError('code_search requires a query containing words')
        self.check_cancelled()
        from .workspaces import source_files
        root = self.tools.settings.root
        directory = self.tools.settings.state_dir
        if directory.resolve() != directory:
            raise ValueError('Index storage must not be an alias')
        directory.mkdir(exist_ok=True)
        path = directory / 'code-index.sqlite3'
        for suffix in ('', '-journal', '-wal', '-shm'):
            if (directory / (path.name + suffix)).is_symlink():
                raise ValueError('Index files must not be symbolic links')
        db = sqlite3.connect(path)
        try:
            db.execute('CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, stamp TEXT, digest TEXT, outline TEXT)')
            db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS source USING fts5(path, body, tokenize="unicode61")')
            known = dict(db.execute('SELECT path,stamp FROM files'))
            seen, changed, skipped, total, scanned = set(), 0, 0, 0, 0
            partial = False
            with db:
                # Transactional migration also backfills unchanged pre-v0.12 caches.
                db.execute('BEGIN')
                migrated = db.execute("SELECT 1 FROM sqlite_master WHERE name='symbols'").fetchone()
                db.execute('CREATE TABLE IF NOT EXISTS symbols(path TEXT, name TEXT, line INTEGER, kind TEXT)')
                db.execute('CREATE INDEX IF NOT EXISTS symbol_names ON symbols(name,path)')
                if not migrated:
                    for rel, data in db.execute('SELECT path,outline FROM files'):
                        self.check_cancelled()
                        self.save_symbols(db, rel, json.loads(data))
                for source in source_files(self.tools):
                    self.check_cancelled()
                    scanned += 1
                    if scanned > 100000:
                        partial = True
                        break
                    rel = source.relative_to(root).as_posix()
                    if source.is_symlink() or source.resolve() != root / rel:
                        skipped += 1
                        continue
                    try:
                        stat = source.stat()
                        if stat.st_size > 1_000_000:
                            skipped += 1
                            continue
                        total += stat.st_size
                        if total > 100_000_000:
                            partial = True
                            break
                        credential_scope = hashlib.sha256(self.tools.settings.api_key.encode()).hexdigest()
                        stamp = f'{stat.st_mtime_ns}:{stat.st_ctime_ns}:{stat.st_size}:{credential_scope}'
                        if known.get(rel) == stamp:
                            seen.add(rel)
                            continue
                        with source.open('rb') as stream:
                            raw = stream.read(1_000_001)
                        if len(raw) > 1_000_000:
                            skipped += 1
                            continue
                        text = raw.decode('utf-8-sig')
                        if '\x00' in text or (self.tools.settings.api_key and self.tools.settings.api_key in text):
                            skipped += 1
                            continue
                        self.check_cancelled()
                        info = structure(rel, text)
                        self.check_cancelled()
                        self.save_symbols(db, rel, info)
                        digest = hashlib.sha256(raw).hexdigest()
                        db.execute('DELETE FROM source WHERE path=?', (rel,))
                        db.execute('INSERT INTO source(path,body) VALUES(?,?)', (rel, text))
                        db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?)',
                                   (rel, stamp, digest, json.dumps(info, ensure_ascii=False)))
                        seen.add(rel)
                        changed += 1
                    except (OSError, UnicodeError):
                        skipped += 1
                # Stale and now-ignored entries must never remain searchable, even in a partial scan.
                self.check_cancelled()
                for removed in known.keys() - seen:
                    self.check_cancelled()
                    db.execute('DELETE FROM symbols WHERE path=?', (removed,))
                    db.execute('DELETE FROM source WHERE path=?', (removed,))
                    db.execute('DELETE FROM files WHERE path=?', (removed,))
                self.check_cancelled()
            self.check_cancelled()
            tokens = re.findall(r'\w+', query, re.UNICODE)[:20]
            if tokens:
                expression = ' OR '.join('"' + token + '"' for token in tokens)
                rows = db.execute('SELECT files.path,digest,outline FROM source JOIN files ON files.path=source.path '
                                  'WHERE source MATCH ? ORDER BY bm25(source),files.path LIMIT ?', (expression, limit)).fetchall()
            elif outline:
                rows = db.execute('SELECT path,digest,outline FROM files ORDER BY path LIMIT ?', (limit,)).fetchall()
            else:
                raise ValueError('code_search requires a query containing words')
            if len(tokens) == 1 and query.strip() == tokens[0]:
                exact = db.execute('SELECT DISTINCT files.path,digest,outline FROM symbols JOIN files '
                                   'ON files.path=symbols.path WHERE symbols.name=? ORDER BY files.path LIMIT ?',
                                   (tokens[0], limit)).fetchall()
                paths = {row[0] for row in exact}
                rows = (exact + [row for row in rows if row[0] not in paths])[:limit]
            results = []
            for rel, digest, data in rows:
                self.check_cancelled()
                try:
                    source = self.tools.path(rel)
                    with source.open('rb') as stream:
                        raw = stream.read(1_000_001)
                    if hashlib.sha256(raw).hexdigest() != digest:
                        continue
                    info = json.loads(data)
                    item = {'path': rel, 'sha256': digest}
                    item['matched_symbols'] = [symbol for symbol in info['symbols'] if symbol['name'] == query.strip()]
                    if outline:
                        item.update(info)
                    else:
                        lines = raw.decode('utf-8-sig').splitlines()
                        hits = [i for i, line in enumerate(lines) if any(t.casefold() in line.casefold() for t in tokens)][:4]
                        item['matches'] = [{'line': i + 1, 'text': lines[i][:350]} for i in hits]
                        item['symbols'] = info['symbols'][:12]
                    results.append(item)
                except (OSError, ValueError):
                    continue
            payload = {'results': results, 'index': {'files': len(seen), 'updated': changed,
                              'skipped': skipped, 'partial': partial or scanned >= 30000},
                       'output_truncated': False,
                       'notice': 'Historical source index; verify files before edits. Imports are syntax summaries, not resolved dependencies.'}
            encoded = json.dumps(payload, ensure_ascii=False)
            while results and len(encoded) > self.tools.settings.output_limit:
                results.pop()
                payload['output_truncated'] = True
                encoded = json.dumps(payload, ensure_ascii=False)
            return encoded
        finally:
            db.close()

    @staticmethod
    def save_symbols(db, path, info):
        db.execute('DELETE FROM symbols WHERE path=?', (path,))
        db.executemany('INSERT INTO symbols VALUES(?,?,?,?)',
                       [(path, s['name'], s['line'], s['kind']) for s in info['symbols']])
