import React,{useEffect,useRef,useState} from 'react';
import {Terminal} from '@xterm/xterm';
import {FitAddon} from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
export function TerminalPanel({id,owner,active,onDraft,onBrowser}:any) {
  const element=useRef<HTMLDivElement>(null),term=useRef<Terminal|null>(null),fit=useRef<FitAddon|null>(null),activeRef=useRef(active),tail=useRef('');const [status,setStatus]=useState('正在启动'),[error,setError]=useState(''),[link,setLink]=useState('');
  const call=(method:string,p:any={})=>window.eca.invoke(method,{owner,id,...p});activeRef.current=active;
  useEffect(()=>{
    const t=new Terminal({fontFamily:'Cascadia Mono, Consolas, monospace',fontSize:13,scrollback:5000,theme:{background:'#181b21',foreground:'#d8dee9'},allowProposedApi:false});const f=new FitAddon();t.loadAddon(f);t.open(element.current!);term.current=t;fit.current=f;
    let offset=0,disposed=false,inflight=false;
    const input=t.onData(data=>{void call('terminal.write',{data}).catch(e=>setError(String(e)));});
    const resize=t.onResize(({cols,rows})=>{void call('terminal.resize',{cols,rows}).catch(()=>{});});
    const poll=async()=>{if(disposed||inflight||!activeRef.current)return;inflight=true;try{const v=await call('terminal.read',{offset});if(disposed)return;offset=v.offset;setStatus(v.status==='running'?'PowerShell · 运行中':v.status==='starting'?'正在启动':`已退出${v.code==null?'':' · '+v.code}`);if(v.error)setError(v.error);if(v.truncated)t.write('\r\n[较早输出已截断]\r\n');tail.current=(tail.current+v.data).slice(-12000);const found=tail.current.match(/https?:\/\/(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?[^\s\x1b]*/g);if(found?.length)setLink(found[found.length-1]);if(v.data)await new Promise<void>(resolve=>t.write(v.data,resolve));}catch(e){if(!disposed)setError(String(e));}finally{inflight=false;}};
    const timer=setInterval(poll,80);void poll();return()=>{disposed=true;clearInterval(timer);input.dispose();resize.dispose();t.dispose();term.current=null;};
  },[id,owner]);
  useEffect(()=>{if(!active)return;const resize=()=>{try{fit.current?.fit();}catch{}};const observer=new ResizeObserver(resize);if(element.current)observer.observe(element.current);resize();return()=>observer.disconnect();},[active]);
  return <section className="terminal-panel"><div className="terminal-toolbar"><span>{status}</span><button onClick={()=>{void call('terminal.write',{data:'\x03'}).catch(e=>setError(String(e)));}}>中断 Ctrl+C</button><button onClick={()=>onDraft(`终端引用 · ${id} · ${new Date().toLocaleTimeString()}\n${term.current?.getSelection()||tail.current}`)}>引用输出</button></div>
    {link&&<button className="terminal-url" onClick={()=>onBrowser(link)}>在右侧浏览器打开 {link}</button>}{error&&<p className="workspace-error" role="alert">{error}</p>}<div className="terminal-canvas" ref={element}/><small>用户终端 · 本机权限 · 收起面板后继续运行</small></section>;
}
