"""Bounded incremental source index. No code execution, embeddings or model calls."""
import ast
import hashlib
import json
import re
import sqlite3
import time


def structure(path, text):
    symbols, imports, references = [], [], []
    parse_status = 'python_ast' if path.endswith('.py') else 'lexical'
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
                    for name in node.names:
                        references.append({'name': name.name, 'line': node.lineno, 'kind': 'import',
                                           'target': '.' * node.level + (node.module or '') + '.' + name.name})
                elif isinstance(node, ast.Call):
                    callee = node.func
                    if isinstance(callee, (ast.Name, ast.Attribute)):
                        name = callee.id if isinstance(callee, ast.Name) else callee.attr
                        references.append({'name': name, 'line': node.lineno, 'kind': 'call',
                                           'target': ast.unparse(callee)[:200]})
        except (SyntaxError, ValueError, RecursionError):
            parse_status = 'syntax_error'
            symbols, imports, references = [], [], []
    if parse_status != 'python_ast':
        for line, value in enumerate(text.splitlines(), 1):
            match = re.match(r'\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|interface|type|def|fn|func|struct|enum)\s+([\w$]+)', value)
            if match:
                symbols.append({'name': match[1], 'line': line, 'kind': 'lexical'})
            if re.match(r'\s*(?:import\b|from\b|use\b|#include\b)', value):
                imports.append(value.strip()[:200])
    return {'symbols': symbols[:100], 'imports': imports[:100], 'references': references[:1000],
            'parse_status': parse_status,
            'structure_truncated': len(symbols) > 100 or len(imports) > 100 or len(references) > 1000}


class IndexCancelled(Exception):
    """Cooperative worker cancellation; never publish a partial transaction."""


