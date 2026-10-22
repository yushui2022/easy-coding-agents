const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {transformSync}=require('esbuild');
const Module=require('node:module');
const source=path.resolve(__dirname,'../src/main/github.ts');
const moduleFile=new Module(source,module);
moduleFile.filename=source;moduleFile.paths=module.paths;
moduleFile._compile(transformSync(fs.readFileSync(source,'utf8'),{loader:'ts',format:'cjs'}).code,source);
const {GitHub}=moduleFile.exports;

// Test-only reversible cipher; production injects Electron safeStorage.
const cipher={isEncryptionAvailable:()=>true,encryptString:text=>Buffer.from([...text].reverse().join('')),
  decryptString:data=>[...data.toString()].reverse().join('')};
const noEncryption={...cipher,isEncryptionAvailable:()=>false};

function setup(t){
  const base=fs.existsSync('G:/')?'G:/DevCache/Temp/easy-coding-agents':os.tmpdir();
  fs.mkdirSync(base,{recursive:true});
  const temp=fs.mkdtempSync(path.join(base,'github-'));
  t.after(()=>fs.rmSync(temp,{recursive:true,force:true}));
  return {file:path.join(temp,'github.json'),temp};
}
const json=(body,status=200)=>({ok:status>=200&&status<300,status,text:async()=>JSON.stringify(body)});
function fakeFetch(handler){const calls=[];const impl=async(url,init)=>{calls.push({url,init});return handler(url,init,calls.length);};
  impl.calls=calls;return impl;}

test('连接失败时不写入令牌', async t=>{
  const {file}=setup(t);
  const github=new GitHub(file,cipher,fakeFetch(()=>json({message:'Bad credentials'},401)));
  await assert.rejects(()=>github.connect('ghp_bad'),/拒绝/);
  assert.equal(fs.existsSync(file),false);
  assert.equal(github.status().connected,false);
});

test('系统加密不可用时拒绝保存', async t=>{
  const {file}=setup(t);
  let called=false;
  const github=new GitHub(file,noEncryption,fakeFetch(()=>{called=true;return json({login:'x'});}));
  await assert.rejects(()=>github.connect('ghp_x'),/系统加密/);
  assert.equal(called,false,'no network call when the token cannot be stored');
});

test('成功连接后令牌加密保存，状态只暴露账号名', async t=>{
  const {file}=setup(t);
  const github=new GitHub(file,cipher,fakeFetch(()=>json({login:'yushui2022'})));
  const status=await github.connect('  ghp_secret  ');
  assert.equal(status.connected,true);
  assert.equal(status.login,'yushui2022');
  assert.equal(status.encrypted,true);
  const raw=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.equal(raw.login,'yushui2022');
  assert.ok(raw.encryptedToken && !raw.encryptedToken.includes('ghp_secret'),'token must not be stored in clear text');
  assert.equal(JSON.stringify(status).includes('ghp_secret'),false);
  // A second instance must decrypt with the same cipher.
  const again=new GitHub(file,cipher,fakeFetch(()=>json({})));
  assert.equal(again.token(),'ghp_secret');
});

test('仓库列表被裁剪成需要的字段并过滤坏行', async t=>{
  const {file}=setup(t);
  const github=new GitHub(file,cipher,fakeFetch(url=>url.endsWith('/user')?json({login:'me'})
    :json([{full_name:'a/b',private:true,description:'d',updated_at:'2026-01-01',default_branch:'main'},
           {full_name:12},{description:'no name'}])));
  await github.connect('ghp_x');
  const repos=await github.repos();
  assert.equal(repos.length,1);
  assert.deepEqual(repos[0],{full_name:'a/b',private:true,description:'d',updated_at:'2026-01-01',
    default_branch:'main',clone_url:'https://github.com/a/b.git'});
});

test('未连接时读取仓库给出明确错误', async t=>{
  const {file}=setup(t);
  const github=new GitHub(file,cipher,fakeFetch(()=>json({})));
  await assert.rejects(()=>github.repos(),/先连接/);
});

test('断开连接后清空文件与状态', async t=>{
  const {file}=setup(t);
  const github=new GitHub(file,cipher,fakeFetch(()=>json({login:'me'})));
  await github.connect('ghp_x');
  const status=github.disconnect();
  assert.equal(status.connected,false);
  assert.equal(github.token(),undefined);
  assert.deepEqual(JSON.parse(fs.readFileSync(file,'utf8')),{});
});

test('克隆前拒绝非法仓库名和已存在的目录', async t=>{
  const {file,temp}=setup(t);
  const github=new GitHub(file,cipher,fakeFetch(()=>json({login:'me'})));
  await github.connect('ghp_x');
  await assert.rejects(()=>github.clone('../../etc',temp),/不合法/);
  fs.mkdirSync(path.join(temp,'repo'));
  fs.writeFileSync(path.join(temp,'repo','a.txt'),'x');
  await assert.rejects(()=>github.clone('owner/repo',temp),/已存在且非空/);
});
