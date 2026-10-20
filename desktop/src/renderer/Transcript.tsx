import {createContext,useContext} from 'react';
import {AttachmentNames} from './Attachments';
const ProjectContext=createContext<string|undefined>(undefined);
import React, {memo, useEffect, useMemo, useRef, useState} from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {CaretRight, TerminalWindow, FileText, CheckCircle, WarningCircle, Code, Circle, ListChecks, MinusCircle, Copy, Check} from '@phosphor-icons/react';
import {transcriptNodes,resultInfo,toolArgs,toolTarget,failureHint,visibleEntries,type ToolEntry} from './transcript-model';
import {AgentCards,agentsForCall,type ChildAgent} from './subagents/AgentCards';

export const RichText=memo(function RichText({text}:{text:string}) {
  return <Markdown skipHtml remarkPlugins={[remarkGfm]} components={{img:()=>null,table:({children})=><div className="markdown-table" role="region" aria-label="表格，可横向滚动" tabIndex={0}><table>{children}</table></div>,a:({href,children})=><button className="text-link" onClick={()=>href&&window.eca.invoke('link.open',{url:href}).catch(()=>{})}>{children}</button>}}>{text}</Markdown>;
});

export function LogText({text}:{text:string}) {
  const [length,setLength]=useState(8000);
  return <><pre>{text.slice(0,length)}</pre>{text.length>length&&<button className="log-more" onClick={()=>setLength(size=>size+16000)}>继续展开 · 还有 {(text.length-length).toLocaleString()} 字符</button>}</>;
}

export function LazyDetail({title,text,className=''}:{title:React.ReactNode;text:string;className?:string}) {
  const [open,setOpen]=useState(false);
  return <details className={'lazy-detail '+className} onToggle={e=>setOpen(e.currentTarget.open)}><summary>{title}</summary>{open&&<LogText text={text}/>}</details>;
}

const names:Record<string,string>={read:'读取',write:'写入',edit:'修改',edit_many:'批量修改',delete:'删除',shell:'运行命令',glob:'查找文件',grep:'搜索内容',search:'搜索代码',code_search:'搜索代码',repo_map:'项目结构',code_relations:'调用关系',delegate:'子任务',delegate_parallel:'并行任务',web_fetch:'读取网页',web_search:'搜索资料',todo:'更新计划'};
const ToolRecord=memo(function ToolRecord({entry,sessionId,root,pending,onOpen}:{entry:ToolEntry;sessionId:string;root:string;pending:boolean;onOpen:(key:string,open:boolean)=>void}) {
  const project_id=useContext(ProjectContext);
  const {call,result,source}=entry;
  const [open,setOpen]=useState(false),[full,setFull]=useState<any>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  const info=resultInfo(result,pending),target=toolTarget(call,root),hint=failureHint(entry);
  const longScript=call.function.name==='shell'&&target.text.length>160;
  const displayTarget=longScript?`脚本 · ${target.raw.split(/\r?\n/).length} 行 · ${target.raw.length.toLocaleString()} 字符`:target.text;
  const load=async()=>{
    setLoading(true);setError('');
    try {
      const [message,output]=await Promise.all([
        source.truncated?window.eca.invoke('session.message',{project_id,id:sessionId,index:source.message_index,message_ref:source.message_ref}):Promise.resolve(source),
        result?.truncated?window.eca.invoke('session.message',{project_id,id:sessionId,index:result.message_index,message_ref:result.message_ref}):Promise.resolve(result)]);
      setFull({call:message.tool_calls?.find((value:any)=>value.id===call.id)||call,result:output,
        sourceRef:source.message_ref??source,resultRef:result?.message_ref??result});
    }catch(e){setError(String(e));}finally{setLoading(false);}
  };
  // A result can arrive after the user loaded a large call's parameters. Keep it
  // live, and invalidate loaded detail if the backend's message fingerprint changes.
  const callLoaded=full&&full.sourceRef===(source.message_ref??source);
  const resultLoaded=full&&full.resultRef===(result?.message_ref??result);
  const data={call:callLoaded?full.call:call,result:resultLoaded?full.result:result};
  const needsFull=source.truncated&&!callLoaded||result?.truncated&&!resultLoaded;
  const args=toolArgs(data.call),command=typeof args.command==='string'?args.command:null;
  return <details className={'tool-record outcome-'+info.kind} onToggle={e=>{setOpen(e.currentTarget.open);onOpen(entry.key,e.currentTarget.open);}}>
    <summary><CaretRight size={12}/>{call.function.name==='shell'?<TerminalWindow size={15}/>:<FileText size={15}/>}<span className="tool-name">{names[call.function.name]||call.function.name}</span><span className="tool-target" title={target.raw}>{displayTarget||'查看执行详情'}{hint&&<small className="tool-error-hint">{hint}</small>}</span><span className="tool-outcome" title={info.hint}>{info.kind==='error'?<WarningCircle size={13}/>:info.kind==='returned'?<CheckCircle size={13}/>:info.kind==='denied'||info.kind==='stopped'?<MinusCircle size={13}/>:<Circle size={11}/>}<span>{info.label}</span></span></summary>
    {open&&<div className="tool-detail"><div className="panel-label">{command?'命令':'参数'}</div><LogText text={command??data.call.function.arguments}/>{command&&Object.keys(args).length>1&&<LazyDetail title="其他参数" text={JSON.stringify(Object.fromEntries(Object.entries(args).filter(([key])=>key!=='command')),null,2)}/>}{data.result&&<><div className="panel-label">返回结果</div><LogText text={typeof data.result.content==='string'?data.result.content:JSON.stringify(data.result.content,null,2)}/></>}
      {needsFull&&<button disabled={loading} onClick={load}>{loading?'正在加载…':'加载完整工具记录'}</button>}{error&&<p role="alert">{error}</p>}</div>}
  </details>;
});

