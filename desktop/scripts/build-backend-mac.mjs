// Locate a Python 3.11+ interpreter and freeze the desktop backend with it.
// The Windows build leans on a locked requirements file; macOS reuses the repo
// virtualenv so the frozen bundle is built from the same sources it runs in dev.
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');
const candidates = [process.env.ECA_PYTHON, path.join(root, '.venv', 'bin', 'python'), 'python3'].filter(Boolean);
const python = candidates.find(candidate => !candidate.includes(path.sep) || fs.existsSync(candidate));
if (!python) {
  console.error('No Python found. Install Python 3.11+ or set ECA_PYTHON.');
  process.exit(1);
}
const probe = spawnSync(python, ['-c', 'import sys; print(sys.version_info[:2])'], {encoding: 'utf8'});
if (probe.status !== 0 || !/\(3, (1[1-9]|[2-9]\d)\)/.test(probe.stdout)) {
  console.error(`Python 3.11+ is required; ${python} reported: ${(probe.stdout || probe.stderr || '').trim()}`);
  process.exit(1);
}
const result = spawnSync(python, [path.join(here, 'build-backend-mac.py')], {stdio: 'inherit'});
process.exit(result.status ?? 1);
