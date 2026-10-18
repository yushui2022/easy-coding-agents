#!/usr/bin/env node
'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawn, spawnSync} = require('node:child_process');
const pkg = require('../package.json');

function runtimeHome(env = process.env, platform = process.platform, home = os.homedir(), exists = fs.existsSync) {
  if (env.ECA_RUNTIME_HOME) return path.resolve(env.ECA_RUNTIME_HOME);
  if (platform === 'win32' && exists('G:\\')) return 'G:\\DevCache\\easy-coding-agent\\runtimes';
  return path.join(platform === 'win32' ? (env.LOCALAPPDATA || home) : (env.XDG_CACHE_HOME || path.join(home, '.cache')), 'easy-coding-agent', 'runtimes');
}
function pythonIn(root, platform = process.platform) {
  return path.join(root, platform === 'win32' ? 'Scripts' : 'bin', platform === 'win32' ? 'python.exe' : 'python');
}
function findPython(env = process.env, run = spawnSync) {
  const candidates = env.ECA_PYTHON ? [[env.ECA_PYTHON]] : (process.platform === 'win32' ? [['python'], ['py', '-3'], ['python3']] : [['python3'], ['python']]);
  for (const [command, ...prefix] of candidates) {
    const result = run(command, [...prefix, '-I', '-c', 'import sys, venv, ensurepip; sys.exit(0 if sys.version_info >= (3,11) else 1)'], {stdio:'ignore', timeout:10000, windowsHide:true});
    if (!result.error && result.status === 0) return {command, prefix};
  }
  throw new Error('Python 3.11+ is required. Install Python with venv support, or set ECA_PYTHON to its executable path.');
}
function bundledRuntime(base = path.resolve(__dirname, '..')) {
  const manifest = JSON.parse(fs.readFileSync(path.join(base, 'vendor', 'runtime.json'), 'utf8'));
  if (manifest.version !== pkg.version || !/^[A-Za-z0-9_.-]+\.whl$/.test(manifest.wheel) || !/^[a-f0-9]{64}$/.test(manifest.sha256)) throw new Error('Invalid bundled runtime manifest');
  const wheel = path.join(base, 'vendor', manifest.wheel);
  if (crypto.createHash('sha256').update(fs.readFileSync(wheel)).digest('hex') !== manifest.sha256) throw new Error('Bundled runtime checksum mismatch; reinstall this npm package.');
  return {...manifest, wheel};
}
function checked(command, args, env = process.env) {
  const result = spawnSync(command, args, {stdio:'inherit', windowsHide:true, env});
  if (result.error || result.status !== 0) throw new Error('Runtime setup failed. Check Python/network access and run ecs --setup again.');
}
function setup(manifest, home = runtimeHome()) {
  const root = path.join(home, `${pkg.version}-${manifest.sha256.slice(0,16)}`);
  const python = pythonIn(root), ready = path.join(root, '.ecs-ready');
  if (fs.existsSync(python) && fs.existsSync(ready) && fs.readFileSync(ready, 'utf8') === manifest.sha256) return python;
  const selected = findPython();
  fs.mkdirSync(home, {recursive:true});
  const lock = root + '.lock';
  try { fs.mkdirSync(lock); } catch (error) {
    if (error.code === 'EEXIST') throw new Error(`Runtime setup is already locked: ${lock}. Wait for the other setup; after a crash, confirm it stopped before removing this lock directory.`);
    throw error;
  }
  try {
    console.error(`[ecs] Preparing Python runtime in ${root}. First launch installs Python dependencies.`);
    const temp = path.join(home, 'tmp');
    fs.mkdirSync(temp, {recursive:true});
    const env = {...process.env, TEMP:temp, TMP:temp, TMPDIR:temp};
    checked(selected.command, [...selected.prefix, '-I', '-m', 'venv', root], env);
    checked(python, ['-I', '-m', 'pip', 'install', '--disable-pip-version-check', '--cache-dir', path.join(home, 'pip-cache'), manifest.wheel], env);
    fs.writeFileSync(ready + '.tmp', manifest.sha256);
    fs.renameSync(ready + '.tmp', ready);
    return python;
  } finally { fs.rmdirSync(lock); }
}
function launch(python, args) {
  // Isolated mode prevents a project-local eca.py/PYTHONPATH from replacing the installed CLI.
  const child = spawn(python, ['-I', '-m', 'eca', ...args], {stdio:'inherit', windowsHide:false});
  const interrupt = () => {}; // Terminal Ctrl+C already reaches the child; let its cleanup finish.
  const terminate = () => child.kill('SIGTERM');
  process.on('SIGINT', interrupt);
  process.on('SIGTERM', terminate);
  child.on('error', () => { console.error('[ecs] Cannot start the Python runtime. Run ecs --setup.'); process.exitCode = 1; });
  child.on('close', (code, signal) => {
    process.removeListener('SIGINT', interrupt);
    process.removeListener('SIGTERM', terminate);
    process.exitCode = code ?? (signal === 'SIGINT' ? 130 : 1);
  });
}
function main(args = process.argv.slice(2)) {
  if (args.length === 1 && (args[0] === '--version' || args[0] === '-v')) { console.log(`ecs ${pkg.version}`); return; }
  const manifest = bundledRuntime();
  const python = setup(manifest);
  if (args.length === 1 && args[0] === '--setup') { console.log(`[ecs] Ready: ${python}`); return; }
  launch(python, args);
}
module.exports = {runtimeHome, pythonIn, findPython, bundledRuntime, setup, launch};
if (require.main === module) {
  try { main(); } catch (error) { console.error(`[ecs] ${error.message}`); process.exitCode = 1; }
}