const ExecutionGroup=memo(function ExecutionGroup({entries,sessionId,root,pending}:{entries:ToolEntry[];sessionId:string;root:string;pending:boolean}) {
  const [expanded,setExpanded]=useState(false),[pinned,setPinned]=useState<Set<string>>(()=>new Set());
  const onOpen=React.useCallback((key:string,open:boolean)=>setPinned(old=>{const next=new Set(old);if(open)next.add(key);else next.delete(key);return next;}),[]);
  const counts=new Map<string,number>();
  for(const entry of entries){const kind=resultInfo(entry.result,pending).kind;counts.set(kind,(counts.get(kind)||0)+1);}
  const visible=visibleEntries(entries,expanded,pending,pinned),hidden=entries.length-visible.length;
  const countNames:Record<string,string>={returned:'已返回',error:'失败',denied:'拒绝',stopped:'中断',pending:'待返回',unknown:'无结果'};
  return <section className="execution-group" aria-label="执行记录">
    <header className="execution-heading"><ListChecks size={15}/><strong>执行记录</strong><span className="execution-count">{entries.length} 项操作</span><div className="execution-totals">{[...counts].map(([kind,count])=><span key={kind} className={'count-'+kind}>{count} {countNames[kind]}</span>)}</div></header>
    <div className="execution-steps">{visible.map(({entry,index},i)=><React.Fragment key={entry.key}>
      {index>(visible[i-1]?.index??-1)+1&&<button className="execution-fold" onClick={()=>setExpanded(true)}><CaretRight size={12}/>{index-(visible[i-1]?.index??-1)-1} 项已返回操作已收起</button>}
      <ToolRecord entry={entry} sessionId={sessionId} root={root} pending={pending} onOpen={onOpen}/>
    </React.Fragment>)}</div>
    {(hidden>0||expanded&&entries.length>3)&&<button className="execution-toggle" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{expanded?'收起已返回操作':`查看全部 ${entries.length} 项操作`}</button>}
  </section>;
});

// Keep child entries in conversation order without wrapping them in a tool log.
function ExecutionEntries({entries,sessionId,root,pending,agents,onOpenAgent}:{entries:ToolEntry[];sessionId:string;root:string;pending:boolean;agents:ChildAgent[];onOpenAgent?:(agent:ChildAgent)=>void}) {
  const parts:React.ReactNode[]=[];
  let ordinary:ToolEntry[]=[];
  const flush=()=>{if(ordinary.length){parts.push(<ExecutionGroup key={ordinary[0].key} entries={ordinary} sessionId={sessionId} root={root} pending={pending}/>);ordinary=[];}};
  for(const entry of entries) {
    const children=onOpenAgent?agentsForCall(entry,agents):[];
    if(children.length&&onOpenAgent){flush();parts.push(<AgentCards key={entry.key} agents={children} onOpen={onOpenAgent}/>);}
    else ordinary.push(entry);
  }
  flush();
  return <>{parts}</>;
}

