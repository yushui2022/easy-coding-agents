import React, {useEffect, useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {FolderOpen, GearSix, Plus, Stop, ArrowUp, Check, ArrowCounterClockwise, X, ArrowClockwise, FileText, ChatCircle, SidebarSimple, CaretDown, Code, Bug, TestTube, MagnifyingGlass, ArrowDown, ListChecks, ShieldCheck} from '@phosphor-icons/react';
import {Dialog} from './Dialog';
import {ModelPicker, ModelSettings} from './ModelSettings';
import {Transcript, LazyDetail, LogText} from './Transcript';
import {Workspace} from './workspace/Workspace';
import {EmptyState} from './ui/EmptyState';
import './tokens.css';
import './style.css';
import './workbench.css';
import './workspace/workspace.css';

declare global { interface Window { eca: {
  invoke: (method: string, params?: Record<string, unknown>) => Promise<any>;
  subscribe: (callback: (data:{event?:string}) => void) => () => void;
  onFailure: (callback: (message: string) => void) => () => void;
}; } }
const invoke = window.eca.invoke;
const labels: Record<string,string> = {idle:'等待指令', running:'执行中', repairing:'正在修复', interrupted:'已停止', error:'遇到问题', blocked:'需要处理', limit:'达到配置上限', passed:'通过', failed:'失败', not_run:'未验证', stale:'结果已过期', task_incomplete:'任务未完成', unconfirmed_snapshot:'结果待核实', applied:'已修改', accepted:'已审查', undone:'已撤销'};
const label = (value: string) => labels[value] || value;
const shorten = (text: string, count = 1600) => text.length > count ? text.slice(0,count) + '\n…' : text;
const draftKey = 'eca.desktop.task-draft';
const thinkingLabels:Record<string,string>={fast:'快速',balanced:'均衡',deep:'深入',default:'服务默认'};
const permissionLabels:Record<string,string>={ask:'逐次确认','accept-edits':'自动编辑','full-access':'完全访问'};
function Activity({state}: {state:any}) {
  const [now,setNow]=useState(Date.now());
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);
  const activity=state.activity||{};
  const phases:Record<string,string>={preparing:'正在准备任务',waiting_model:'等待模型响应',thinking:'模型正在思考',responding:'正在生成回答',tool_arguments:'正在生成工具参数',executing:'正在执行工具',verifying:'正在执行验证',repairing:'正在修复验证失败',approval:'等待你的授权',question:'等待你的回答'};
  const elapsed=Math.max(0,Math.floor(now/1000-(state.started_at||now/1000)));
  return <div className="run-activity" role="status"><span className="status-dot active"/><div><strong>{phases[activity.phase]||'正在处理'}{activity.tool?' · '+activity.tool:''}</strong><small>{activity.phase==='thinking'?`已接收 ${Number(activity.reasoning_chars||0).toLocaleString()} 个思考字符`:activity.phase==='tool_arguments'?`参数生成中 · ${Number(activity.tool_argument_chars||0).toLocaleString()} 字符 · 尚未执行`:activity.phase==='waiting_model'?'请求已发出，可以随时停止':'进度与已完成修改会保留'}</small></div><time>{Math.floor(elapsed/60)}:{String(elapsed%60).padStart(2,'0')}</time></div>;
}
function readDraft() {try {return sessionStorage.getItem(draftKey) || '';} catch {return '';}}
function App() {
  const [state,setState] = useState<any>({project:null,busy:false,sessions:[],messages:[],events:[],pending:[],changes:[],tasks:[]});
  const [config,setConfig] = useState<any>({recent:[]});
  const [settingsOpen,setSettingsOpen] = useState(false);
  const [confirmFull,setConfirmFull] = useState(false);
  const [permissionChanging,setPermissionChanging] = useState(false);
  const [modelPickerOpen,setModelPickerOpen] = useState(false);
  const [modelChanging,setModelChanging] = useState(false);
  const [projectChanging,setProjectChanging] = useState(false);
  const projectBusy = useRef(false);
  const [modelSelectionError,setModelSelectionError] = useState('');
  const [error,setError] = useState('');
  const [prompt,setPrompt] = useState(readDraft);
  const [notice,setNotice] = useState('');
  const [detailsOpen,setDetailsOpen] = useState(()=>window.innerWidth>=1180);
  const [navCollapsed,setNavCollapsed] = useState(false);
  const [sessionSearch,setSessionSearch] = useState('');
  const [following,setFollowing] = useState(true);
  const [narrow,setNarrow] = useState(() => window.innerWidth < 1180);
  const [sheetOpen,setSheetOpen] = useState(false);
  const [checks,setChecks] = useState('');
  const [checkOptionsOpen,setCheckOptionsOpen]=useState(false);
  const [repairAttempts,setRepairAttempts] = useState(1);
  const [sending,setSending] = useState(false);
  const [stopping,setStopping] = useState(false);
  const [sideTab,setSideTab] = useState('changes');
  const [diff,setDiff] = useState<any>(null);
  const [answer,setAnswer] = useState('');
  const [answered,setAnswered] = useState<string|null>(null);
  const [older,setOlder] = useState<any[]>([]);
  const [cursor,setCursor] = useState<number|null>(null);
  const [historyLoading,setHistoryLoading] = useState(false);
  const historyBusy=useRef(false);
  const [diagnostic,setDiagnostic] = useState<any>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const promptInput = useRef<HTMLTextAreaElement>(null);
  const composing = useRef(false);
  const compositionEndedAt = useRef(-Infinity);
  const startBusy = useRef(false);
  const bottom = useRef(true);
  const latest = useRef(state);
  const refreshBusy = useRef(false);
  const refreshAgain = useRef(false);
  const liveBusy = useRef(false);
  const reportedError = useRef(0);
  const refresh = async () => {
    if (refreshBusy.current) {refreshAgain.current = true; return;}
    refreshBusy.current = true;
    try {const value = await invoke('snapshot',{preview:true}); if(value.backend_id!==latest.current.backend_id||value.seq>=latest.current.seq||value.session_id!==latest.current.session_id){latest.current = value; setState(value);}}
    catch (e) {setError(String(e));}
    finally {refreshBusy.current=false; if (refreshAgain.current) {refreshAgain.current=false; void refresh();}}
  };
  const loadConfig = async () => {
    const value = await invoke('config.get'); setConfig(value);

  };
  const refreshLive = async () => {
    if(liveBusy.current||refreshBusy.current)return;
    liveBusy.current=true;
    try {
      const requested=latest.current;
      const value=await invoke('live',{stream_id:requested.stream_id,stream_offset:requested.stream_offset}), old=latest.current;
      if(value.backend_id===old.backend_id&&value.session_id===old.session_id&&value.project===old.project&&value.seq>=old.seq) {
        if('stream_delta' in value) {
          // A concurrent full snapshot may already contain these characters.
          if(old.stream_id!==requested.stream_id||old.stream_offset!==requested.stream_offset)return;
          value.stream=(old.stream||'')+value.stream_delta;
        }
        latest.current={...old,...value};setState(latest.current);
      }
    } catch(e){setError(String(e));} finally {liveBusy.current=false;}
  };
  useEffect(() => {
    void loadConfig().catch(e => setError(String(e))); void refresh();
    let timer: ReturnType<typeof setTimeout>|undefined;
    let full=false;
    const off = window.eca.subscribe(data => {
      if(data.event==='sidechat')return;
      if(!['text','model_activity'].includes(data.event||''))full=true;
      if (!timer) timer=setTimeout(() => {timer=undefined;const structural=full;full=false;void (structural?refresh():refreshLive());},80);
    });
    const failure = window.eca.onFailure(message => {setError(message); setState((old:any) => ({...old,busy:false,status:'interrupted',pending:[],stream:''}));});
    return () => {off(); failure(); clearTimeout(timer);};
  },[]);
  useEffect(() => {try {sessionStorage.setItem(draftKey,prompt);} catch { /* storage unavailable */ }},[prompt]);
  useEffect(() => {
    const query = matchMedia('(max-width: 1179px)');
    const update = () => {setNarrow(query.matches);setSheetOpen(false);};
    query.addEventListener('change',update);
    return () => query.removeEventListener('change',update);
  },[]);
  useEffect(() => {setOlder([]);setCursor(null);setDiff(null);bottom.current=true;setFollowing(true);},[state.session_id]);
  useEffect(()=>{setSessionSearch('');},[state.project]);
  const messages=useMemo(()=>[...older,...state.messages],[older,state.messages]);
  useEffect(() => {
    if(!state.project)return;
    try {
      const saved=JSON.parse(sessionStorage.getItem('eca.verification.'+state.project)||'null');
      setChecks(typeof saved?.checks==='string'?saved.checks:'');
      setRepairAttempts(Number.isInteger(saved?.repairAttempts)&&saved.repairAttempts>=0&&saved.repairAttempts<=3?saved.repairAttempts:1);
    } catch {setChecks('');setRepairAttempts(1);}
  },[state.project]);
  const verificationDraft = (text:string, attempts:number) => {
    setChecks(text);setRepairAttempts(attempts);
    if(state.project)try {sessionStorage.setItem('eca.verification.'+state.project,JSON.stringify({checks:text,repairAttempts:attempts}));} catch { /* optional draft storage */ }
  };
  useEffect(() => {if (!state.busy) setStopping(false);},[state.busy]);
  useEffect(() => {
    if(state.seq<reportedError.current)reportedError.current=0; // A restarted backend begins a new sequence.
    const failures=state.events.filter((event:any)=>event.event==='error'&&event.seq>reportedError.current);
    if(failures.length){const last=failures[failures.length-1];reportedError.current=last.seq;setError(String(last.data));}
  },[state.events,state.seq]);
  useEffect(() => {if (bottom.current && scroll.current) scroll.current.scrollTop=scroll.current.scrollHeight;},[state.messages,state.stream,state.pending]);
  const perform = async (method:string, params:Record<string,unknown>={}) => {
    const projectOperation=['project.pick','project.recent','project.close'].includes(method);
    if(projectOperation&&projectBusy.current)return null;
    if(projectOperation){projectBusy.current=true;setProjectChanging(true);}
    setError('');
    if(method==='session.switch') setNotice('');
    try {const result=await invoke(method,{preview:true,...params}); await refresh(); return result;}
    catch(e) {setError(String(e)); return null;}
    finally {if(projectOperation){projectBusy.current=false;setProjectChanging(false);}}
  };
  const pick = async () => {
    const result = await perform('project.pick');
    await loadConfig().catch(e=>setError(String(e)));
    if(result) setNotice('项目已就绪，确认模型后发送任务。');
    promptInput.current?.focus();
    return result;
  };
  const start = async () => {
    if (!prompt.trim() || startBusy.current || state.busy || modelChanging || projectBusy.current) return;
    startBusy.current=true;setSending(true);bottom.current=true;setNotice('');
    try {
      // Choosing a directory never implicitly runs a draft against that project.
      if (!state.project) {await pick();return;}
      const submitted=prompt;
      const commands=checks.split('\n').map(x=>x.trim()).filter(Boolean);
      setCheckOptionsOpen(false);
      const result=await perform('task.start',{prompt:submitted,checks:commands,repair_attempts:commands.length&&state.settings?.mode==='code'?repairAttempts:0});
      if(result) setPrompt(current=>current===submitted?'':current);
    } finally {startBusy.current=false;setSending(false);}
  };
  const chooseModel = async (choice:string) => {
    if(modelChanging||state.busy||projectBusy.current)return false;
    setModelChanging(true);setModelSelectionError('');
    try {
      if(state.project) {await invoke('model.use',{choice});await refresh();}
      else {setConfig(await invoke('config.default',{id:choice}));}
      setModelPickerOpen(false);setSettingsOpen(false);setNotice('模型已切换。');return true;
    } catch(e) {setModelSelectionError(String(e));return false;}
    finally{setModelChanging(false);}
  };
  const choosePermission = async (mode:string) => {
    if(permissionChanging)return;
    setPermissionChanging(true);
    try {await perform('permissions.set',{mode});setConfirmFull(false);}
    finally {setPermissionChanging(false);}
  };
  const loadOlder = async () => {
    if(historyBusy.current)return;
    const before=cursor ?? Math.max(0,state.message_total-50);
    const session=state.session_id,project=state.project,backend=state.backend_id;
    historyBusy.current=true;setHistoryLoading(true);
    try {
      const result=await invoke('session.messages',{id:session,before,preview:true});
      if(latest.current.session_id!==session||latest.current.project!==project||latest.current.backend_id!==backend)return;
      bottom.current=false;setFollowing(false);setOlder(old=>[...result.messages,...old].slice(0,150));setCursor(result.before);
    } catch(e){if(latest.current.session_id===session)setError(String(e));}
    finally{historyBusy.current=false;setHistoryLoading(false);}
  };
  const waiting=state.pending?.[0];
  const reply = async (value:boolean|string) => {
    if (!waiting || answered===waiting.id) return;
    setAnswered(waiting.id);
    const result=await perform('input.reply',{id:waiting.id,run_id:waiting.run_id,value});
    if (!result) setAnswered(null);
  };
  const usage=state.usage || {};
  const tokens=Object.values(usage.reported_tokens || {}).reduce((sum:number,value:any)=>sum+Number(value),0);
  const prices=Object.entries(usage.priced_subtotals || {});
  const empty = !state.messages?.length && !state.stream && !waiting;
  const model = state.project ? state.settings?.model : config.model?.model;
  const checkCount=checks.split('\n').filter(command=>command.trim()).length;
  const permissionHint=state.approval_mode==='full-access'?'完全访问仅对本次打开的项目生效':state.approval_mode==='accept-edits'?'自动批准文件修改，命令仍需确认':'需要授权的操作逐次确认';
  const modelSource = state.project
    ? (state.settings?.source==='desktop'
      ? (state.model_selection?.choice==='default'?'桌面默认':'项目指定连接')+' · '+(state.model_selection?.name||'')
      : '项目配置与环境变量')
    : (config.model?'桌面默认模型':'添加一个模型连接即可开始');
  const projectName = state.project?.split(/[\\/]/).pop();
  const activeSession=state.sessions.find((session:any)=>session.id===state.session_id);
  const sessionTitle=activeSession?.title&&activeSession.title!=='New session'?activeSession.title:'新任务';
  const filteredSessions=state.sessions.filter((session:any)=>(session.title==='New session'?'新会话':session.title).toLowerCase().includes(sessionSearch.toLowerCase()));
  const verificationStatus=state.suite?.status||state.verification?.status||'not_run';
  const stopReasons:Record<string,string>={repair_budget_exhausted:'已达到本次自动修复次数，失败记录已保留。',repeated_failure_same_source:'相同代码再次出现相同失败，已停止重复尝试。',unsafe_to_retry:'执行结果不确定或未获授权，未自动重试。'};
  const inspector = <>
    <div className="tabs" role="tablist" aria-label="任务详情">
      {[['changes','修改'],['checks','验证'],['tasks','进度'],['usage','用量']].map(([id,text]) =>
        <button key={id} id={'tab-'+id} role="tab" aria-selected={sideTab===id} aria-controls={'panel-'+id}
          className={sideTab===id?'active':''} onClick={()=>setSideTab(id)}>{text}{id==='changes'&&state.changes.length>0&&<span className="count">{state.changes.length}</span>}</button>)}
    </div>
    <div className="inspector-body" role="tabpanel" id={'panel-'+sideTab} aria-labelledby={'tab-'+sideTab}>
      {sideTab==='changes'&&<>
        <div className="panel-label">文件变更 <span>{state.changes.length}</span></div>
        {!state.changes.length?<EmptyState icon={<FileText size={25} weight="light"/>} title="还没有文件修改">任务产生的修改会显示在这里。</EmptyState>
          :state.changes.map((c:any)=><div className="change" key={c.id}>
            <button className="change-title" title={c.path} onClick={async()=>{const result=await perform('changes.diff',{id:c.id});if(result)setDiff({...c,...result});}}><FileText size={16}/><span>{c.path}</span></button>
            <div className="change-bottom"><span>{label(c.status)}</span>
              <button aria-label={'审查 '+c.path} title="标记已审查，不提交 Git" disabled={state.busy||!['applied','accepted'].includes(c.status)} onClick={()=>perform('changes.accept',{id:c.id})}><Check size={16}/></button>
              <button aria-label={'撤销 '+c.path} title="撤销这次文件修改" disabled={state.busy||c.status==='undone'} onClick={()=>perform('changes.undo',{id:c.id})}><ArrowCounterClockwise size={16}/></button>
            </div>
          </div>)}
        <div className="panel-label verification-label">检查概览<button className="text-link" onClick={()=>setSideTab('checks')}>查看记录</button></div>
        <div className="verification"><span className={verificationStatus==='passed'?'passed':''}>{verificationStatus==='passed'?'所选检查通过':label(verificationStatus)}</span><p>{state.suite?.commands?.length?`${state.suite.commands.length} 条所选命令 · 记录在当前会话`:'本次尚未设置验收命令'}</p></div>
        <p className="fine-print">审查只标记记录；撤销仅作用于对应文件修改。</p>
      </>}
      {sideTab==='checks'&&<>
        <div className="panel-label">验证结果</div>
        <div className="verification"><span className={verificationStatus==='passed'?'passed':''}>{verificationStatus==='passed'?'所选检查通过':label(verificationStatus)}</span>
          <p>{state.suite?.commands?.join(' · ')||state.verification?.command||'设置验证命令，或让 ECA 执行检查。'}</p>
          {!!state.suite?.commands?.length&&<p>自动修复上限：{state.suite.repair_budget||0} 次 · 已进行 {Math.max(0,(state.suite.rounds?.length||0)-1)} 次</p>}
          {state.suite?.stop_reason&&<p role="status">{stopReasons[state.suite.stop_reason]||state.suite.stop_reason}</p>}
          {state.suite?.rounds?.map((round:any,i:number)=><div className="check-round" key={i}><div className="check-round-title">第 {i+1} 轮 · {label(round.status)}</div>{round.checks?.map((check:any,j:number)=><LazyDetail key={j} className="check-record" title={<><span className={check.status==='failed'?'failed':''}>{label(check.status)}</span><code>{check.command}</code></>} text={JSON.stringify(check,null,2)}/>)}</div>)}
          {verificationStatus==='passed'&&<p>仅代表上述命令通过；未覆盖的行为和视觉效果仍需检查。</p>}
        </div>
        {!!state.change_impact?.length&&<details className="impact-review"><summary>回归检查建议 · {state.change_impact.length} 个文件</summary><p className="fine-print">根据 Python 代码变化生成的线索；不代表已经验证，也不覆盖所有调用关系。</p>{state.change_impact.slice(-6).map((item:any)=><div key={item.path}><strong>{item.path}</strong><p>{item.risks.includes('transaction_mode')?'事务设置发生变化：检查调用方的提交、回滚及拒绝操作后数据是否保持不变。':'公共代码发生变化：检查调用方、异常行为和相关回归测试。'}{item.symbols.length>0&&` 涉及：${item.symbols.join('、')}`}</p></div>)}</details>}
      </>}
      {sideTab==='tasks'&&<>
        <div className="panel-label">任务清单</div>
        {!state.tasks.length&&<EmptyState icon={<ListChecks size={25} weight="light"/>} title="等待任务计划">ECA 制定计划后，可以在这里跟踪进度。</EmptyState>}
        {state.tasks.map((t:any,i:number)=><div className="task-row" key={i}><span>{t.status==='completed'?'✓':'·'}</span><span>{t.content}</span><small>{({completed:'已完成',in_progress:'进行中',pending:'待处理'} as Record<string,string>)[t.status]||t.status}</small></div>)}
        <div className="panel-label verification-label">执行活动</div>
        {state.events.filter((event:any)=>!['text','usage','model_activity'].includes(event.event)).slice(-30).reverse().map((event:any)=><LazyDetail className="activity" key={event.seq} title={event.event==='subagent_progress'?'子 Agent 活动':({tool:'工具调用',result:'工具返回',request_start:'模型请求',request_end:'请求结束',notice:'运行提示',verification_suite:'验证结果',verification_progress:'验证进度',turn:'新一轮处理'} as Record<string,string>)[event.event]||event.event} text={shorten(typeof event.data==='string'?event.data:JSON.stringify(event.data,null,2),10000)}/>)}
      </>}
      {sideTab==='usage'&&<>
        <div className="panel-label">当前会话、子任务与侧聊</div>
        <div className="metric"><span>模型请求</span><strong>{usage.requests||0}</strong></div>
        <div className="metric"><span>已报告 tokens</span><strong>{tokens.toLocaleString()}</strong></div>
        <div className="metric"><span>费用</span><strong>{!prices.length?'未知':prices.map(([currency,value])=>currency+' '+value).join(' / ')}</strong></div>
        {usage.incomplete_cost_requests>0&&<p className="muted">{usage.incomplete_cost_requests} 次请求缺少完整计价依据，已知金额仅为小计。</p>}
        <p className="fine-print">费用基于服务商用量与项目定价配置，不是账单。</p>
      </>}
    </div>
    <button className="diagnose" onClick={async()=>{const result=await perform('diagnostics');if(result)setDiagnostic(result);}} disabled={!state.project}><ArrowClockwise size={15}/>检查项目环境</button>
  </>;
  return <div className={'eca-app workspace'+(state.project&&detailsOpen?' with-inspector':'')+(navCollapsed?' nav-collapsed':'')}>
    <aside className="sidebar">
      <div className="brand"><img src="./logo.png" alt="ECA"/><strong>ECA</strong><span>Desktop</span><span className="preview">预览</span></div>
      <button className="open-project" onClick={pick} disabled={state.busy||sending||projectChanging}><FolderOpen size={18}/>打开项目<Plus size={15}/></button>
      <div className="section-heading">项目</div>
      {state.project&&<div className="project-current" title={state.project}><FolderOpen size={16}/><span>{projectName}</span></div>}
      {!state.project&&!config.recent.length&&<p className="nav-empty">打开一个文件夹，<br/>从你的代码开始。</p>}
      {config.recent.filter((p:string)=>p!==state.project).slice(0,4).map((p:string)=>
        <button className="recent" key={p} title={p} disabled={state.busy||sending||projectChanging} onClick={()=>perform('project.recent',{index:config.recent.indexOf(p)})}><FolderOpen size={15}/><span>{p.split(/[\\/]/).pop()}</span></button>)}
      <div className="section-heading session-heading">会话<button className="icon-button" aria-label="新建会话" title="新建会话" disabled={!state.project||state.busy||sending||projectChanging} onClick={()=>perform('session.switch')}><Plus size={17}/></button></div>
      <label className="session-search"><MagnifyingGlass size={14}/><input aria-label="搜索会话" placeholder="搜索会话" value={sessionSearch} onChange={e=>setSessionSearch(e.target.value)}/>{sessionSearch&&<button className="icon-button" aria-label="清除会话搜索" onClick={()=>setSessionSearch('')}><X size={12}/></button>}</label>
      <nav className="session-list" aria-label="历史会话">
        {!state.sessions.length&&<p className="nav-empty">任务记录会保存在项目中，<br/>下次可以继续。</p>}
        {sessionSearch&&!filteredSessions.length&&<p className="nav-empty">没有匹配的会话<br/><button className="text-link" onClick={()=>setSessionSearch('')}>清除搜索</button></p>}
        {filteredSessions.map((s:any)=><button key={s.id} title={s.title} className={s.id===state.session_id?'selected':''} aria-current={s.id===state.session_id?'page':undefined} disabled={state.busy||sending||projectChanging} onClick={()=>perform('session.switch',{id:s.id})}><ChatCircle size={16}/><span>{s.title==='New session'?'新会话':s.title}</span></button>)}
      </nav>
      <div className="sidebar-bottom">
        <button className="settings-button" onClick={()=>setSettingsOpen(true)}><GearSix size={18}/><span>模型与设置</span>{config.credential_configured&&<span className="connection-dot" title="已配置密钥"/>}</button>
        <footer><span>本地工作空间</span><span>{config.version||'预览版'}</span></footer>
      </div>
    </aside>
    <main className="conversation">
      <header className="conversation-header">
        <button className="icon-button nav-toggle" aria-label={navCollapsed?'展开导航':'收起导航'} aria-expanded={!navCollapsed} onClick={()=>setNavCollapsed(!navCollapsed)}><SidebarSimple size={18}/></button>
        <div className="workspace-title" title={state.project||'选择项目后，ECA 将在该文件夹内工作'}><span>{projectName||'本地工作空间'}</span><strong>{state.project?sessionTitle:'开始工作'}</strong></div>
        <div className="header-actions">
          <div className="status"><span className={state.busy?'status-dot active':'status-dot'}/>{projectChanging?'正在打开项目…':state.busy?(stopping?'正在停止…':waiting?'等待确认':'执行中'):label(state.status||'idle')}</div>
          {state.project&&<><button className="icon-button" aria-label="打开侧边聊天" title="在侧边聊天中询问选中内容" onClick={()=>{setDetailsOpen(true);window.dispatchEvent(new CustomEvent('eca:sidechat',{detail:window.getSelection()?.toString()||''}));}}><ChatCircle size={19}/></button><button className="icon-button details-toggle" aria-label="任务详情" title="显示或收起工作区" aria-expanded={detailsOpen} onClick={()=>setDetailsOpen(!detailsOpen)}><SidebarSimple size={19}/></button></>}
        </div>
      </header>
      {error&&<div role="alert" className="error-banner"><span>{error}</span><button className="icon-button" aria-label="关闭错误" onClick={()=>setError('')}><X size={17}/></button></div>}
      <div className={'work-area'+(empty?' is-empty':'')}>
        <div className="transcript" ref={scroll} onScroll={()=>{const el=scroll.current!;bottom.current=el.scrollHeight-el.scrollTop-el.clientHeight<100;setFollowing(bottom.current);}}>
          {empty?<div className="welcome">
            <h1>{state.project?'这次想完成什么？':'开始一个编码任务'}</h1>
            <p>{state.project?'从一个想法、一处修改，或一段报错开始。':'写下任务，选择项目，即可开始。'}</p>
          </div>:<div className="messages">
            {(cursor??state.message_total-50)>0&&<button className="load-older" disabled={historyLoading} onClick={loadOlder}>{historyLoading?'正在加载…':'加载更早的消息'}</button>}
            {older.length>=150&&<p className="fine-print">历史记录分段显示；继续加载查看更早内容。</p>}
            <Transcript messages={messages} sessionId={state.session_id} root={state.project||''} busy={state.busy}/>
            {older.length>0&&<button className="log-more" onClick={()=>{setOlder([]);setCursor(null);bottom.current=true;setFollowing(true);if(scroll.current)scroll.current.scrollTop=scroll.current.scrollHeight;}}>返回最近记录</button>}
          </div>}
          {state.stream&&<article className="message assistant live"><div className="message-label">ECA <span>正在输出</span></div><div className="stream-text">{state.stream}</div></article>}
        </div>
        <div className="composer-wrap">
          {!following&&!empty&&<div className="scroll-return"><button className="jump-latest" onClick={()=>{bottom.current=true;setFollowing(true);scroll.current?.scrollTo({top:scroll.current.scrollHeight});}}><ArrowDown size={14}/>回到最新</button></div>}
          {state.busy&&!waiting&&<Activity state={state}/>}
          {waiting&&<section className="approval" role="region" aria-label="等待确认">
            <div className="eyebrow">{waiting.kind==='approval'?'需要你的授权':'ECA 有一个问题'}</div><h3>{waiting.message}</h3>
            {waiting.detail&&<div className="approval-detail"><LogText text={waiting.detail}/></div>}
            {waiting.kind==='approval'?<div className="actions"><button disabled={answered===waiting.id} onClick={()=>reply(false)}>拒绝</button><button className="primary" disabled={answered===waiting.id} onClick={()=>reply(true)}>本次允许</button></div>
              :<form onSubmit={e=>{e.preventDefault();void reply(answer);setAnswer('');}}><input aria-label="回答" value={answer} onChange={e=>setAnswer(e.target.value)}/><button className="primary" type="submit" disabled={answered===waiting.id}>发送回答</button></form>}
          </section>}
          <div className="composer">
            <textarea ref={promptInput} id="prompt" aria-label="任务指令" placeholder="描述任务，或粘贴需要排查的报错…" value={prompt} onChange={e=>setPrompt(e.target.value)}
              onCompositionStart={()=>{composing.current=true;}}
              onCompositionEnd={()=>{composing.current=false;compositionEndedAt.current=performance.now();}}
              onKeyDown={e=>{
                if(e.key!=='Enter'||e.shiftKey||e.altKey)return;
                if(composing.current||e.nativeEvent.isComposing||e.nativeEvent.keyCode===229||performance.now()-compositionEndedAt.current<50)return;
                e.preventDefault();
                if(!e.repeat)void start();
              }}/>
            <div className="composer-toolbar">
              <div className="composer-options">
              <button className="model-chip" title={modelSource} disabled={state.busy||sending||modelChanging||projectChanging} onClick={()=>{setModelSelectionError('');setModelPickerOpen(true);}}><span className={model?'connection-dot':'status-dot'}/><span>{model||'配置模型'}</span>{model?.toLowerCase().startsWith('deepseek')&&<span className="thinking-badge">{thinkingLabels[(state.project?state.settings?.thinking_mode:config.model?.thinking_mode)||'default']}</span>}<CaretDown size={13}/></button>
              </div>
              <div className="composer-actions">
              {state.project&&<div className={'permission-control '+(state.approval_mode==='full-access'?'full-access':'')}><ShieldCheck size={14}/><select className={'permission-picker '+(state.approval_mode==='full-access'?'full-access':'')} aria-label="审批模式" title={permissionHint} value={state.approval_mode||'ask'} disabled={permissionChanging||projectChanging} onChange={e=>e.target.value==='full-access'?setConfirmFull(true):void choosePermission(e.target.value)}>{Object.entries(permissionLabels).map(([value,text])=><option key={value} value={value}>{text}</option>)}</select></div>}
              {state.busy?<button className="stop-button" disabled={stopping} onClick={()=>{setStopping(true);void perform('task.cancel',{run_id:state.run_id}).then(result=>{if(!result)setStopping(false);});}}><Stop size={13} weight="fill"/>{stopping?'正在停止':'停止'}</button>
                :<button className="send-button" aria-label="发送任务" title={state.project?'发送任务 · Enter':'选择项目后确认发送'} disabled={!prompt.trim()||sending||modelChanging||projectChanging} onClick={start}>{!state.project&&<span>{sending?'正在打开…':'选择项目并继续'}</span>}<ArrowUp size={17}/></button>}
              </div>
            </div>
          </div>
          {notice&&<div className="composer-notice" role="status"><Check size={15}/>{notice}</div>}
          <div className="composer-meta">
            <details className="checks" open={checkOptionsOpen} onToggle={e=>setCheckOptionsOpen(e.currentTarget.open)}>
              <summary aria-label="验证与自动修复" title="配置任务完成后的检查与修复" onClick={e=>{if(state.busy)e.preventDefault();}}><TestTube size={14}/><span>任务验证</span>{checkCount>0&&<span className="check-count">{checkCount} 项</span>}<CaretDown size={11} className="checks-caret"/></summary>
              <div className="check-settings">
                <div className="check-settings-heading"><label htmlFor="verification-commands">完成任务后运行</label><span>每行一条命令</span></div>
                <textarea id="verification-commands" aria-label="验证命令" placeholder={'npm test\nnpm run build'} value={checks} onChange={e=>verificationDraft(e.target.value,repairAttempts)} disabled={state.busy}/>
                <label className="repair-option">检查失败时<select aria-label="自动修复次数" value={repairAttempts} disabled={state.busy||!checks.trim()||state.settings?.mode!=='code'} onChange={e=>verificationDraft(checks,Number(e.target.value))}><option value={0}>停止，保留结果</option>{[1,2,3].map(count=><option key={count} value={count}>最多自动修复 {count} 次</option>)}</select></label>
                <p className="fine-print">修复后重跑全部检查。授权被拒绝、超时或取消时停止。</p>
              </div>
            </details>
            <span className="keyboard-hint" aria-label="Enter 发送，Shift 加 Enter 换行"><span><kbd>↵</kbd>发送</span><span><kbd>Shift ↵</kbd>换行</span></span>
          </div>
          {empty&&<div className="suggestions" aria-label="任务示例">
            <span className="suggestions-label">快速开始</span>
            {[[Code,'了解项目','梳理项目结构、运行方式和核心模块，先不要修改代码。'],[Bug,'排查问题','帮我定位并修复一个问题：'],[TestTube,'补充测试','检查项目现有测试，为缺少覆盖的关键逻辑补充测试。']].map(([Icon,text,value])=>{
              const SuggestionIcon=Icon as typeof Code;
              return <button key={String(text)} onClick={()=>{setPrompt(String(value));promptInput.current?.focus();}}><SuggestionIcon size={16}/>{String(text)}</button>;
            })}
          </div>}
        </div>
      </div>
    </main>
    {state.project&&<Workspace key={state.session_id} state={state} config={config} review={inspector} open={detailsOpen} onOpen={setDetailsOpen} narrow={narrow} blocked={!!(settingsOpen||modelPickerOpen||confirmFull||diff||diagnostic||waiting)} onDraft={(text:string)=>{setPrompt(p=>p?p+'\n\n'+text:text);setNotice('已放入主对话草稿，确认后发送。');promptInput.current?.focus();}}/>}
    {modelPickerOpen&&<ModelPicker config={config} state={state} busy={state.busy||modelChanging} error={modelSelectionError} onClose={()=>setModelPickerOpen(false)} onChoose={chooseModel} onManage={()=>{setModelPickerOpen(false);setSettingsOpen(true);}}/>}
    <ModelSettings open={settingsOpen} config={config} state={state} onConfig={setConfig} onClose={()=>setSettingsOpen(false)} onUse={chooseModel}/>
    {confirmFull&&<Dialog title="开启完全访问" closeLabel="取消完全访问" onClose={()=>setConfirmFull(false)}><p>在当前项目中自动批准文件修改、命令、联网及外部工具操作，也会放行正在等待的授权。</p><p>命令按当前系统账户权限执行，可能访问项目外文件和网络；不会获得管理员权限。文件工具仍保留路径和冲突检查，已有沙箱及只读模式继续生效。</p><p className="fine-print">仅本次打开项目有效，重新打开后恢复项目审批设置。随时可切回逐次确认；已执行的操作不会因此撤销。</p><div className="actions"><button onClick={()=>setConfirmFull(false)}>取消</button><button className="primary" disabled={permissionChanging} onClick={()=>choosePermission('full-access')}>开启完全访问</button></div></Dialog>}
    {diff&&<Dialog title={diff.path} name="文件差异" closeLabel="关闭差异" wide onClose={()=>setDiff(null)}><pre className="diff">{diff.diff.split('\n').map((line:string,i:number)=><span key={i} className={line.startsWith('+')?'added':line.startsWith('-')?'removed':''}>{line}{'\n'}</span>)}</pre></Dialog>}
    {diagnostic&&<Dialog title="项目环境" name="环境检查" closeLabel="关闭环境检查" onClose={()=>setDiagnostic(null)}>{diagnostic.checks.map((item:any,i:number)=><div className="diagnostic" key={i}><strong>{item.name} · {item.status}</strong><p>{item.message}</p></div>)}</Dialog>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
