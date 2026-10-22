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

test('设备码登录：先给码，轮询到 pending，授权后把令牌加密保存', async t=>{
  const {file}=setup(t);
  const work=fakeFetch((url,init,n)=>{
    if(url.endsWith('/login/device/code'))return json({device_code:'DEV1',user_code:'ABCD-1234',verification_uri:'https://github.com/login/device',expires_in:900,interval:5});
    if(url.endsWith('/login/oauth/access_token'))return n===2?json({error:'authorization_pending'}):json({access_token:'gho_new'});
    return json({login:'me'});
  });
  const github=new GitHub(file,cipher,work,{clientId:'Iv1.abcdef123456'});
  assert.equal(github.oauthReady(),true);
  const start=await github.startDevice();
  assert.deepEqual({userCode:start.userCode,uri:start.verificationUri,interval:start.interval},{userCode:'ABCD-1234',uri:'https://github.com/login/device',interval:5});
  assert.deepEqual(await github.pollDevice(),{status:'pending'});
  const done=await github.pollDevice();
  assert.equal(done.status,'connected');
  assert.equal(done.login,'me');
  assert.equal(github.token(),'gho_new');
  const raw=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.equal(raw.login,'me');
  assert.ok(raw.encryptedToken && !raw.encryptedToken.includes('gho_new'),'device token must be encrypted at rest');
  // The device code is single use: a second poll after success cannot mint another session.
  assert.equal((await github.pollDevice()).status,'failed');
});

test('设备码登录：没有 Client ID 时不发起请求', async t=>{
  const {file}=setup(t);
  let called=false;
  const github=new GitHub(file,cipher,fakeFetch(()=>{called=true;return json({});}));
  assert.equal(github.oauthReady(),false);
  await assert.rejects(()=>github.startDevice(),/Client ID/);
  assert.equal(called,false,'no network call without a client id');
});

test('设备码登录：slow_down、过期、被拒绝和未启用都有明确结果', async t=>{
  const {file}=setup(t);
  const answers=[{error:'slow_down',interval:15},{error:'expired_token'},{error:'access_denied'}];
  const github=new GitHub(file,cipher,fakeFetch(url=>url.endsWith('/login/device/code')
    ? json({device_code:'DEV2',user_code:'WXYZ-9876',expires_in:900,interval:5})
    : json(answers.shift())),{clientId:'Iv1.abcdef123456'});
  await github.startDevice();
  assert.deepEqual(await github.pollDevice(),{status:'slow_down',interval:15});
  const expired=await github.pollDevice();
  assert.equal(expired.status,'expired');
  assert.match(expired.message,/失效|过期/);
  // An expired code is dropped: the next poll cannot keep asking GitHub.
  assert.equal((await github.pollDevice()).status,'failed');
  await github.startDevice();
  const denied=await github.pollDevice();
  assert.equal(denied.status,'denied');
  assert.match(denied.message,/取消/);

  const disabled=new GitHub(file,cipher,fakeFetch(()=>json({error:'device_flow_disabled'},400)),{clientId:'Iv1.abcdef123456'});
  await assert.rejects(()=>disabled.startDevice(),/Device Flow/);
});

test('Client ID 可以保存、覆盖，格式不对会拒绝，断开登录也不会丢', async t=>{
  const {file}=setup(t);
  const github=new GitHub(file,cipher,fakeFetch(()=>json({login:'me'})));
  assert.throws(()=>github.setClientId('not a valid id!'),/格式/);
  assert.equal(github.setClientId('Iv1.0123456789abcdef'),'Iv1.0123456789abcdef');
  assert.equal(github.oauthReady(),true);
  await github.connect('ghp_x');
  github.disconnect();
  const again=new GitHub(file,cipher,fakeFetch(()=>json({})));
  assert.equal(again.clientId(),'Iv1.0123456789abcdef','the public client id survives a disconnect');
  assert.equal(again.status().connected,false);
});

test('本机 gh 令牌可以直接登录，没有就给出提示', async t=>{
  const {file}=setup(t);
  const withToken=new GitHub(file,cipher,fakeFetch(()=>json({login:'me'})),{ghToken:async()=>'ghp_from_gh'});
  assert.equal(await withToken.ghAvailable(),true);
  const status=await withToken.connectGh();
  assert.equal(status.connected,true);
  assert.equal(withToken.token(),'ghp_from_gh');
  const bare=new GitHub(path.join(path.dirname(file),'bare.json'),cipher,fakeFetch(()=>json({})));
  assert.equal(await bare.ghAvailable(),false);
  await assert.rejects(()=>bare.connectGh(),/gh auth login/);
});