const CopyButton=memo(function CopyButton({text}:{text:string}) {
  const [state,setState]=useState<'idle'|'done'|'error'>('idle');
  const timer=useRef<number|undefined>(undefined);
  useEffect(()=>()=>{if(timer.current!==undefined)window.clearTimeout(timer.current);},[]);
  const copy=async()=>{
    let ok=false;
    try {ok=typeof window.eca?.copy==='function'?await window.eca.copy(text):false;} catch {ok=false;}
    setState(ok?'done':'error');
    if(timer.current!==undefined)window.clearTimeout(timer.current);
    timer.current=window.setTimeout(()=>setState('idle'),1600);
  };
  const label=state==='done'?'已复制':state==='error'?'复制失败':'复制';
  return <div className="message-actions">
    <button type="button" className={'message-copy '+state} onClick={copy} aria-label={label+'这条消息'}
      title={state==='done'?'原文已放入剪贴板':'复制这条消息的原文'}>
      {state==='done'?<Check size={13}/>:state==='error'?<WarningCircle size={13}/>:<Copy size={13}/>}
      <span>{label}</span>
    </button>
  </div>;
});
const Message=memo(function Message({message,sessionId}:{message:any;sessionId:string}) {
  const project_id=useContext(ProjectContext);
  const [full,setFull]=useState<any>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  const data=full||message;
  const more=<>{message.truncated&&!full&&<button className="log-more" disabled={loading} onClick={async()=>{setLoading(true);try{setFull(await window.eca.invoke('session.message',{project_id,id:sessionId,index:message.message_index,message_ref:message.message_ref}));}catch(e){setError(String(e));}finally{setLoading(false);}}}>{loading?'正在加载…':'加载完整消息'}</button>}{error&&<p role="alert">{error}</p>}</>;
  if(message.role==='system')return null;
  if(message.role==='tool')return <div className="orphan-tool"><LazyDetail title="工具结果 · 调用位于前页" text={String(data.content)}/>{more}</div>;
  const internal=message.role==='user'&&/^(User-requested verification command:|Repair the failed user-selected verification)/.test(message.content||'');
  if(internal)return <div className="runtime-note"><LazyDetail title={<><Code size={13}/>运行时检查与修复指令</>} text={data.content}/>{more}</div>;
  return <article className={'message '+message.role}><div className="message-label">{message.role==='user'?'你':'ECA'}{message.role==='assistant'&&<span>编码助手</span>}</div>
    {typeof data.content==='string'&&data.content&&<RichText text={data.content}/>}
    <AttachmentNames items={data.attachments}/>{more}
    {typeof data.content==='string'&&data.content.trim()&&<CopyButton text={data.content}/>}
  </article>;
});

const noAgents:ChildAgent[]=[];
export const Transcript=memo(function Transcript({messages,sessionId,projectId,root='',busy=false,agents=noAgents,onOpenAgent}:{messages:any[];sessionId:string;projectId?:string;root?:string;busy?:boolean;agents?:ChildAgent[];onOpenAgent?:(agent:ChildAgent)=>void}) {
  const nodes=useMemo(()=>transcriptNodes(messages),[messages]);
  return <ProjectContext.Provider value={projectId}>{nodes.map((node,index)=><React.Fragment key={sessionId+'-'+node.key}>
    {node.kind==='gap'?<div className="history-gap">中间 {node.count} 条记录已收起。返回最近记录后可重新加载。</div>:
      node.kind==='tools'?<ExecutionEntries entries={node.entries} sessionId={sessionId} root={root} pending={busy&&index===nodes.length-1} agents={agents} onOpenAgent={onOpenAgent}/>:
      <Message message={node.message} sessionId={sessionId}/>}</React.Fragment>)}</ProjectContext.Provider>;
});
