"""User-level context that applies to every project.

The desktop writes two files into its data directory and passes their paths in
the environment, so a long-running backend picks up edits on the next turn
without a restart:

    ECA_USER_PROFILE     profile.json  {"name", "role", "about", "style"}
    ECA_GLOBAL_AGENTS    AGENTS.md     free-form instructions

Both are authored by the user, which is the same trust level as a project
AGENTS.md. They steer wording and preferences; they cannot grant permissions,
change the approval mode, or override the tool layer.
"""
import json
import os
from pathlib import Path

NAME_LIMIT = 80
ROLE_LIMIT = 120
ABOUT_LIMIT = 2000
STYLE_LIMIT = 1000
INSTRUCTIONS_LIMIT = 20000
# Read the raw profile file generously: truncating the JSON itself would drop
# every field. The per-field limits are what actually bound the prompt.
PROFILE_FILE_LIMIT = 64_000


def _read_text(path, limit):
    """Bounded read that refuses links and missing files."""
    if not path:
        return ''
    try:
        target = Path(path)
        if target.is_symlink() or not target.is_file():
            return ''
        return target.read_text('utf-8', errors='replace').strip()[:limit]
    except (OSError, ValueError):
        return ''


def _profile():
    raw = _read_text(os.environ.get('ECA_USER_PROFILE'), PROFILE_FILE_LIMIT)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _field(profile, key, limit):
    value = profile.get(key)
    return value.strip()[:limit] if isinstance(value, str) else ''


def blocks():
    """Prompt blocks for the current user context; empty list when nothing is set."""
    out = []
    profile = _profile()
    lines = []
    name = _field(profile, 'name', NAME_LIMIT)
    if name:
        lines.append(f"The user prefers to be called {name}.")
    role = _field(profile, 'role', ROLE_LIMIT)
    if role:
        lines.append(f"Their role: {role}")
    about = _field(profile, 'about', ABOUT_LIMIT) or _field(profile, 'notes', ABOUT_LIMIT)
    if about:
        lines.append('About the user: ' + about)
    style = _field(profile, 'style', STYLE_LIMIT)
    if style:
        lines.append('How they want answers: ' + style)
    if lines:
        out.append('User profile (set by the user in the desktop):\n' + '\n'.join(lines))
    instructions = _read_text(os.environ.get('ECA_GLOBAL_AGENTS'), INSTRUCTIONS_LIMIT)
    if instructions:
        out.append('Global user instructions for every project (set by the user in the desktop):\n'
                   + instructions)
    return out
