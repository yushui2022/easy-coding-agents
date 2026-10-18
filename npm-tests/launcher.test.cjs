'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');
const launcher = require('../bin/ecs.cjs');
const pkg = require('../package.json');
function cleanup(base) {
  const root = path.resolve(process.env.ECA_TEST_TMP || os.tmpdir());
  assert.equal(path.dirname(path.resolve(base)),root);
  assert.ok(path.basename(base).startsWith('ecs-npm-'));
  fs.rmSync(base,{recursive:true,force:true});
}
const temp = () => fs.mkdtempSync(path.join(process.env.ECA_TEST_TMP || os.tmpdir(), 'ecs-npm-'));

test('runtime location honors override and prefers G on Windows', () => {
  assert.equal(launcher.runtimeHome({ECA_RUNTIME_HOME:'custom'},'win32'),path.resolve('custom'));
  assert.equal(launcher.runtimeHome({},'win32','unused',()=>true),'G:\\DevCache\\easy-coding-agent\\runtimes');
  assert.equal(launcher.runtimeHome({XDG_CACHE_HOME:'/cache'},'linux','/home',()=>false),path.join('/cache','easy-coding-agent','runtimes'));
});
test('Python selection rejects old or missing interpreters and treats override as one executable', () => {
  const seen=[];
  const selected=launcher.findPython({ECA_PYTHON:'folder with spaces/python'},(command,args)=>{seen.push([command,args]); return {status:0};});
  assert.equal(selected.command,'folder with spaces/python');
  assert.equal(seen[0][1][0],'-I');
  assert.throws(()=>launcher.findPython({},()=>({status:1})),/Python 3.11/);
});
test('bundle checksum and path traversal are rejected', () => {
  const base=temp();
  try {
    fs.mkdirSync(path.join(base,'vendor'));
    const manifest={version:pkg.version,wheel:'runtime.whl',sha256:'0'.repeat(64)};
    const file=path.join(base,'vendor','runtime.json');
    fs.writeFileSync(file,JSON.stringify(manifest)); fs.writeFileSync(path.join(base,'vendor','runtime.whl'),'test');
    assert.throws(()=>launcher.bundledRuntime(base),/checksum/);
    manifest.sha256=crypto.createHash('sha256').update('test').digest('hex'); fs.writeFileSync(file,JSON.stringify(manifest));
    assert.equal(launcher.bundledRuntime(base).version,pkg.version);
    manifest.wheel='../outside.whl'; fs.writeFileSync(file,JSON.stringify(manifest));
    assert.throws(()=>launcher.bundledRuntime(base),/manifest/);
  } finally { cleanup(base); }
});
test('version requires neither Python nor setup/network', () => {
  const result=spawnSync(process.execPath,[path.resolve('bin/ecs.cjs'),'--version'],{encoding:'utf8',env:{...process.env,ECA_PYTHON:'missing-python'}});
  assert.equal(result.status,0); assert.equal(result.stdout.trim(),`ecs ${pkg.version}`);
});
test('launch preserves cwd, arguments and exit code, with isolated Python mode', () => {
  const base=temp();
  try {
    // A Node script impersonates Python; its -I argument is consumed by the script.
    const fake=path.join(base,'fake.cjs');
    fs.writeFileSync(fake,`console.log(JSON.stringify({cwd:process.cwd(),args:process.argv.slice(2)})); process.exit(7);`);
    const code=`const cp=require('node:child_process'); const original=cp.spawn; cp.spawn=(python,args,opts)=>original(process.execPath,[${JSON.stringify(fake)},...args],opts); require(${JSON.stringify(path.resolve('bin/ecs.cjs'))}).launch('python',['-p','spaces ; $literal','--cwd','project with spaces']);`;
    const result=spawnSync(process.execPath,['-e',code],{cwd:base,encoding:'utf8'});
    assert.equal(result.status,7);
    const value=JSON.parse(result.stdout);
    assert.equal(value.cwd,base);
    assert.deepEqual(value.args,['-I','-m','eca','-p','spaces ; $literal','--cwd','project with spaces']);
  } finally { cleanup(base); }
});
test('ready runtime is reused without interpreter discovery or setup', () => {
  const base=temp();
  try {
    const sha='a'.repeat(64), root=path.join(base,`${pkg.version}-${sha.slice(0,16)}`);
    const python=launcher.pythonIn(root);
    fs.mkdirSync(path.dirname(python),{recursive:true}); fs.writeFileSync(python,'');
    fs.writeFileSync(path.join(root,'.ecs-ready'),sha);
    const old=process.env.ECA_PYTHON;
    try { process.env.ECA_PYTHON='missing-python'; assert.equal(launcher.setup({sha256:sha},base),python); }
    finally { if (old === undefined) delete process.env.ECA_PYTHON; else process.env.ECA_PYTHON=old; }
  } finally { cleanup(base); }
});

test('executable shebang uses Unix line endings', () => {
  const bytes=fs.readFileSync(path.resolve('bin/ecs.cjs'));
  assert.ok(bytes.toString().startsWith('#!/usr/bin/env node\n'));
  assert.equal(bytes.includes(Buffer.from('\r\n')),false);
});
