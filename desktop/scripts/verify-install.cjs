// Read-only installed payload verification. A successful NSIS exit alone is insufficient.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const installed=path.resolve(process.argv[2]||'G:/Apps/ECA Desktop');
const built=path.resolve(__dirname,'../../output/release/desktop/win-unpacked');
function files(folder,prefix='') {
  return fs.readdirSync(folder,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()
    ?files(path.join(folder,entry.name),path.join(prefix,entry.name)):[path.join(prefix,entry.name)]);
}
function hash(file){return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');}
async function main(){
  const paths=['ECA Desktop.exe','resources/app.asar',...['resources/backend','resources/app.asar.unpacked'].flatMap(folder=>
    fs.existsSync(path.join(built,folder))?files(path.join(built,folder)).map(p=>path.join(folder,p)):[])];
  const mismatches=paths.filter(p=>!fs.existsSync(path.join(installed,p))||hash(path.join(built,p))!==hash(path.join(installed,p)));
  if(mismatches.length)throw Error('Installed payload differs: '+mismatches.join(', '));
  const handshake=await new Promise((resolve,reject)=>{
    const child=spawn(path.join(installed,'resources/backend/eca-backend.exe'),[],{cwd:installed,windowsHide:true,stdio:'pipe'});
    let buffer='',result;
    const timer=setTimeout(()=>{child.kill();reject(Error('Backend handshake timed out'));},10000);
    child.on('error',error=>{clearTimeout(timer);reject(error);});
    child.stdout.on('data',chunk=>{
      buffer+=chunk;
      if(buffer.includes('\n')){
        try{result=JSON.parse(buffer.split('\n')[0]);child.stdin.end();}catch{reject(Error('Invalid backend reply'));}
      }
    });
    child.stderr.resume();
    child.stdin.on('error',()=>{});
    child.on('exit',code=>{clearTimeout(timer);code===0&&result?.result?.protocol===1?resolve(result.result):reject(Error('Installed backend failed to initialize'));});
    child.stdin.write(JSON.stringify({jsonrpc:'2.0',id:1,method:'initialize',params:{protocol:1}})+'\n');
  });
  console.log(JSON.stringify({installed,payload_files:paths.length,payload_hashes:'passed',handshake},null,2));
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
