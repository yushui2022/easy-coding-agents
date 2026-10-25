import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {ChatCircleDots,ArrowClockwise,ArrowUp,ArrowUpLeft,CaretDown,Eye,Stop,WarningCircle} from '@phosphor-icons/react';
import {RichText} from '../Transcript';
import {ModelMenu,effortLabels} from '../ModelMenu';
import './side-chat.css';
import {useAttachments,AttachmentNames} from '../Attachments';
const invoke=window.eca.invoke;

export function SideChat({session,projectId,draftScope=session,selection,config,onDraft}:any) {
  const [chat,setChat]=useState<any>(null),[error,setError]=useState(''),[draft,setDraft]=useState(()=>sessionStorage.getItem('eca.side.draft.'+draftScope)||''),[sending,setSending]=useState(false);
  const current=useRef<any>(null),busy=useRef(false),composing=useRef(false),ended=useRef(0),body=useRef<HTMLDivElement>(null),follow=useRef(true);
  const [older,setOlder]=useState<any[]>([]),[cursor,setCursor]=useState<number|null>(null),[loading,setLoading]=useState(false);
  const [updating,setUpdating]=useState(false),[changingModel,setChangingModel]=useState(false);
  const input=useRef<HTMLTextAreaElement>(null),modelButton=useRef<HTMLButtonElement>(null);
  const [modelOpen,setModelOpen]=useState(false);
  const attachments=useAttachments('side.'+draftScope,sending||chat?.busy);
  const accept=(value:any)=>{const prior=current.current;const next={...value,messages:value.messages??prior?.messages??[],stream:'stream_delta' in value?(prior?.stream||'')+value.stream_delta:value.stream};current.current=next;setChat(next);};
  useEffect(()=>{let disposed=false,timer:ReturnType<typeof setTimeout>|undefined;
    const load=async()=>{if(busy.current)return;busy.current=true;const prior=current.current;try{const value=await invoke(prior?'sidechat.snapshot':'sidechat.open',{project_id:projectId,session_id:session,id:prior?.id,selection,message_count:prior?.message_total,stream_run_id:prior?.run_id,stream_offset:prior?.stream_offset,stream_id:prior?.stream_id});if(!disposed&&current.current===prior)accept(value);}catch(e){if(!disposed)setError(String(e));}finally{busy.current=false;}};
    void load();const off=window.eca.subscribe(e=>{if(e.event==='sidechat'&&!timer)timer=setTimeout(()=>{timer=undefined;void load();},100);});
    const failure=window.eca.onFailure(e=>{setError(e);current.current=null;setChat(null);});
    return()=>{disposed=true;off();failure();clearTimeout(timer);};
  },[session]);
  useEffect(()=>{sessionStorage.setItem('eca.side.draft.'+draftScope,draft);},[draft,session]);
  useEffect(()=>{if(follow.current&&body.current)body.current.scrollTop=body.current.scrollHeight;},[chat]);
  const act=async(method:string,extra:any={})=>{setError('');try{const v=await invoke(method,{project_id:projectId,session_id:session,id:current.current?.id,...extra});if(v.id)accept(v);return v;}catch(e){setError(String(e));return null;}};
  const send=async()=>{if((!draft.trim()&&!attachments.items.length)||attachments.reading||sending||chat?.busy||!chat||changingModel||updating)return;setSending(true);follow.current=true;const text=draft;try{if(await act('sidechat.send',{prompt:text,attachments:attachments.items})){setDraft('');await attachments.clear();}}finally{setSending(false);}};
  useLayoutEffect(()=>{if(input.current){input.current.style.height='0px';input.current.style.height=Math.min(168,Math.max(82,input.current.scrollHeight))+'px';}},[draft]);
  const refreshContext=async()=>{if(updating)return;setUpdating(true);try{await act('sidechat.context',{selection});}finally{setUpdating(false);}};
  const chooseModel=async(choice:string)=>{if(changingModel)return;setChangingModel(true);try{await act('sidechat.model',{choice});}finally{setChangingModel(false);}};
  const chooseEffort=async(effort:string)=>{if(changingModel)return false;setChangingModel(true);try{return !!await act('sidechat.reasoning',{effort});}finally{setChangingModel(false);}};
  const prompts=[['解释报错','帮我解释当前任务遇到的报错，并分析可能的原因。'],['梳理进展','梳理一下当前任务已完成的工作、待办和需要注意的问题。'],['比较方案','结合当前项目，帮我比较可选方案的取舍。']];
  const messages=[...older,...(chat?.messages||[])].filter((m:any)=>m.role==='user'||(m.role==='assistant'&&m.content));
  const empty=!messages.length&&!chat?.busy;
  const cost=Object.entries(chat?.usage?.priced_subtotals||{}).map(([c,v])=>`${c} ${v}`).join(' / ')||'未知';
  return <section className="side-chat" aria-label="侧边聊天">
    <header className="side-context">
      <div className="side-context-copy"><strong>任务上下文<span className="side-readonly"><Eye size={12}/>只读</span></strong><small>{chat?<>来自主对话的 {chat.context.message_count} 条记录<span>·</span><time>{new Date(chat.context.captured_at*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</time></>:'正在读取当前任务…'}</small></div>
      <button className={'side-refresh'+(updating?' is-updating':'')} aria-label="更新上下文" title="获取最新主对话，当前侧聊记录会保留" disabled={!chat||chat.busy||updating} onClick={refreshContext}><ArrowClockwise size={15}/><span>{updating?'更新中':'更新'}</span></button>
    </header>
    <div className={'side-messages'+(empty?' is-empty':'')} ref={body} onScroll={()=>{const e=body.current;follow.current=!!e&&e.scrollHeight-e.scrollTop-e.clientHeight<70;}}>
      {empty&&<div className="side-welcome"><span className="side-welcome-mark" aria-hidden="true"><ChatCircleDots size={29} weight="light"/></span><h2>把想法聊清楚</h2><p>围绕当前任务，讨论思路与下一步。</p><div className="side-starters">{prompts.map(([label,text])=><button key={label} onClick={()=>{setDraft(text);input.current?.focus();}}>{label}<ArrowUpLeft size={12}/></button>)}</div><small>主任务继续运行，讨论记录独立保存。</small></div>}
      {chat&&(cursor??chat.message_total-50)>0&&<button disabled={loading} onClick={async()=>{setLoading(true);follow.current=false;try{const v=await invoke('session.messages',{project_id:projectId,session_id:session,id:chat.id,before:cursor??chat.message_total-50,preview:true});setOlder(rows=>[...v.messages,...rows].slice(0,150));setCursor(v.before);}catch(e){setError(String(e));}finally{setLoading(false);}}}>加载更早的侧聊</button>}
      {messages.map((m:any,i:number)=><article className={'side-message '+m.role} key={m.message_index??i}><strong className="side-speaker">{m.role==='user'?'你':'ECA'}</strong><RichText text={m.content}/><AttachmentNames items={m.attachments}/>{m.role==='assistant'&&<button className="side-attach" onClick={()=>onDraft('来自侧边聊天：\n'+m.content)}><ArrowUpLeft size={13}/>放入主对话草稿</button>}</article>)}
      {chat?.busy&&<div className="side-stream">{chat.stream?<RichText text={chat.stream}/>:<span className="side-waiting" role="status"><span className="status-dot active"/>正在阅读上下文…</span>}</div>}
    </div>
    {(error||chat?.error)&&<p className="side-error" role="alert"><WarningCircle size={16}/>{error||chat.error}</p>}
    <footer className="side-compose-area"><div className="side-composer" {...attachments.events}>{attachments.preview}<textarea ref={input} aria-label="侧边聊天输入" placeholder="聊聊这个任务…" value={draft} onChange={e=>setDraft(e.target.value)} onCompositionStart={()=>{composing.current=true;}} onCompositionEnd={()=>{composing.current=false;ended.current=Date.now();}} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing&&!composing.current&&Date.now()-ended.current>100){e.preventDefault();if(!e.repeat)void send();}}}/>
      <div className="side-composer-toolbar">{attachments.button}<div className="side-model-menu"><button ref={modelButton} className="side-model-trigger" aria-label="侧聊模型" aria-haspopup="dialog" aria-expanded={modelOpen} disabled={!chat||chat.busy||sending} title={chat?.model} onClick={()=>setModelOpen(v=>!v)}><span className="side-model-dot"/><span>{chat?.model||'准备侧聊…'}</span><small>{effortLabels[chat?.reasoning?.value]||'默认'}</small><CaretDown size={12}/></button></div>{chat?.busy?<button className="side-stop" onClick={()=>act('sidechat.cancel',{run_id:chat.run_id})}><Stop size={12} weight="fill"/>停止侧聊</button>:<button className="side-send" aria-label="发送" title="发送 · Enter" disabled={!chat||(!draft.trim()&&!attachments.items.length)||attachments.reading||sending||changingModel||updating} onClick={send}><ArrowUp size={18}/></button>}</div>
    </div><div className="side-compose-meta">{chat?.usage?.requests>0?<span title={`费用 ${cost} · 已计入主会话总用量`}>{chat.usage.requests} 次请求<span className="side-usage-cost"> · 费用 {cost}</span></span>:<span>仅讨论与读取</span>}<span title="Enter 发送，Shift + Enter 换行"><kbd>↵</kbd> 发送<span className="side-newline"> · <kbd>Shift ↵</kbd> 换行</span></span></div></footer>
    {modelOpen&&<ModelMenu anchor={modelButton} align="start" label="侧聊模型选择" connections={config.connections||[]} recent={config.recentModels||[]} selectedId={chat?.connection_id} reasoning={chat?.reasoning} busy={!chat||chat.busy||changingModel||sending} error={error} onChoose={chooseModel} onEffort={chooseEffort} onClose={()=>setModelOpen(false)}/>}
  </section>;
}
