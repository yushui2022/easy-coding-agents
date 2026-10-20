import React,{useEffect,useRef,useState} from 'react';
import {ArrowDown,ArrowLeft,ArrowClockwise,Info} from '@phosphor-icons/react';
import {Transcript,RichText} from '../Transcript';
import {AgentMark,AgentStatus,agentName,type ChildAgent} from './AgentCards';

export function AgentDetail({owner,projectId,agent,active,root,onBack}:{owner:string;projectId?:string;agent:ChildAgent;active:boolean;root:string;onBack:()=>void}) {
  const [data,setData]=useState<any>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  const [older,setOlder]=useState<any[]>([]),[cursor,setCursor]=useState<number|null>(null),[loading,setLoading]=useState(false);
  const [following,setFollowing]=useState(true);
  const current=useRef<any>(null),body=useRef<HTMLDivElement>(null),follow=useRef(true),generation=useRef(0);
  useEffect(()=>{
    const token=++generation.current;
    if(!active)return;
    let disposed=false,busy=false,again=false,timer:ReturnType<typeof setTimeout>|undefined;
    const load=async()=>{
      if(disposed)return;if(busy){again=true;return;}busy=true;
      try {
        const value=await window.eca.invoke('subagent.snapshot',{owner,id:agent.id,backend_id:current.current?.backend_id,message_revision:current.current?.message_revision});
        if(disposed)return;
        const next={...value,messages:value.messages??current.current?.messages??[]};
        current.current=next;setData(next);setError('');
      } catch(e){if(!disposed)setError(String(e));}finally{busy=false;if(again&&!disposed){again=false;schedule();}}
    };
    const schedule=()=>{if(!timer)timer=setTimeout(()=>{timer=undefined;void load();},160);};
    void load();
    const off=window.eca.subscribe(e=>{if(['subagent_live','subagent_progress','run_finished','subagent'].includes(e.event||''))schedule();});
    const failure=window.eca.onFailure(e=>{setError('后端连接已中断，保留已加载记录。'+e);setData((old:any)=>old?{...old,busy:false,status:'interrupted',stream:''}:old);});
    return()=>{disposed=true;off();failure();clearTimeout(timer);if(generation.current===token)generation.current++;};
  },[owner,agent.id,active,retry]);
  useEffect(()=>{if(active&&follow.current&&body.current)body.current.scrollTop=body.current.scrollHeight;},[data,active]);
  const loadOlder=async()=>{
    if(loading||!data)return;
    const token=generation.current;setLoading(true);follow.current=false;setFollowing(false);
    try {
      const value=await window.eca.invoke('subagent.snapshot',{owner,id:agent.id,before:cursor??data.before});
      if(generation.current!==token)return;
      setOlder(rows=>[...value.messages,...rows].slice(0,150));setCursor(value.before);
    } catch(e){if(generation.current===token)setError(String(e));}finally{setLoading(false);}
  };
  const value=data||agent;
  return <section className="agent-detail" aria-label="子 Agent 内容">
    <header className="agent-detail-header"><button className="agent-back" aria-label="返回主对话" onClick={onBack}><ArrowLeft size={17}/></button><AgentMark agent={agent}/><strong title={data?.task||agent.title}>{agent.title||agentName(agent)}</strong><span className="agent-model" title={agent.model||'沿用主模型'}>{agent.model||'沿用主模型'}</span></header>
    <div className="agent-detail-body" ref={body} onScroll={()=>{const el=body.current!;follow.current=el.scrollHeight-el.scrollTop-el.clientHeight<80;setFollowing(follow.current);}}>
      <details className="agent-assignment"><summary><Info size={13}/>任务说明<AgentStatus status={value.status}/></summary><p>{data?.task||agent.title}</p><small>{agent.mode==='plan'?'只读分析':'编码任务'} · {data?.changes_count??0} 条文件修改记录 · {agent.isolated?'隔离目录，等待主 Agent 合并':'共享项目目录'}<br/>关闭查看不会停止任务；授权在主对话中处理。</small></details>
      {error&&<div className="agent-error" role="alert"><p>{error}</p><button onClick={()=>setRetry(n=>n+1)}><ArrowClockwise size={13}/>重新加载</button></div>}
      {!data&&!error&&<div className="agent-loading" role="status">正在加载执行记录…</div>}
      {data&&<>
        {(cursor??data.before)>0&&<button className="log-more" disabled={loading} onClick={loadOlder}>{loading?'正在加载…':'加载更早的子任务记录'}</button>}
        {older.length>=150&&<p className="fine-print">较长历史已分段显示。</p>}
        <Transcript projectId={projectId} messages={[...older,...data.messages].filter(m=>m.message_index!==0||m.role!=='user')} sessionId={agent.id} root={root} busy={data.busy}/>
        {data.stream&&<div className="agent-stream" aria-label="子 Agent 正在输出"><RichText text={data.stream}/></div>}
        {data.busy&&!data.stream&&<p className="agent-waiting" role="status">子 Agent 正在处理，执行记录会自动更新。</p>}
        {!data.busy&&data.messages.length<=1&&!data.stream&&<p className="agent-waiting">此子任务尚无输出记录。</p>}
        {data.stop_reason&&<p className="agent-error">{data.stop_reason}</p>}
        {older.length>0&&<button className="log-more" onClick={()=>{setOlder([]);setCursor(null);follow.current=true;setFollowing(true);body.current?.scrollTo({top:body.current.scrollHeight});}}>返回最近记录</button>}
      </>}
    </div>
    {!following&&<button className="agent-jump" onClick={()=>{follow.current=true;setFollowing(true);body.current?.scrollTo({top:body.current.scrollHeight});}}><ArrowDown size={12}/>回到最新</button>}
  </section>;
}
