const {test}=require('node:test');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const path=require('node:path');
test('stdio handshake rejects mismatches and handles EOF',async()=>{
  const child=spawn(process.env.ECA_PYTHON||'python',['-B','-m','eca.desktop_rpc'],{cwd:path.resolve('..'),windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
  const lines=createInterface({input:child.stdout});const output=[];
  lines.on('line',line=>output.push(JSON.parse(line)));
  child.stdin.write(JSON.stringify({jsonrpc:'2.0',id:1,method:'initialize',params:{protocol:999}})+'\n');
  child.stdin.write(JSON.stringify({jsonrpc:'2.0',id:2,method:'initialize',params:{protocol:1}})+'\n');
  const until=Date.now()+10000;
  while(output.length<2 && Date.now()<until)await new Promise(r=>setTimeout(r,20));
  assert(output.find(v=>v.id===1)?.error);
  assert.equal(output.find(v=>v.id===2)?.result.protocol,1);
  child.stdin.end();
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{child.kill();reject(new Error('EOF did not terminate backend'));},5000);child.on('exit',code=>{clearTimeout(timer);code===0?resolve():reject(new Error('backend exit '+code));});});
});
