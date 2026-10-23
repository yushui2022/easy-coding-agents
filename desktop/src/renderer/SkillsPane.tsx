import React,{useEffect,useMemo,useState} from 'react';
import {ArrowLeft, Sparkle} from '@phosphor-icons/react';
import {Dialog} from './Dialog';
import './external-history.css';
import './skills-pane.css';

// Read-only view of <name>/SKILL.md folders. Nothing is copied, enabled or
// renamed: the same files stay owned by the tool that installed them.
const labels:Record<string,string>={project:'本 项目',eca:'ECA',codex:'Codex',claude:'Claude',workbuddy:'WorkBuddy'};

export function SkillsPane({onClose}:{onClose:()=>void}) {
  const [rows,setRows]=useState<any[]|null>(null);
  const [error,setError]=useState('');
  const [filter,setFilter]=useState('all');
  const [picked,setPicked]=useState<any>(null);
  const [body,setBody]=useState<any>(null);
  const [loading,setLoading]=useState(false);

  useEffect(()=>{
    let alive=true;
    void (async()=>{
      try {
        const result=await window.eca.invoke('skills.list');
        if(alive)setRows(result?.skills||[]);
      } catch(reason){
        if(alive){setError(String(reason));setRows([]);}
      }
    })();
    return()=>{alive=false;};
  },[]);

  const open=async(row:any)=>{
    setPicked(row);setBody(null);setLoading(true);setError('');
    try {setBody(await window.eca.invoke('skills.read',{name:row.name}));}
    catch(reason){setError(String(reason));}
    finally {setLoading(false);}
  };

  const counts=useMemo(()=>{
    const map:Record<string,number>={};
    for(const row of rows||[])map[row.source]=(map[row.source]||0)+1;
    return map;
  },[rows]);
  const visible=(rows||[]).filter(row=>filter==='all'||row.source===filter);
  const sources=['all',...Object.keys(counts)];

  return <Dialog title="技能" closeLabel="关闭技能面板" wide className="external-history skills-pane" onClose={onClose}>
    <p className="external-note">
      只读列出本机各工具的 <code>&lt;名称&gt;/SKILL.md</code>。技能只是说明文字，不会获得额外权限；
      同名时按 本 项目 → ECA → Codex → Claude → WorkBuddy 的顺序取第一个。
    </p>
    {error&&<p className="external-error" role="alert">{error}</p>}

    {!picked&&<>
      <div className="external-filters" role="group" aria-label="按来源筛选">
        {sources.map(name=>
          <button key={name} type="button" className={'external-chip'+(filter===name?' is-current':'')}
            aria-pressed={filter===name} onClick={()=>setFilter(name)}>
            {name==='all'?'全部':labels[name]||name}
            <small>{name==='all'?(rows?.length??0):counts[name]||0}</small>
          </button>)}
      </div>
      {rows===null?<p className="external-empty">正在读取技能目录…</p>
        :visible.length===0?<p className="external-empty">没有找到技能。放进 ~/.ecs/skills/&lt;名称&gt;/SKILL.md 或项目 .agents/skills/ 就会出现。</p>
        :<ul className="external-list">{visible.map(row=>
          <li key={row.source+row.name}>
            <button type="button" className="external-row" onClick={()=>void open(row)}>
              <span className="external-badge" data-source={row.source}>{labels[row.source]||row.source}</span>
              <span className="external-title"><strong>{row.name}</strong>{row.description?<small className="skill-desc">{row.description}</small>:null}</span>
              <span className="external-meta"><Sparkle size={12}/>{row.scope==='project'?'项目':'用户'}</span>
            </button>
          </li>)}</ul>}
    </>}

    {picked&&<section className="external-view">
      <header>
        <button type="button" className="external-back" onClick={()=>{setPicked(null);setBody(null);}}><ArrowLeft size={14}/>返回列表</button>
        <span className="external-badge" data-source={picked.source}>{labels[picked.source]||picked.source}</span>
        <strong className="external-view-title">{picked.name}</strong>
      </header>
      {loading&&<p className="external-empty">正在读取技能…</p>}
      {!loading&&body&&<>
        {body.description&&<p className="external-note">{body.description}</p>}
        <pre className="skill-body">{body.text}</pre>
        {body.truncated&&<p className="external-note">技能文件较长，这里只显示开头 4000 字。</p>}
      </>}
    </section>}
  </Dialog>;
}
