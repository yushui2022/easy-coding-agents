"""Build the Windows onedir backend using the locked desktop build environment."""
from pathlib import Path
import os
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
desktop = root / 'desktop'
cache = Path('G:/DevCache/Temp/easy-coding-agents') if Path('G:/').exists() else root/'output'/'build-cache'
cache.mkdir(parents=True, exist_ok=True)
env = {**os.environ, 'TEMP': str(cache), 'TMP': str(cache), 'PYINSTALLER_CONFIG_DIR': str(cache/'pyinstaller-cache')}
from PIL import Image
resources = desktop/'resources'
resources.mkdir(exist_ok=True)
with Image.open(root/'docs/assets/eca-logo-v1.png') as image:
    image.save(resources/'icon.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--console',
    '--name', 'eca-backend', '--paths', str(root), '--distpath', str(desktop/'runtime'),
    '--workpath', str(cache/'pyinstaller-work'), '--specpath', str(cache),
    '--collect-submodules', 'eca', '--collect-submodules', 'agent_memory_core',
    '--collect-submodules', 'mcp.client', '--collect-submodules', 'mcp.shared', '--collect-data', 'mcp',
    '--hidden-import', 'mcp.types', '--collect-all', 'jsonschema', '--collect-all', 'jsonschema_specifications',
    '--collect-data', 'certifi', str(desktop/'scripts/backend-entry.py')], cwd=root, env=env, check=True)
