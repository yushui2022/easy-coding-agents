import * as pty from 'node-pty';
// This utility process is the only native PTY owner. No model configuration enters it.
const parent=(process as any).parentPort;
let terminal:pty.IPty|undefined;
let pending='',dropped=0;
const flush=setInterval(()=>{
  if(!pending&&!dropped)return;
  parent.postMessage({type:'data',data:pending,dropped});pending='';dropped=0;
  terminal?.resume();
},30);
parent.on('message',({data:m}:any)=>{
  try {
    if(m.type==='start') {
      // Windows gets PowerShell; macOS gets a login zsh so the project terminal
      // reads the user's real PATH instead of the GUI's minimal environment.
      const shell = process.platform==='win32' ? 'powershell.exe' : (process.platform==='darwin' ? '/bin/zsh' : '/bin/sh');
      const shellArgs = process.platform==='win32' ? ['-NoLogo','-NoProfile'] : (process.platform==='darwin' ? ['-l'] : []);
      terminal=pty.spawn(shell,shellArgs,{cwd:m.cwd,env:process.env as Record<string,string>,cols:80,rows:24,name:'xterm-256color'});
      parent.postMessage({type:'ready',pid:terminal.pid});
      terminal.onData(data=>{pending+=data;if(pending.length>262144){dropped+=pending.length-262144;pending=pending.slice(-262144);}if(pending.length>131072)terminal?.pause();});
      terminal.onExit(e=>{parent.postMessage({type:'data',data:pending,dropped});pending='';parent.postMessage({type:'exit',code:e.exitCode});clearInterval(flush);process.exit(0);});
    } else if(m.type==='write')terminal?.write(m.data);
    else if(m.type==='resize')terminal?.resize(m.cols,m.rows);
    else if(m.type==='stop'){terminal?.kill();clearInterval(flush);process.exit(0);}
  } catch(e){parent.postMessage({type:'error',message:String(e)});}
});
