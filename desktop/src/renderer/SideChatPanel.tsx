import React,{useEffect,useRef,useState} from 'react';
import {PaperPlaneRight,Stop,X,ChatCircle} from '@phosphor-icons/react';
import './sidechat-panel.css';

type Message={role:string;content:any};
type Snapshot={id:string;busy:boolean;run_id:string|null;status:string;stream?:string;messages?:Message[];
  context?:{selection?:string};message_total?:number;error?:string};

// A small read-only conversation beside the session: the backend runs it in plan
// mode and denies every side effect, so asking about a selection cannot touch files.
export function SideChatPanel({session,initial,onClose}:{session:string;initial:Snapshot;onClose:()=>void}) {
  const [state,setState]=useState<Snapshot>(initial);
  const [draft,setDraft]=useState('');
  const [error,setError]=useState('');
  const [sending,setSending]=useState(false);
  const log=useRef<HTMLDivElement|null>(null);
  const id=initial.id;

  const apply=(next:Snapshot)=>setState(old=>({...old,...next}));
  const refresh=async()=>{
    try{apply(await window.eca.invoke('sidechat.snapshot',{session_id:session,id}) as Snapshot);}
    catch(err){setError(String(err));}
  };
  useEffect(()=>{
    const off=window.eca.subscribe(data=>{
      if(data.event!=='sidechat')return;
      const branch=(data as any).branch_id;
      if(branch&&branch!==id)return;
      void refresh();
    });
    return off;
  },[]);
  useEffect(()=>{if(log.current)log.current.scrollTop=log.current.scrollHeight;},[state.messages,state.stream]);

  const send=async()=>{
    const prompt=draft.trim();
    if(!prompt||sending||state.busy)return;
    setSending(true);setError('');
    try{
      apply(await window.eca.invoke('sidechat.send',{session_id:session,id,prompt}) as Snapshot);
      setDraft('');
    }catch(err){setError(String(err));} finally {setSending(false);}
  };
  const stop=async()=>{
    try{await window.eca.invoke('sidechat.cancel',{session_id:session,id,run_id:state.run_id});await refresh();}
    catch(err){setError(String(err));}
  };

  const messages=(state.messages||[]).filter(message=>['user','assistant'].includes(message.role)
    && typeof message.content==='string'&&message.content.trim());
  const selection=(state.context?.selection||'').trim();

  return <div className="sidechat-panel" role="dialog" aria-label="侧边聊天">
    <header>
      <ChatCircle size={15} weight="bold"/>
      <strong>侧边聊天</strong>
      <span className="sidechat-note">只读</span>
      <button className="sidechat-close" aria-label="关闭侧边聊天" onClick={onClose}><X size={14}/></button>
    </header>
    {!!selection&&<details className="sidechat-context"><summary>引用的选中内容 · {selection.length} 字</summary>
      <pre>{selection}</pre></details>}
    <div className="sidechat-log" ref={log}>
      {!messages.length&&!state.stream&&<p className="sidechat-hint">就选中的内容提问，不会改动项目文件。</p>}
      {messages.map((message,index)=><div key={index} className={'sidechat-message is-'+message.role}>
        <span>{message.role==='user'?'我':'侧聊'}</span>
        <p>{String(message.content)}</p>
      </div>)}
      {!!state.stream&&<div className="sidechat-message is-assistant is-live">
        <span>侧聊</span><p>{state.stream}</p></div>}
      {!!state.error&&<p className="sidechat-error">{state.error}</p>}
      {!!error&&<p className="sidechat-error">{error}</p>}
    </div>
    <div className="sidechat-composer">
      <textarea rows={2} value={draft} placeholder="就这段内容问点什么…" aria-label="侧边聊天输入"
        onChange={event=>setDraft(event.target.value)}
        onKeyDown={event=>{
          if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing){event.preventDefault();void send();}
        }}/>
      {state.busy
        ?<button type="button" className="sidechat-stop" aria-label="停止侧边聊天" onClick={()=>void stop()}><Stop size={14} weight="fill"/></button>
        :<button type="button" className="sidechat-send" aria-label="发送问题" disabled={!draft.trim()||sending}
          onClick={()=>void send()}><PaperPlaneRight size={14} weight="fill"/></button>}
    </div>
  </div>;
}
