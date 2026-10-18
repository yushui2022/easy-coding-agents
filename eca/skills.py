"""Bounded local workflow discovery. Skills never grant tool permissions."""
import os
from pathlib import Path
import re


class Skills:
    def __init__(self, root):
        self.root = root

    def catalog(self):
        found = {}
        user = Path(os.environ.get('ECS_SKILLS_DIR', str(Path.home() / '.ecs' / 'skills')))
        for scope, folder in [('user', user), ('project', self.root / '.agents' / 'skills')]:
            if not folder.is_dir() or folder.is_symlink():
                continue
            if scope == 'project' and not folder.resolve().is_relative_to(self.root.resolve()):
                continue
            for item in sorted(folder.iterdir())[:100]:
                path = item / 'SKILL.md'
                if (not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', item.name) or item.is_symlink()
                        or path.is_symlink() or not path.is_file() or path.stat().st_size > 32000):
                    continue
                try:
                    text = path.read_text('utf-8')
                except (OSError, UnicodeError):
                    continue
                description = next((line.split(':', 1)[1].strip().strip('\"\'') for line in text.splitlines()[:30]
                                    if line.startswith('description:')), '')
                found[item.name] = {'name': item.name, 'scope': scope, 'description': description[:300], 'path': str(path)}
        return found

    def load(self, name):
        entry = self.catalog().get(name)
        if not entry:
            raise ValueError('Unknown skill; use skills to list available names')
        return f"Local workflow {name} ({entry['scope']}). User instructions and tool permissions take precedence.\n" + Path(entry['path']).read_text('utf-8')
