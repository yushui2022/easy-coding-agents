import React,{useEffect,useMemo,useState} from 'react';
import {ArrowLeft,Clock,Files} from '@phosphor-icons/react';
import {Dialog} from './Dialog';
import './external-history.css';

// Read-only: these transcripts belong to other tools. Nothing here writes to
// their folders, imports a session, or resumes one.
const labels:Record<string,string>={codex:'Codex',claude:'Claude',workbuddy:'WorkBuddy'};

const clock=(seconds:number)=>{
  if(!seconds)return '';
  const date=new Date(seconds*1000);
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')} ${String(date.getHours()).padStart(2,'0')}:${String(date.getMinutes()).padStart(2,'0')}`;
};
const size=(bytes:number)=>bytes>1048576?`${(bytes/1048576).toFixed(1)} MB`:`${Math.max(1,Math.round(bytes/1024))} KB`;

export function ExternalHistory({onClose,projectId,onImported}:{onClose:()=>void;projectId?:string;onImported?:(sessionId:string)=>void|Promise<void>}) {
  const [rows,setRows]=useState<any[]|null>(null);
  const [error,setError]=useState('');
  const [filter,setFilter]=useState('all');
  const [picked,setPicked]=useState<any>(null);
  const [view,setView]=useState<any>(null);
  const [loading,setLoading]=useState(false);

  useEffect(()=>{
    let alive=true;
    void (async()=>{
      try {
        const result=await window.eca.invoke('external.sessions',{limit:300});
        if(alive)setRows(result?.sessions||[]);
      } catch(reason){
        if(alive){setError(String(reason));setRows([]);}
      }
    })();
    return()=>{alive=false;};
  },[]);

  const pick=async(row:any)=>{
    setPicked(row);setView(null);setLoading(true);setError('');
    try {setView(await window.eca.invoke('external.session',{source:row.source,id:row.id}));}
    catch(reason){setError(String(reason));}
    finally {setLoading(false);}
  };

  // Import copies text into a NEW ECA session. The foreign tool calls are not
  // replayed: they never ran here, and their pairing does not exist in ECA.
  const importSession=async()=>{
    if(!picked)return;
    setLoading(true);setError('');
    try {
      const result=await window.eca.invoke('external.import',{source:picked.source,id:picked.id,title:picked.title});
      onImported?.(result?.session_id||'');
    } catch(reason){setError(String(reason));}
    finally {setLoading(false);}
  };

  const counts=useMemo(()=>{
    const map:Record<string,number>={};
    for(const row of rows||[])map[row.source]=(map[row.source]||0)+1;
    return map;
  },[rows]);
  const visible=(rows||[]).filter(row=>filter==='all'||row.source===filter);

  return <Dialog title="其他工具的历史会话" closeLabel="关闭其他工具历史" wide className="external-history" onClose={onClose}>
    <p className="external-note">只读取本机 Codex、Claude、WorkBuddy 的会话文件。不会导入到 ECA，也不会继续运行这些会话。</p>
    {error&&<p className="external-error" role="alert">{error}</p>}

    {!picked&&<>
      <div className="external-filters" role="group" aria-label="按来源筛选">
        {['all','codex','claude','workbuddy'].map(name=>
          <button key={name} type="button" className={'external-chip'+(filter===name?' is-current':'')}
            aria-pressed={filter===name} onClick={()=>setFilter(name)}>
            {name==='all'?'全部':labels[name]}
            <small>{name==='all'?(rows?.length??0):counts[name]||0}</small>
          </button>)}
      </div>
      {rows===null?<p className="external-empty">正在统计本机会话…</p>
        :visible.length===0?<p className="external-empty">没有找到会话。装了对应工具并产生过对话后，这里会出现记录。</p>
        :<ul className="external-list">{visible.map(row=>
          <li key={row.source+row.id}>
            <button type="button" className="external-row" onClick={()=>void pick(row)}>
              <span className="external-badge" data-source={row.source}>{labels[row.source]||row.source}</span>
              <span className="external-title" title={row.title}>{row.title||row.id}</span>
              <span className="external-meta">{clock(row.updated)} · {size(row.size)}</span>
            </button>
          </li>)}</ul>}
    </>}

    {picked&&<section className="external-view">
      <header>
        <button type="button" className="external-back" onClick={()=>{setPicked(null);setView(null);}}><ArrowLeft size={14}/>返回列表</button>
        <span className="external-badge" data-source={picked.source}>{labels[picked.source]||picked.source}</span>
        <strong className="external-view-title" title={picked.title}>{picked.title||picked.id}</strong>
        <span className="external-meta"><Clock size={12}/>{clock(picked.updated)}<Files size={12}/>{size(picked.size)}</span>
        <button type="button" className="external-import" disabled={!projectId||loading}
          title={projectId?'把这段历史导入成一个新的 ECA 会话，然后接着聊':'先在左侧打开一个项目，导入会创建新会话'}
          onClick={()=>void importSession()}>在 ECA 里接着聊</button>
      </header>
      {!projectId&&<p className="external-note">导入会新建一个 ECA 会话，所以需要先打开一个项目。</p>}
      {loading&&<p className="external-empty">正在读取会话…</p>}
      {!loading&&view?.error&&<p className="external-error" role="alert">{view.error}</p>}
      {!loading&&view&&!view.error&&<>
        {view.messages.length===0&&<p className="external-empty">这个会话里没有可显示的文字消息。</p>}
        <ol className="external-messages">{view.messages.map((message:any,index:number)=>
          <li key={index} className={'external-message role-'+message.role+(message.synthetic?' is-synthetic':'')}>
            <span className="external-role">{message.role==='user'?(message.synthetic?'上下文注入':'你'):'助手'}</span>
            <pre>{message.text}</pre>
          </li>)}</ol>
        {view.truncated&&<p className="external-note">记录较长，这里只显示前 {view.messages.length} 条或前 40000 字。</p>}
      </>}
    </section>}
  </Dialog>;
}
