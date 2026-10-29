"""Build the macOS onedir backend that ships inside ECA Desktop.

The Windows build (scripts/build-runtime.py) attaches an .ico and VSVersionInfo
because Windows shows both. macOS needs neither: the app bundle carries the
identity, and the backend is only ever spawned with piped stdio. So this script
keeps the same PyInstaller layout and only changes the icons/metadata steps.

Run it with the repository virtualenv so the frozen bundle matches the sources:

    ../.venv/bin/python scripts/build-backend-mac.py

Output: desktop/runtime/eca-backend/eca-backend (+ _internal/), which
electron-builder copies to Contents/Resources/backend via extraResources.
"""
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
desktop = root / 'desktop'
runtime = desktop / 'runtime'
cache = root / 'output' / 'build-cache'
cache.mkdir(parents=True, exist_ok=True)

entry = desktop / 'scripts' / 'backend-entry.py'
if not entry.exists():
    sys.exit(f'missing backend entry: {entry}')

args = [
    sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--console',
    '--name', 'eca-backend',
    '--paths', str(root),
    '--distpath', str(runtime),
    '--workpath', str(cache / 'pyinstaller-work'),
    '--specpath', str(cache),
    '--collect-submodules', 'eca',
    '--collect-submodules', 'agent_memory_core',
    '--collect-all', 'jsonschema',
    '--collect-all', 'jsonschema_specifications',
    '--collect-data', 'certifi',
    str(entry),
]

# MCP is an optional dependency; only freeze it when the build environment has it.
try:
    import mcp  # noqa: F401
except ImportError:
    print('mcp not installed: building without the optional MCP bridge')
else:
    args[args.index('--collect-all'):args.index('--collect-all')] = [
        '--collect-submodules', 'mcp.client',
        '--collect-submodules', 'mcp.shared',
        '--collect-data', 'mcp',
        '--hidden-import', 'mcp.types',
    ]

if (runtime / 'eca-backend').exists():
    shutil.rmtree(runtime / 'eca-backend')

subprocess.run(args, cwd=root, check=True)

built = runtime / 'eca-backend' / 'eca-backend'
if not built.exists():
    sys.exit(f'PyInstaller did not produce {built}')
built.chmod(0o755)
size = sum(p.stat().st_size for p in (runtime / 'eca-backend').rglob('*') if p.is_file())
print(f'built {built} ({size / 1024 / 1024:.1f} MB)')
