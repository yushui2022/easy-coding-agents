import React,{useEffect,useRef,useState} from 'react';
import Markdown from 'react-markdown';
import {ChatCircle} from '@phosphor-icons/react';
import {EmptyState} from '../ui/EmptyState';
const invoke=window.eca.invoke;
export function SideChat({session,selection,config,onDraft}:any) {
  const [chat,setChat]=useState<any>(null),[error,setError]=useState(''),[draft,setDraft]=useState(()=>sessionStorage.getItem('eca.side.draft.'+session)||''),[sending,setSending]=useState(false);
  const current=useRef<any>(null),busy=useRef(false),composing=useRef(false),ended=useRef(0),body=useRef<HTMLDivElement>(null),follow=useRef(true);
  const [older,setOlder]=useState<any[]>([]),[cursor,setCursor]=useState<number|null>(null),[loading,setLoading]=useState(false);
  const accept=(value:any)=>{const prior=current.current;const next={...value,messages:value.messages??prior?.messages??[],stream:'stream_delta' in value?(prior?.stream||'')+value.stream_delta:value.stream};current.current=next;setChat(next);};
  useEffect(()=>{let disposed=false,timer:ReturnType<typeof setTimeout>|undefined;
    const load=async()=>{if(busy.current)return;busy.current=true;const prior=current.current;try{const value=await invoke(prior?'sidechat.snapshot':'sidechat.open',{session_id:session,id:prior?.id,selection,message_count:prior?.message_total,stream_run_id:prior?.run_id,stream_offset:prior?.stream_offset,stream_id:prior?.stream_id});if(!disposed&&current.current===prior)accept(value);}catch(e){if(!disposed)setError(String(e));}finally{busy.current=false;}};
    void load();const off=window.eca.subscribe(e=>{if(e.event==='sidechat'&&!timer)timer=setTimeout(()=>{timer=undefined;void load();},100);});
    const failure=window.eca.onFailure(e=>{setError(e);current.current=null;setChat(null);});
    return()=>{disposed=true;off();failure();clearTimeout(timer);};
  },[session]);
  useEffect(()=>{sessionStorage.setItem('eca.side.draft.'+session,draft);},[draft,session]);
  useEffect(()=>{if(follow.current&&body.current)body.current.scrollTop=body.current.scrollHeight;},[chat]);
  const act=async(method:string,extra:any={})=>{setError('');try{const v=await invoke(method,{session_id:session,id:current.current?.id,...extra});if(v.id)accept(v);return v;}catch(e){setError(String(e));return null;}};
  const send=async()=>{if(!draft.trim()||sending||chat?.busy||!chat)return;setSending(true);follow.current=true;const text=draft;try{if(await act('sidechat.send',{prompt:text}))setDraft('');}finally{setSending(false);}};
  return <section className="side-chat" aria-label="侧边聊天">
    <div className="side-context"><span>当前任务的侧边讨论 · 只读</span><button disabled={!chat||chat.busy} onClick={()=>act('sidechat.context',{selection})}>更新上下文</button>
      {chat&&<small>上下文采集于 {new Date(chat.context.captured_at*1000).toLocaleTimeString()} · {chat.context.message_count} 条主对话记录</small>}</div>
    <div className="side-messages" ref={body} onScroll={()=>{const e=body.current;follow.current=!!e&&e.scrollHeight-e.scrollTop-e.clientHeight<70;}}>
      {!chat?.messages.length&&<EmptyState icon={<ChatCircle size={25} weight="light"/>} title="在这里继续追问"><p>解释一个报错、讨论方案，或了解主任务的进展。</p><p>主任务继续运行，侧聊单独保留记录。</p></EmptyState>}
      {chat&&(cursor??chat.message_total-50)>0&&<button disabled={loading} onClick={async()=>{setLoading(true);follow.current=false;try{const v=await invoke('session.messages',{id:chat.id,before:cursor??chat.message_total-50,preview:true});setOlder(rows=>[...v.messages,...rows].slice(0,150));setCursor(v.before);}catch(e){setError(String(e));}finally{setLoading(false);}}}>加载更早的侧聊</button>}
      {[...older,...(chat?.messages||[])].filter((m:any)=>m.role==='user'||(m.role==='assistant'&&m.content)).map((m:any,i:number)=><article className="side-message" key={m.message_index??i}><strong>{m.role==='user'?'你':'ECA'}</strong><Markdown skipHtml components={{img:()=>null,a:({href,children})=><button className="text-link" onClick={()=>invoke('link.open',{url:href}).catch(e=>setError(String(e)))}>{children}</button>}}>{m.content}</Markdown>{m.role==='assistant'&&<button className="text-link" onClick={()=>onDraft('来自侧边聊天：\n'+m.content)}>放入主对话草稿</button>}</article>)}
      {chat?.busy&&<div className="side-stream" role="status">{chat.stream||'正在阅读上下文并生成回答…'}</div>}
    </div>
    {(error||chat?.error)&&<p className="workspace-error" role="alert">{error||chat.error}</p>}
    <div className="side-composer"><textarea aria-label="侧边聊天输入" placeholder="询问当前任务，不中断主对话…" value={draft} onChange={e=>setDraft(e.target.value)} onCompositionStart={()=>{composing.current=true;}} onCompositionEnd={()=>{composing.current=false;ended.current=Date.now();}} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing&&!composing.current&&Date.now()-ended.current>100){e.preventDefault();if(!e.repeat)void send();}}}/>
      <div><select aria-label="侧聊模型" value="" disabled={!chat||chat.busy} onChange={e=>act('sidechat.model',{choice:e.target.value})}><option value="">{chat?.model||'准备侧聊…'}</option>{(config.connections||[]).map((c:any)=><option value={c.id} key={c.id}>{c.name} · {c.model}</option>)}</select>{chat?.busy?<button onClick={()=>act('sidechat.cancel',{run_id:chat.run_id})}>停止侧聊</button>:<button disabled={!chat||!draft.trim()||sending} onClick={send}>发送</button>}</div>
      {chat&&<small>{chat.usage.requests} 次请求 · 费用{Object.keys(chat.usage.priced_subtotals||{}).length?Object.entries(chat.usage.priced_subtotals).map(([c,v])=>`${c} ${v}`).join(' / '):'未知'} · 已计入主会话总用量</small>}
    </div>
  </section>;
}
