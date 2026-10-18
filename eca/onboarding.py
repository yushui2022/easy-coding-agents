"""Explicit first-run configuration. Existing project configuration is preserved."""
import getpass
import json
import os
from pathlib import Path
import re
import subprocess

from .config import Settings


def configure(root, ask=input, secret=getpass.getpass, emit=print):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('Project directory does not exist')
    config, dotenv, ignore = (root/name for name in ('eca.toml', '.env', '.gitignore'))
    if config.exists() or config.is_symlink():
        raise ValueError('eca.toml already exists; edit it directly. No configuration was overwritten.')
    if dotenv.is_symlink() or ignore.is_symlink():
        raise ValueError('Configuration paths must not be symbolic links')
    emit('Configure one API for this project. No network request is made.')
    protocol = ask('Protocol [openai / responses / anthropic] (openai): ').strip() or 'openai'
    default_url = 'https://api.anthropic.com/v1' if protocol == 'anthropic' else 'https://api.openai.com/v1'
    base_url = ask(f'API base URL ({default_url}): ').strip() or default_url
    model = ask('Model ID: ').strip()
    variable = ask('API key environment variable (ECA_API_KEY): ').strip() or 'ECA_API_KEY'
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', variable):
        raise ValueError('Enter an environment variable name, not an API key')
    Settings(root, model=model, base_url=base_url, api_format=protocol).validate()
    key = ''
    if not dotenv.exists() and not os.environ.get(variable):
        key = secret('API key (hidden; Enter to configure it later via the environment): ').strip()
        if any(ord(c) < 32 for c in key):
            raise ValueError('API key must be a single line')
    if key:
        try:
            tracked = subprocess.run(['git', 'ls-files', '--', '.env'], cwd=root, capture_output=True, timeout=5)
            if tracked.returncode == 0 and tracked.stdout.strip():
                raise ValueError('.env is tracked by Git; use an environment variable instead of saving a key')
        except FileNotFoundError:
            pass
    emit('Will create eca.toml' + (' and .env (plaintext secret), and add .env/.eca to .gitignore.' if key else '. Existing .env is preserved.'))
    if ask('Save configuration? [y/N]: ').strip().lower() not in {'y', 'yes'}:
        emit('Cancelled; no files written.')
        return False
    # Exclusive creation protects against another process creating configuration
    # during the interactive prompts. Never truncate an existing credential file.
    if key:
        current = ignore.read_text('utf-8') if ignore.exists() else ''
        with ignore.open('a', encoding='utf-8') as stream:
            stream.write(('\n' if current and not current.endswith('\n') else '') + '\n# ECA private project data\n.env\n.eca/\n')
        fd = os.open(dotenv, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            escaped = key.replace('\\', '\\\\').replace("'", "\\'")
            stream.write(f"{variable}='{escaped}'\n")
    with config.open('x', encoding='utf-8') as stream:
        stream.write('[agent]\n' + ''.join(f'{k} = {json.dumps(v, ensure_ascii=False)}\n' for k, v in
                     [('api_format', protocol), ('base_url', base_url), ('model', model), ('api_key_env', variable)]))
    emit(f'Configuration saved. Set {variable} in your environment if needed; run ecs --doctor to check it.')
    emit('For an explicit API request (may incur cost), run ecs --doctor --check-api. Environment overrides still take precedence.')
    return True
