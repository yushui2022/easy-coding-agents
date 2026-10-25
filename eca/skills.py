"""Bounded local workflow discovery. Skills never grant tool permissions.

Several agents on this machine already keep skills as ``<name>/SKILL.md``. This
catalog reads those folders too, so a skill installed for Codex or Claude is
available here without copying anything. Read-only: nothing is written, moved or
re-labelled in the other tools' folders.
"""
import os
from pathlib import Path
import re

MAX_SKILL_BYTES = 32000
MAX_PER_FOLDER = 100
NAME = re.compile(r'[a-zA-Z0-9_-]{1,64}')
# Later entries lose to earlier ones on a name clash, so a project skill beats a
# shared one and ECA's own folder beats another tool's.
SOURCES = ('project', 'eca', 'codex', 'claude', 'workbuddy')


def folders(root=None):
    home = Path(os.path.expanduser('~'))
    return {
        'project': (Path(root) / '.agents' / 'skills') if root else None,
        'eca': Path(os.environ.get('ECS_SKILLS_DIR') or home / '.ecs' / 'skills'),
        'codex': Path(os.environ.get('ECA_CODEX_HOME') or home / '.codex') / 'skills',
        'claude': Path(os.environ.get('ECA_CLAUDE_HOME') or home / '.claude') / 'skills',
        'workbuddy': Path(os.environ.get('ECA_WORKBUDDY_HOME') or home / '.workbuddy') / 'skills',
    }


# Stat key -> catalog. Reading the files is the expensive part, so an unchanged
# set of (path, size, mtime) reuses the previous result.
_CACHE = {}

class Skills:
    def __init__(self, root=None):
        self.root = Path(root) if root else None

    def catalog(self):
        """Metadata for every readable skill, cached until the folders change.

        Reading and even statting 46 small files costs about 60 ms on this machine
        and this runs on every request, so the key is the set of skill-folder mtimes:
        adding, removing or renaming a skill invalidates it immediately. Editing the
        description inside an existing SKILL.md is picked up after a restart, while
        load() below always reads the current body.
        """
        base = self.root.resolve() if self.root else None
        usable = []
        for source, folder in folders(self.root).items():
            if folder is None or not folder.is_dir() or folder.is_symlink():
                continue
            if source == 'project' and (base is None or not folder.resolve().is_relative_to(base)):
                continue
            try:
                usable.append((source, folder, folder.stat().st_mtime_ns))
            except OSError:
                continue
        key = tuple((source, str(folder), stamp) for source, folder, stamp in usable)
        cached = _CACHE.get(key)
        if cached is not None:
            return {name: dict(entry) for name, entry in cached.items()}
        found = {}
        for source, folder, _ in usable:
            try:
                items = sorted(folder.iterdir())[:MAX_PER_FOLDER]
            except OSError:
                continue
            for item in items:
                if item.name in found or not NAME.fullmatch(item.name) or item.is_symlink():
                    continue
                path = item / 'SKILL.md'
                if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SKILL_BYTES:
                    continue
                try:
                    text = path.read_text('utf-8')
                except (OSError, UnicodeError):
                    continue
                description = next((line.split(':', 1)[1].strip().strip('\"\'') for line in text.splitlines()[:30]
                                    if line.startswith('description:')), '')
                found[item.name] = {'name': item.name, 'source': source,
                                    'scope': 'project' if source == 'project' else 'user',
                                    'description': description[:300], 'path': str(path)}
        if len(_CACHE) >= 8:
            _CACHE.clear()
        _CACHE[key] = found
        return {name: dict(entry) for name, entry in found.items()}

    def load(self, name):
        entry = self.catalog().get(name)
        if not entry:
            raise ValueError('Unknown skill; use skills to list available names')
        where = '' if entry['source'] == 'eca' else f", installed for {entry['source']}"
        return (f"Local workflow {name} ({entry['scope']}{where}). User instructions and tool permissions take "
                f"precedence.\n" + Path(entry['path']).read_text('utf-8'))

    def read(self, name, limit=4000):
        entry = self.catalog().get(name)
        if not entry:
            raise ValueError('Unknown skill')
        text = Path(entry['path']).read_text('utf-8', errors='replace')
        return {'name': name, 'source': entry['source'], 'description': entry['description'],
                'text': text[:limit], 'truncated': len(text) > limit}
