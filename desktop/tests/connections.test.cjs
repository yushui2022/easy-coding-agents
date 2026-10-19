const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {transformSync}=require('esbuild');
const Module=require('node:module');
const source=path.resolve(__dirname,'../src/main/connections.ts');
const moduleFile=new Module(source,module);
moduleFile.filename=source;moduleFile.paths=module.paths;
moduleFile._compile(transformSync(fs.readFileSync(source,'utf8'),{loader:'ts',format:'cjs'}).code,source);
const {Connections}=moduleFile.exports;
// Test-only reversible cipher; production injects Electron safeStorage.
const cipher={isEncryptionAvailable:()=>true,encryptString:text=>Buffer.from([...text].reverse().join('')),decryptString:data=>[...data.toString()].reverse().join('')};
function setup(t,initial){
  const base=fs.existsSync('G:/')?'G:/DevCache/Temp/easy-coding-agents':os.tmpdir();
  fs.mkdirSync(base,{recursive:true});const temp=fs.mkdtempSync(path.join(base,'connections-'));
  const file=path.join(temp,'preferences.json');
  if(initial)fs.writeFileSync(file,JSON.stringify(initial));
  t.after(()=>fs.rmSync(temp,{recursive:true,force:true}));
  return {file,store:new Connections(file,cipher)};
}
const draft={name:'Primary',model:'model-a',base_url:'https://example.com/v1',api_format:'openai',api_key:'test-secret-a',persist:true};
test('DeepSeek fast default and explicit modes survive save without leaking to other providers',t=>{
  const {file,store}=setup(t);
  const id=store.save({...draft,model:'deepseek-flash'}).savedId;
  assert.equal(store.runtime(id).thinking_mode,'fast');
  store.save({...draft,id,model:'deepseek-flash',api_key:'',thinking_mode:'deep'});
  assert.equal(new Connections(file,cipher).runtime(id).thinking_mode,'deep');
  store.save({...draft,id,thinking_mode:'deep'});
  assert.equal(store.runtime(id).thinking_mode,'default');
  assert.throws(()=>store.resolve({...draft,thinking_mode:'invalid'}),/响应模式/);
});
test('legacy connection keeps ciphertext, defaults over project config, exposes no keys',t=>{
  const encryptedKey=cipher.encryptString('legacy-secret').toString('base64');
  const {file,store}=setup(t,{model:{model:'deepseek',base_url:draft.base_url,api_format:'openai'},encryptedKey,recent:[]});
  const selection=store.selection(store.choice('project'));
  assert.equal(selection.model.model,'deepseek');assert.equal(selection.model.api_key,'legacy-secret');
  assert(!JSON.stringify(store.public()).includes(encryptedKey));
  store.opened('project');assert.equal(JSON.parse(fs.readFileSync(file)).connections[0].encryptedKey,encryptedKey);
});
test('multiple keys survive restart; model rename reuses key but endpoint or protocol change does not',t=>{
  const {file,store}=setup(t);
  const a=store.save(draft).savedId;
  const b=store.save({...draft,name:'Secondary',model:'model-b',api_key:'test-secret-b'}).savedId;
  store.save({...draft,id:a,model:'renamed',api_key:''});
  assert.throws(()=>store.save({...draft,id:a,api_key:'',base_url:'https://different.example/v1'}),/重新输入/);
  assert.throws(()=>store.resolve({...draft,id:a,api_key:'',api_format:'anthropic'},false),/重新输入/);
  const resumed=new Connections(file,cipher);
  assert.equal(resumed.runtime(a).api_key,'test-secret-a');assert.equal(resumed.runtime(b).api_key,'test-secret-b');
  assert.equal(resumed.runtime(a).model,'renamed');
  assert(!fs.readFileSync(file,'utf8').includes('test-secret'));
  assert(!JSON.stringify(resumed.public()).includes('test-secret'));
});
test('explicit project choice persists and default changes do not replace pinned connections',t=>{
  const {file,store}=setup(t);const a=store.save(draft).savedId;
  const b=store.save({...draft,model:'model-b'}).savedId;
  store.remember('one',a);store.remember('two','project');store.setDefault(b);
  const resumed=new Connections(file,cipher);
  assert.equal(resumed.selection(resumed.choice('one')).connection_id,a);
  assert.deepEqual(resumed.selection(resumed.choice('two')).model,{});
  assert.equal(resumed.selection(resumed.choice('three')).connection_id,b);
  assert.throws(()=>resumed.remove(a),/被项目使用/);assert.throws(()=>resumed.remove(b),/默认模型/);
  resumed.remember('one','default');resumed.remove(a);assert.equal(resumed.public().connections.length,1);
});
test('temporary credentials expire, unavailable encryption never writes plaintext, local auth is explicit',t=>{
  const {file}=setup(t);
  const store=new Connections(file,{...cipher,isEncryptionAvailable:()=>false});
  const saved=store.save(draft);assert(saved.warning);assert.equal(store.runtime(saved.savedId).api_key,draft.api_key);
  assert(!fs.readFileSync(file,'utf8').includes(draft.api_key));
  assert.throws(()=>new Connections(file,cipher).runtime(saved.savedId),/临时密钥/);
  assert.throws(()=>store.save({...draft,no_auth:true}),/本机服务/);
  const local=store.save({...draft,no_auth:true,api_key:'',base_url:'http://localhost:11434/v1'});
  assert.equal(new Connections(file,cipher).runtime(local.savedId).api_key,'eca-local');
});
test('invalid URLs and corrupt preferences are not silently accepted or overwritten',t=>{
  const {file,store}=setup(t);
  for(const base_url of ['https://user:pass@example.com','https://example.com?key=secret','file:///tmp/model'])assert.throws(()=>store.save({...draft,base_url}));
  fs.writeFileSync(file,'{broken');assert.throws(()=>new Connections(file,cipher),/无法读取/);assert.equal(fs.readFileSync(file,'utf8'),'{broken');
});
