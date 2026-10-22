"""Build the Windows onedir backend using the locked desktop build environment.

The backend is a second executable that ships inside the product, so it gets the
same identity as the app: the ECA icon plus Windows version metadata. Without them
Windows shows it as an anonymous "eca-backend" with a default PyInstaller icon,
which reads like a stray process next to the app it belongs to.
"""
from pathlib import Path
import os
import re
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

version = re.search(r'__version__\s*=\s*"([^"]+)"', (root/'eca/__init__.py').read_text(encoding='utf-8')).group(1)
parts = (version.split('.') + ['0', '0', '0', '0'])[:4]
numbers = ', '.join(str(int(digits)) if digits.isdigit() else '0' for digits in parts)
# PyInstaller reads this file as a Python expression; it must stay plain ASCII.
version_file = cache/'eca-backend-version.txt'
version_file.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({numbers}), prodvers=({numbers}), mask=0x3f, flags=0x0,
    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'ECA contributors'),
        StringStruct('FileDescription', 'ECA Desktop backend runtime'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', 'eca-backend'),
        StringStruct('OriginalFilename', 'ECA Desktop Backend.exe'),
        StringStruct('ProductName', 'ECA Desktop'),
        StringStruct('ProductVersion', '{version}'),
        StringStruct('LegalCopyright', 'MIT License')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding='ascii')

subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--console',
    '--name', 'eca-backend', '--paths', str(root), '--distpath', str(desktop/'runtime'),
    '--workpath', str(cache/'pyinstaller-work'), '--specpath', str(cache),
    '--icon', str(resources/'icon.ico'), '--version-file', str(version_file),
    '--collect-submodules', 'eca', '--collect-submodules', 'agent_memory_core',
    '--collect-submodules', 'mcp.client', '--collect-submodules', 'mcp.shared', '--collect-data', 'mcp',
    '--hidden-import', 'mcp.types', '--collect-all', 'jsonschema', '--collect-all', 'jsonschema_specifications',
    '--collect-data', 'certifi', str(desktop/'scripts/backend-entry.py')], cwd=root, env=env, check=True)

# Windows shows the process name from the file name, so the runtime is renamed to
# the product. The bootloader still finds `_internal` because it sits alongside.
built = desktop/'runtime'/'eca-backend'/'eca-backend.exe'
renamed = desktop/'runtime'/'eca-backend'/'ECA Desktop Backend.exe'
if built.exists():
    if renamed.exists():
        renamed.unlink()
    built.rename(renamed)
    print(f'renamed {built.name} -> {renamed.name}')
