import {utilityProcess, UtilityProcess} from 'electron';
import {randomUUID} from 'node:crypto';
import path from 'node:path';
import {execFile} from 'node:child_process';

type Term={id:string;host:UtilityProcess;pid?:number;status:string;output:string;offset:number;error:string;code?:number};
export class TerminalManager {
  terms=new Map<string,Term>();root='';
  list(){return [...this.terms.values()].map(({id,status,error,code})=>({id,status,error,code}));}
  get(id:string){const t=this.terms.get(id);if(!t)throw new Error('终端已关闭');return t;}
  async close(id:string) {
    const t=this.get(id);
    // Only terminate a PID received from our own living host, never a renderer-supplied PID.
    if(process.platform==='win32'&&t.host.pid&&t.status!=='exited')await new Promise<void>(resolve=>execFile('taskkill',['/pid',String(t.host.pid),'/T','/F'],{windowsHide:true,timeout:5000},()=>resolve()));
    t.host.kill();this.terms.delete(id);
  }
  async closeAll(){await Promise.all([...this.terms.keys()].map(id=>this.close(id)));}
  async action(method:string,p:any) {
    if(method==='terminal.list')return this.list();
    if(!this.root)throw new Error('请先打开项目');
    if(method==='terminal.create') {
      if(this.terms.size>=4)throw new Error('请先关闭不用的终端（最多 4 个）');
      const env:Record<string,string>={};
      for(const [k,v] of Object.entries(process.env))if(v&&!/KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL/i.test(k)&&!/^ECA_/i.test(k))env[k]=v;
      const host=utilityProcess.fork(path.join(__dirname,'terminal-host.cjs'),[],{env,serviceName:'ECA project terminal',stdio:'pipe'});
      const t:Term={id:randomUUID(),host,status:'starting',output:'',offset:0,error:''};this.terms.set(t.id,t);
      host.stdout?.on('data',()=>{});host.stderr?.on('data',()=>{});
      host.on('message',(m:any)=>{
        if(m.type==='ready'){t.pid=m.pid;t.status='running';}
        if(m.type==='data'){
          const s=(m.dropped?'\r\n[部分终端输出已截断]\r\n':'')+m.data;t.output+=s;
          if(t.output.length>262144){const n=t.output.length-262144;t.output=t.output.slice(n);t.offset+=n;}
        }
        if(m.type==='error')t.error=m.message;
        if(m.type==='exit'){t.status='exited';t.code=m.code;}
      });
      host.on('exit',()=>{t.status='exited';});host.postMessage({type:'start',cwd:this.root});return {id:t.id};
    }
    const t=this.get(p.id);
    if(method==='terminal.read'){
      const offset=Number.isSafeInteger(p.offset)&&p.offset>=0?p.offset:0;
      const start=Math.max(t.offset,offset),data=t.output.slice(start-t.offset,start-t.offset+65536);
      return {data,offset:start+data.length,truncated:offset<t.offset,status:t.status,error:t.error,code:t.code};
    }
    if(method==='terminal.write'){
      if(t.status!=='running'||typeof p.data!=='string'||p.data.length>65536)throw new Error('终端尚未就绪或输入过长');
      t.host.postMessage({type:'write',data:p.data});return true;
    }
    if(method==='terminal.resize'){
      if(!Number.isInteger(p.cols)||!Number.isInteger(p.rows)||p.cols<2||p.cols>500||p.rows<1||p.rows>300)throw new Error('无效的终端尺寸');
      t.host.postMessage({type:'resize',cols:p.cols,rows:p.rows});return true;
    }
    if(method==='terminal.close'){await this.close(p.id);return true;}
    throw new Error('不支持的终端操作');
  }
}