class CodeIndex:
    def __init__(self, tools, cancelled=None):
        self.tools = tools
        self.cancelled = cancelled

    def check_cancelled(self):
        if self.cancelled is not None and self.cancelled.is_set():
            raise IndexCancelled()

    def query(self, query='', limit=10, outline=False, path='', related=False):
        started = time.perf_counter()
        if not isinstance(path, str) or len(path) > 500:
            raise ValueError('Index path must be a relative file or directory')
        path = path.replace('\\', '/')
        if path.startswith('/') or ':' in path or any(p in {'.', '..'} for p in path.split('/')):
            raise ValueError('Index path must be a relative file or directory')
        path = path.rstrip('/')
        if related and not query.isidentifier():
            raise ValueError('code_relations requires one symbol identifier')
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
        db_path = directory / 'code-index.sqlite3'
        for suffix in ('', '-journal', '-wal', '-shm'):
            if (directory / (db_path.name + suffix)).is_symlink():
                raise ValueError('Index files must not be symbolic links')
        db = sqlite3.connect(db_path)
        try:
            db.execute('CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, stamp TEXT, digest TEXT, outline TEXT)')
            db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS source USING fts5(path, body, tokenize="unicode61")')
            read_files = read_bytes = reused = 0
            seen, changed, skipped, total, scanned = set(), 0, 0, 0, 0
            partial = False
            with db:
                # Transactional migration also backfills unchanged pre-v0.12 caches.
                # Serialize refreshes before reading cached row IDs. A concurrent
                # first build must not insert duplicate FTS rows from an old snapshot.
                db.execute('BEGIN IMMEDIATE')
                known = dict(db.execute('SELECT path,stamp FROM files'))
                source_ids = dict(db.execute('SELECT path,rowid FROM source'))
                migrated = db.execute("SELECT 1 FROM sqlite_master WHERE name='symbols'").fetchone()
                db.execute('CREATE TABLE IF NOT EXISTS symbols(path TEXT, name TEXT, line INTEGER, kind TEXT)')
                db.execute('CREATE INDEX IF NOT EXISTS symbol_names ON symbols(name,path)')
                db.execute('CREATE INDEX IF NOT EXISTS symbol_paths ON symbols(path)')
                db.execute('CREATE TABLE IF NOT EXISTS references_index(path TEXT, name TEXT, line INTEGER, kind TEXT)')
                db.execute('CREATE INDEX IF NOT EXISTS reference_names ON references_index(name,path)')
                db.execute('CREATE INDEX IF NOT EXISTS reference_paths ON references_index(path)')
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
                        stamp = f'v2:{stat.st_mtime_ns}:{stat.st_ctime_ns}:{stat.st_size}:{credential_scope}'
                        if known.get(rel) == stamp:
                            seen.add(rel)
                            reused += 1
                            continue
                        with source.open('rb') as stream:
                            raw = stream.read(1_000_001)
                        read_files += 1
                        read_bytes += len(raw)
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
                        db.execute('DELETE FROM references_index WHERE path=?', (rel,))
                        db.executemany('INSERT INTO references_index VALUES(?,?,?,?)',
                                       [(rel, r['name'], r['line'], r['kind']) for r in info['references']])
                        digest = hashlib.sha256(raw).hexdigest()
                        if rel in source_ids:
                            db.execute('DELETE FROM source WHERE rowid=?', (source_ids[rel],))
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
                    db.execute('DELETE FROM references_index WHERE path=?', (removed,))
                    if removed in source_ids:
                        db.execute('DELETE FROM source WHERE rowid=?', (source_ids[removed],))
                    db.execute('DELETE FROM files WHERE path=?', (removed,))
                self.check_cancelled()
            self.check_cancelled()
            tokens = re.findall(r'\w+', query, re.UNICODE)[:20]
            scope = "(?='' OR files.path=? OR substr(files.path,1,length(?)+1)=?||'/')"
            scope_args = (path, path, path, path)
            if related:
                rows = db.execute('SELECT files.path,digest,outline FROM files WHERE ' + scope +
                                  ' AND (files.path IN (SELECT path FROM symbols WHERE name=?) OR '
                                  'files.path IN (SELECT path FROM references_index WHERE name=?)) '
                                  'ORDER BY CASE WHEN files.path IN (SELECT path FROM symbols WHERE name=?) '
                                  'THEN 0 ELSE 1 END, files.path LIMIT ?',
                                  (*scope_args, query, query, query, limit)).fetchall()
            elif tokens:
                expression = ' OR '.join('"' + token + '"' for token in tokens)
                rows = db.execute('SELECT files.path,digest,outline FROM source JOIN files ON files.path=source.path '
                                  'WHERE source MATCH ? AND ' + scope + ' ORDER BY bm25(source),files.path LIMIT ?',
                                  (expression, *scope_args, limit)).fetchall()
            elif outline:
                rows = db.execute('SELECT path,digest,outline FROM files WHERE ' + scope + ' ORDER BY path LIMIT ?', (*scope_args, limit)).fetchall()
            else:
                raise ValueError('code_search requires a query containing words')
            if not related and len(tokens) == 1 and query.strip() == tokens[0]:
                exact = db.execute('SELECT DISTINCT files.path,digest,outline FROM symbols JOIN files '
                                   'ON files.path=symbols.path WHERE symbols.name=? AND ' + scope + ' ORDER BY files.path LIMIT ?',
                                   (tokens[0], *scope_args, limit)).fetchall()
                paths = {row[0] for row in exact}
                rows = (exact + [row for row in rows if row[0] not in paths])[:limit]
            results = []
            for rel, digest, data in rows:
                self.check_cancelled()
                try:
                    source = self.tools.path(rel)
                    with source.open('rb') as stream:
                        raw = stream.read(1_000_001)
                    read_files += 1
                    read_bytes += len(raw)
                    if hashlib.sha256(raw).hexdigest() != digest:
                        continue
                    info = json.loads(data)
                    item = {'path': rel, 'sha256': digest}
                    item['matched_symbols'] = [symbol for symbol in info['symbols'] if symbol['name'] == query.strip()]
                    item['structure_truncated'] = info.get('structure_truncated', False)
                    item['parse_status'] = info.get('parse_status', 'unknown')
                    if related:
                        references = [r for r in info.get('references', []) if r['name'] == query]
                        item['references'] = references[:20]
                        item['indexed_reference_count'] = len(references)
                        item['references_truncated'] = len(references) > 20
                        item['is_test'] = any(p in {'test', 'tests'} for p in rel.split('/')) or rel.rsplit('/', 1)[-1].startswith('test_')
                    elif outline:
                        item.update({k: info[k] for k in ('symbols', 'imports')})
                    else:
                        lines = raw.decode('utf-8-sig').splitlines()
                        hits = [i for i, line in enumerate(lines) if any(t.casefold() in line.casefold() for t in tokens)][:4]
                        item['matches'] = [{'line': i + 1, 'text': lines[i][:350]} for i in hits]
                        item['symbols'] = info['symbols'][:12]
                    results.append(item)
                except (OSError, ValueError):
                    continue
            payload = {'results': results, 'index': {'files': len(seen), 'updated': changed,
                              'reused': reused, 'removed': len(known.keys() - seen),
                              'files_read': read_files, 'bytes_read': read_bytes,
                              'elapsed_ms': round((time.perf_counter() - started) * 1000, 2),
                              'syntax_fallback_files': db.execute('SELECT count(*) FROM files WHERE outline LIKE ?', ('%"parse_status": "syntax_error"%',)).fetchone()[0],
                              'skipped': skipped, 'partial': partial or scanned >= 30000},
                       'output_truncated': False,
                       'notice': 'Historical source index; verify files before edits. Relations are Python syntax candidates, not resolved dependencies: same-name calls may be unrelated; aliases/dynamic calls may be missed. Result limit and per-file structure caps apply.'}
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
