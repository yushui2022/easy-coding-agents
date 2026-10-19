"""Run a bounded isolated Electron check without touching the user's windows."""
import os
from pathlib import Path
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
env = dict(os.environ)
env.pop('ELECTRON_RUN_AS_NODE', None)
env['TEMP'] = env['TMP'] = 'G:/DevCache/Temp/easy-coding-agents'
result = subprocess.run([str(repo / 'desktop/node_modules/electron/dist/electron.exe'),
                         str(repo / 'benchmark/scene_browser_check.cjs'), str(Path.cwd())],
    capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=55,
    creationflags=subprocess.CREATE_NO_WINDOW)
print(result.stdout, end='')
if result.returncode:
    print(result.stderr[-4000:], file=sys.stderr, end='')
raise SystemExit(result.returncode)
