import {useEffect, useRef, useState} from 'react';
import {CalendarCheck, CaretDown, ClockCounterClockwise, Desktop, FolderOpen, GearSix, MagnifyingGlass, Plus, Sparkle, X, Sun, Moon} from '@phosphor-icons/react';
import './sidebar.css';

type Session = {id:string; title:string; busy?:boolean; side_busy?:boolean; pending_count?:number; status?:string};
type Project = {id:string;path:string;session_id:string;sessions:Session[];running_count:number};
type Props = {
  state:{project:string|null;project_id?:string;session_id?:string;sessions:Session[];projects?:Project[];busy:boolean;running_count?:number};
  config:{recent:string[];version?:string;connections?:unknown[];credential_configured?:boolean};
  blocked:boolean;onPick:()=>void;onRecent:(index:number)=>void;
  onSession:(id?:string,projectId?:string)=>void;onClose:(projectId:string)=>void;onSettings:()=>void;
  onHistory:()=>void;
  onSkills:()=>void;
  onAutomations:()=>void;
};
const name=(session:Session)=>session.title==='New session'?'新会话':session.title;
const folderName=(path:string)=>path.split(/[\\/]/).filter(Boolean).pop()||path;
const samePath=(a:string,b:string)=>a.replaceAll('\\','/').toLowerCase()===b.replaceAll('\\','/').toLowerCase();
export function Sidebar({state,config,blocked,onPick,onRecent,onSession,onClose,onSettings,onHistory,onSkills,onAutomations}:Props) {
  const [search,setSearch]=useState('');
  const [collapsed,setCollapsed]=useState<string[]>(()=>{try{return JSON.parse(sessionStorage.getItem('eca.projects.collapsed')||'[]');}catch{return [];}});
  // The theme is a desktop preference: the main process owns the value and
  // nativeTheme drives prefers-color-scheme, so the CSS needs no variant rules.
  const [themeSource,setThemeSource]=useState('system');
  useEffect(()=>{
    let live=true;
    void window.eca?.theme?.().then(value=>{if(live)setThemeSource(String(value));}).catch(()=>{});
    const off=window.eca?.onTheme?.(value=>setThemeSource(String(value)));
    return()=>{live=false;if(typeof off==='function')off();};
  },[]);
  const themeLabel=({system:'跟随系统',light:'浅色',dark:'深色'} as Record<string,string>)[themeSource]||'跟随系统';
  const cycleTheme=async()=>{
    const order=['system','light','dark'],next=order[(order.indexOf(themeSource)+1)%order.length];
    const applied=await window.eca?.setTheme?.(next).catch(()=>null);
    setThemeSource(String(applied||next));
  };
  const toggle=(id:string)=>setCollapsed(old=>{const next=old.includes(id)?old.filter(x=>x!==id):[...old,id];sessionStorage.setItem('eca.projects.collapsed',JSON.stringify(next));return next;});
  // Running → finished. Without this a session that just completed looks exactly
  // like one that never ran; the green dot clears as soon as it is opened.
  const previous = useRef<Record<string,boolean>>({});
  const finished = useRef<Map<string,'done'|'failed'>>(new Map());
  const [, redraw] = useState(0);
  const openSession = (id?:string, projectId?:string) => {
    if (id) finished.current.delete(id);
    onSession(id, projectId);
  };
  useEffect(()=>{
    const sessions = (state.projects||[]).flatMap(project=>project.sessions);
    if (!sessions.length) sessions.push(...state.sessions);
    let changed = false;
    for (const session of sessions) {
      const running = !!(session.busy||session.side_busy);
      const was = previous.current[session.id];
      if (was && !running) {
        // A run that ended in error/interrupt/timeout is not "finished".
        finished.current.set(session.id, ['error','interrupted','limit'].includes(String(session.status||''))?'failed':'done');
        changed = true;
      }
      if (running) finished.current.delete(session.id);
      previous.current[session.id] = running;
    }
    if (changed) redraw(n=>n+1);
  }, [state.projects, state.sessions]);
  const projects=state.projects||[];
  const recent=config.recent.filter(path=>!projects.some(p=>samePath(p.path,path)));
  const query=search.trim().toLowerCase(),connections=config.connections?.length||0;
  const matched=projects.map(project=>({...project,sessions:project.sessions.filter(s=>!query||name(s).toLowerCase().includes(query)||folderName(project.path).toLowerCase().includes(query))})).filter(p=>!query||p.sessions.length||folderName(p.path).toLowerCase().includes(query));
  const recentMatches=recent.filter(p=>!query||folderName(p).toLowerCase().includes(query));
  return <aside className="sidebar clay-sidebar" aria-label="工作空间导航">
    <div className="clay-brand"><img src="./welcome-loop.png" width="42" height="42" alt="" decoding="async"/><div className="clay-brand-copy"><div><strong>ECA</strong><span>Desktop</span></div><small>Easy Coding Agent</small></div></div>
    <button className="open-project" aria-label="打开项目" title="打开另一个项目，当前任务继续运行" onClick={onPick} disabled={blocked}><FolderOpen size={17}/><span>打开项目</span><Plus size={15}/></button>
    <section className="project-navigation" aria-label="项目与会话">
      <div className="section-heading"><span>项目与会话</span><button className="icon-button" aria-label="新建会话" title="在当前项目新建会话" disabled={!state.project||blocked} onClick={()=>onSession()}><Plus size={16}/></button></div>
      <label className="session-search"><MagnifyingGlass size={14}/><input aria-label="搜索会话" placeholder="搜索项目或会话" value={search} onChange={e=>setSearch(e.target.value)}/>{search&&<button className="icon-button" aria-label="清除会话搜索" onClick={()=>setSearch('')}><X size={12}/></button>}</label>
      {!!state.running_count&&<div className="session-concurrency" role="status"><i/>{state.running_count} 个会话运行中<span>跨项目持续运行</span></div>}
      <nav className="project-tree" aria-label="历史会话">
        {!projects.length&&!recent.length&&<p className="nav-empty">打开项目，开始你的第一个任务。<br/>每个项目的会话会整理在一起。</p>}
        {!!query&&!matched.length&&!recentMatches.length&&<p className="nav-empty">没有匹配的项目或会话</p>}
        {matched.map(project=>{
          const title=folderName(project.path),selected=state.project_id===project.id,expanded=!!query||!collapsed.includes(project.id);
          return <section className={'project-group'+(selected?' is-current':'')} key={project.id} data-project-id={project.id} aria-label={'项目 '+title}>
            <div className="project-group-heading">
              <button className="project-disclosure" aria-label={(expanded?'收起':'展开')+'项目 '+title} aria-expanded={expanded} onClick={()=>toggle(project.id)}><CaretDown size={12} className={expanded?'':'collapsed'}/></button>
              <button className="project-title" title={project.path} disabled={blocked} onClick={()=>onSession(project.session_id,project.id)}><FolderOpen size={16}/><span>{title}</span>{project.running_count>0&&<small className="project-running" title={project.running_count+' 个会话运行中'}>{project.running_count}</small>}</button>
              <div className="project-actions"><button aria-label={'在 '+title+' 新建会话'} title="新建会话" disabled={blocked} onClick={()=>{setCollapsed(old=>old.filter(x=>x!==project.id));onSession(undefined,project.id);}}><Plus size={14}/></button><button aria-label={'关闭项目 '+title} title={project.running_count?'请先停止此项目的任务':'关闭项目，保留历史记录'} disabled={blocked||project.running_count>0} onClick={()=>onClose(project.id)}><X size={12}/></button></div>
            </div>
            {expanded&&<div className="session-list project-session-list">
              {project.sessions.map(session=>{const running=!!(session.busy||session.side_busy),outcome=running?undefined:finished.current.get(session.id);return <button key={session.id} data-session-id={session.id} title={name(session)} className={selected&&session.id===state.session_id?'selected':''} aria-current={selected&&session.id===state.session_id?'page':undefined} disabled={blocked} onClick={()=>openSession(session.id,project.id)}><span>{name(session)}</span>{running?<small className={'session-state'+(session.pending_count?' waiting':'')} aria-label={session.pending_count?'等待确认':'正在执行'}><i/>{session.pending_count?'待确认':session.busy?'运行中':'侧聊中'}</small>:outcome?<small className={'session-state '+outcome} title={outcome==='done'?'本轮已完成':'本轮出错或已中断'} aria-label={outcome==='done'?'本轮已完成':'本轮出错或已中断'}><i/></small>:null}</button>;})}
              {!project.sessions.length&&<button className="new-project-session" disabled={blocked} onClick={()=>onSession(undefined,project.id)}>开始一个新会话</button>}
            </div>}
          </section>;
        })}
        {!!recentMatches.length&&<div className="recent-projects"><div className="recent-label">最近项目</div>{recentMatches.map(folder=><button className="recent" key={folder} title={folder} disabled={blocked} onClick={()=>onRecent(config.recent.indexOf(folder))}><FolderOpen size={16}/><span>{folderName(folder)}</span></button>)}</div>}
      </nav>
    </section>
    <div className="sidebar-bottom"><button className="settings-button" aria-label="技能" title="查看本机各工具的 SKILL.md（只读）" onClick={onSkills}><span className="settings-glyph"><Sparkle size={17}/></span><span className="settings-copy"><strong>技能</strong><small>ECA · Codex · Claude · WorkBuddy</small></span></button><button className="settings-button" aria-label="定时任务" title="按日程自动开会话执行任务" onClick={onAutomations}><span className="settings-glyph"><CalendarCheck size={17}/></span><span className="settings-copy"><strong>定时任务</strong><small>按日程自动执行</small></span></button><button className="settings-button" aria-label="其他工具的历史" title="查看 Codex / Claude / WorkBuddy 的历史会话（只读）" onClick={onHistory}><span className="settings-glyph"><ClockCounterClockwise size={17}/></span><span className="settings-copy"><strong>其他工具的历史</strong><small>Codex · Claude · WorkBuddy</small></span></button><button className="settings-button" aria-label="模型与设置" title="模型与设置" onClick={onSettings}><span className="settings-glyph"><GearSix size={17}/></span><span className="settings-copy"><strong>模型与设置</strong><small>{connections?`${connections} 个模型连接`:'添加 API 与模型'}</small></span>{config.credential_configured&&<span className="connection-dot" title="已配置密钥"/>}</button><footer><span><Desktop size={12}/>本地工作空间</span><button className="theme-toggle" aria-label={'主题：'+themeLabel} title={'主题：'+themeLabel+'（点击切换）'} onClick={cycleTheme}>{themeSource==='dark'?<Moon size={13}/>:themeSource==='light'?<Sun size={13}/>:<Desktop size={13}/>}</button><span title="版本">{config.version||'本地构建'}</span></footer></div>
  </aside>;
}
