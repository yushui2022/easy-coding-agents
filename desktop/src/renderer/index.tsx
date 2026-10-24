import React, {useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {FolderOpen, Stop, ArrowUp, Check, ArrowCounterClockwise, X, ArrowClockwise, FileText, ChatCircle, SidebarSimple, CaretDown, Desktop, ArrowDown, ListChecks, ShieldCheck, Sparkle, PencilSimple} from '@phosphor-icons/react';
import {Dialog} from './Dialog';
import {ModelSettings} from './ModelSettings';
import {ModelMenu,effortLabels} from './ModelMenu';
import {RunActivity} from './RunActivity';
import {PlanChecklist} from './PlanChecklist';
import {Transcript, LazyDetail, LogText} from './Transcript';
import {Workspace} from './workspace/Workspace';
import {EmptyState} from './ui/EmptyState';
import {Welcome} from './Welcome';
import {Sidebar} from './Sidebar';
import {ExternalHistory} from './ExternalHistory';
import {SkillsPane} from './SkillsPane';
import {SkillMenu, type SkillRow} from './SkillMenu';
import {AutomationsPane} from './AutomationsPane';
import {ContextMeter} from './ContextMeter';
import {PermissionControl,permissionLabels} from './PermissionMenu';
import {ModeControl} from './ModeMenu';
import {GoalBar,GoalDialog} from './GoalBar';
import {TitleBar} from './TitleBar';
import {useAttachments} from './Attachments';
import {AgentCards,type ChildAgent} from './subagents/AgentCards';
import './tokens.css';
import './style.css';
import './workbench.css';
import './workspace/workspace.css';
import './clay-surfaces.css';

declare global { interface Window { eca: {
  invoke: (method: string, params?: Record<string, unknown>) => Promise<any>;
  subscribe: (callback: (data:{event?:string}) => void) => () => void;
  onFailure: (callback: (message: string) => void) => () => void;
  copy: (text: string) => Promise<boolean>;
  windowControl: (action: string) => Promise<boolean>;
  theme: () => Promise<string>;
  setTheme: (source: string) => Promise<string>;
  onTheme: (callback: (source: string) => void) => () => void;
  onMaximized: (callback: (value: boolean) => void) => () => void;
}; } }
const invoke = window.eca.invoke;
const labels: Record<string,string> = {idle:'等待指令', running:'执行中', repairing:'正在修复', interrupted:'已停止', error:'遇到问题', blocked:'需要处理', limit:'达到配置上限', passed:'通过', failed:'失败', not_run:'未验证', stale:'结果已过期', task_incomplete:'任务未完成', unconfirmed_snapshot:'结果待核实', applied:'已修改', accepted:'已审查', undone:'已撤销'};
const label = (value: string) => labels[value] || value;
const shorten = (text: string, count = 1600) => text.length > count ? text.slice(0,count) + '\n…' : text;
const draftKey = 'eca.desktop.task-draft';
function readDraft(key=draftKey) {try {return sessionStorage.getItem(key) || '';} catch {return '';}}
function App() {
  const [state,setState] = useState<any>({project:null,busy:false,sessions:[],messages:[],events:[],pending:[],changes:[],tasks:[]});
  const [config,setConfig] = useState<any>({recent:[]});
  const [settingsOpen,setSettingsOpen] = useState(false);
const [historyOpen,setHistoryOpen] = useState(false);
const [skillsOpen,setSkillsOpen] = useState(false);
const [automationsOpen,setAutomationsOpen] = useState(false);
const [skillRows,setSkillRows] = useState<SkillRow[]|null>(null);
const [skillMenu,setSkillMenu] = useState<{query:string;index:number}|null>(null);
const [pickedSkills,setPickedSkills] = useState<SkillRow[]>([]);
  const [confirmFull,setConfirmFull] = useState(false);
  const [permissionChanging,setPermissionChanging] = useState(false);
  const [modeChanging,setModeChanging] = useState(false);
  const [goalOpen,setGoalOpen] = useState(false);
  const [modelPickerOpen,setModelPickerOpen] = useState(false);
  const [modelChanging,setModelChanging] = useState(false);
  const [projectChanging,setProjectChanging] = useState(false);
  const projectBusy = useRef(false);
  const [modelSelectionError,setModelSelectionError] = useState('');
  const [queueEdit,setQueueEdit] = useState<{id:string;text:string}|null>(null);
  const [rewindPending,setRewindPending] = useState(false);
  const [error,setError] = useState('');
  const viewKey=state.workspace_owner||state.session_id;
  const promptKey=viewKey?draftKey+'.'+viewKey:draftKey;
  const [draft,setDraft] = useState(()=>({key:draftKey,text:readDraft()}));
  const prompt=draft.key===promptKey?draft.text:readDraft(promptKey);
  const setPrompt=(value:string|((old:string)=>string))=>setDraft(old=>{
    const text=old.key===promptKey?old.text:readDraft(promptKey);
    return {key:promptKey,text:typeof value==='function'?value(text):value};
  });
  const [notice,setNotice] = useState('');
  const [detailsOpen,setDetailsOpen] = useState(()=>sessionStorage.getItem('eca.workspace.open')==='true');
  useEffect(()=>{sessionStorage.setItem('eca.workspace.open',String(detailsOpen));},[detailsOpen]);
  const [agentView,setAgentView] = useState<{id:string;nonce:number}|null>(null);
  const [navCollapsed,setNavCollapsed] = useState(false);
  const [following,setFollowing] = useState(true);
  const [narrow,setNarrow] = useState(() => window.innerWidth < 1180);
  const [sheetOpen,setSheetOpen] = useState(false);
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
  const attachments=useAttachments('main.'+promptKey,sending||projectChanging);
  const promptInput = useRef<HTMLTextAreaElement>(null);
  const modelButton = useRef<HTMLButtonElement>(null);
  const composing = useRef(false);
  const compositionEndedAt = useRef(-Infinity);
  const startBusy = useRef(false);
  const bottom = useRef(true);
  const latest = useRef(state);
  const refreshBusy = useRef(false);
  const refreshAgain = useRef(false);
  const liveBusy = useRef(false);
  // Events are debounced into one attempt per burst, so silently dropping an
  // attempt while a refresh was in flight left the transcript frozen until the
  // next event happened to arrive. Defer instead of dropping.
  const liveAgain = useRef(false);
  const reportedError = useRef(0);
  const refresh = async () => {
    if (refreshBusy.current) {refreshAgain.current = true; return;}
    refreshBusy.current = true;
    try {
      const value = await invoke('snapshot',{preview:true}),old=latest.current;
      if(value.backend_id!==old.backend_id||value.view_revision>old.view_revision||
         (value.view_revision===old.view_revision&&value.session_id===old.session_id&&value.seq>=old.seq)){
        latest.current=value;setState(value);
      }
    }
    catch (e) {setError(String(e));}
  finally {refreshBusy.current=false; if (refreshAgain.current) {refreshAgain.current=false; void refresh();} else if (liveAgain.current) {liveAgain.current=false; void refreshLive();}}
  };
  const loadConfig = async () => {
    const value = await invoke('config.get'); setConfig(value);

  };
  const refreshLive = async () => {
    if(liveBusy.current||refreshBusy.current){liveAgain.current=true;return;}
    liveBusy.current=true;
    try {
      const requested=latest.current;
      const value=await invoke('live',{project_id:requested.project_id,session_id:requested.session_id,stream_id:requested.stream_id,stream_offset:requested.stream_offset}), old=latest.current;
      if(value.backend_id===old.backend_id&&value.view_revision===old.view_revision&&value.session_id===old.session_id&&value.project===old.project&&value.seq>=old.seq) {
        if('stream_delta' in value) {
          // A concurrent full snapshot may already contain these characters.
          if(old.stream_id!==requested.stream_id||old.stream_offset!==requested.stream_offset)return;
          value.stream=(old.stream||'')+value.stream_delta;
        }
        latest.current={...old,...value};setState(latest.current);
      }
    } catch(e){setError(String(e));} finally {liveBusy.current=false; if(liveAgain.current){liveAgain.current=false; void refreshLive();}}
  };
  const namedProjects = useRef<Record<string,boolean>>({});
  useEffect(() => {
    const projectId = state.project_id;
    if (!projectId || namedProjects.current[projectId]) return;
    namedProjects.current[projectId] = true;
    // Older sessions kept the truncated first prompt as their title; name them once per project.
    void invoke('sessions.name-missing', {limit: 8})
      .then((result:any) => { if (result?.renamed?.length) void refresh(); })
      .catch(() => {});
  }, [state.project_id]);
  useEffect(() => {
    void loadConfig().catch(e => setError(String(e))); void refresh();
    let timer: ReturnType<typeof setTimeout>|undefined;
    let full=false;
    const off = window.eca.subscribe(data => {
      if(data.event==='config'){void loadConfig().catch(e=>setError(String(e)));return;}
      if(data.event==='sidechat'||data.event==='subagent_live')return;
      const structural=!['text','model_activity'].includes(data.event||'');
      if(structural)full=true;
      // Text is cheap to append, so a tight tick keeps typing smooth. Anything
      // structural still coalesces over a longer window, and a structural event
      // arriving during a pending tick escalates it: `full` is read when it fires.
      if (!timer) timer=setTimeout(() => {timer=undefined;const goFull=full;full=false;void (goFull?refresh():refreshLive());},structural?80:45);
    });
    const failure = window.eca.onFailure(message => {setError(message); setState((old:any) => ({...old,busy:false,any_busy:false,running_count:0,status:'interrupted',pending:[],stream:'',
      projects:[],sessions:old.sessions.map((s:any)=>({...s,busy:false,side_busy:false,pending_count:0}))}));});
    return () => {off(); failure(); clearTimeout(timer);};
  },[]);
  useEffect(() => {try {sessionStorage.setItem(draft.key,draft.text);} catch { /* storage unavailable */ }},[draft]);
  useEffect(() => {
    const query = matchMedia('(max-width: 1179px)');
    const update = () => {setNarrow(query.matches);setSheetOpen(false);};
    query.addEventListener('change',update);
    return () => query.removeEventListener('change',update);
  },[]);
  useEffect(() => {
    setOlder([]);setCursor(null);setDiff(null);setAgentView(null);bottom.current=true;setFollowing(true);
    setStopping(false);setAnswer('');setAnswered(null);setError('');setNotice('');
    setModelPickerOpen(false);setConfirmFull(false);setDiagnostic(null);
    // A pending rewind belongs to the session it was started in.
    setRewindPending(false);
    reportedError.current=0;
  },[viewKey]);
  const messages=useMemo(()=>[...older,...state.messages],[older,state.messages]);
  useEffect(() => {if (!state.busy) setStopping(false);},[state.busy]);
  useEffect(() => {
    if(state.seq<reportedError.current)reportedError.current=0; // A restarted backend begins a new sequence.
    const failures=state.events.filter((event:any)=>event.event==='error'&&event.seq>reportedError.current);
    if(failures.length){const last=failures[failures.length-1];reportedError.current=last.seq;setError(String(last.data));}
  },[state.events,state.seq]);
  useEffect(() => {if (bottom.current && scroll.current) scroll.current.scrollTop=scroll.current.scrollHeight;},[state.messages,state.stream,state.pending]);
  const perform = async (method:string, params:Record<string,unknown>={}) => {
    const projectOperation=['project.pick','project.recent','project.close','session.switch'].includes(method);
    if(projectOperation&&projectBusy.current)return null;
    if(projectOperation){projectBusy.current=true;setProjectChanging(true);}
    setError('');
    if(method==='session.switch') setNotice('');
    try {
      const result=await invoke(method,{preview:true,project_id:state.project_id,session_id:state.session_id,...params});
      if(!state.project&&result?.session_id&&prompt){
        sessionStorage.setItem(draftKey+'.'+(result.workspace_owner||result.session_id),prompt);
      }
      // Commit the selected view before re-enabling its composer. A snapshot
      // already in flight may still belong to the session we just left.
      if(projectOperation&&result?.backend_id&&
         (result.backend_id!==latest.current.backend_id||result.view_revision>=latest.current.view_revision)){
        latest.current=result;setState(result);
      }
      await refresh(); return result;
    }
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
  // Typing "/" opens a skill picker. Choosing inserts a chip: a literal "/name"
  // in the text would activate nothing, the run itself has to carry the skill.
  const skillMatches=(skillRows||[]).filter(row=>{
    const query=(skillMenu?.query||'').toLowerCase();
    return !query||row.name.toLowerCase().includes(query)||String(row.description||'').toLowerCase().includes(query);
  }).slice(0,8);
  const openSkillMenu=async(query:string)=>{
    if(!skillRows){
      try {const result=await invoke('skills.list');setSkillRows(result?.skills||[]);}
      catch {setSkillRows([]);}
    }
    setSkillMenu({query,index:0});
  };
  const chooseSkill=(row:SkillRow)=>{
    setPickedSkills(old=>old.some(item=>item.name===row.name)?old:(old.length>=3?old:[...old,row]));
    setPrompt('');
    setSkillMenu(null);
    promptInput.current?.focus();
  };
  const start = async () => {
    if ((!prompt.trim()&&!attachments.items.length) || attachments.busy || startBusy.current || modelChanging || projectBusy.current) return;
    startBusy.current=true;setSending(true);bottom.current=true;setNotice('');
    try {
      // Choosing a directory never implicitly runs a draft against that project.
      if (!state.project) {const picked=await pick();if(picked&&attachments.items.length)await attachments.moveTo('main.'+draftKey+'.'+(picked.workspace_owner||picked.session_id));return;}
      const submitted=prompt, queued=!!state.busy;
      // A prompt that came back from "编辑这一轮" rewinds that turn when it is sent.
      const rewinding=rewindPending&&!queued&&!attachments.items.length;
      const payload:any={prompt:submitted,attachments:attachments.items};
      if(!rewinding&&!queued&&pickedSkills.length)payload.skills=pickedSkills.map(item=>item.name);
      const result=await perform(rewinding?'session.resend':(queued?'queue.add':'task.start'),payload);
      if(result) {
        setPrompt(current=>current===submitted?'':current);
        await attachments.clear();
        if(!queued)setPickedSkills([]);
        if(rewinding)setRewindPending(false);
        if(queued)setNotice('已排队；当前任务结束后按顺序发送。');
      }
    } finally {startBusy.current=false;setSending(false);}
  };
  const saveQueued = async () => {
    if(!queueEdit||!queueEdit.text.trim())return;
    const result=await perform('queue.update',{id:queueEdit.id,prompt:queueEdit.text});
    if(result)setQueueEdit(null);
  };
  // Clicking 修改重发 drops the newest instruction straight back into the composer —
  // no dialog in between. The rewind itself still waits for the send.
  const editPrompt = (text:string) => {
    const value=(text||'').trim();
    if(!value||state.busy) return;
    setPrompt(value);
    setRewindPending(true);
    requestAnimationFrame(()=>promptInput.current?.focus());
  };
  const chooseModel = async (choice:string,keepOpen=false) => {
    if(modelChanging||state.busy||projectBusy.current)return false;
    setModelChanging(true);setModelSelectionError('');
    try {
      if(state.project) {await invoke('model.use',{choice,project_id:state.project_id,session_id:state.session_id});await refresh();}
      else {setConfig(await invoke('config.default',{id:choice}));}
      if(!keepOpen)setModelPickerOpen(false);setSettingsOpen(false);setNotice('模型已切换。');return true;
    } catch(e) {setModelSelectionError(String(e));return false;}
    finally{setModelChanging(false);}
  };
  const chooseEffort=async(effort:string)=>{
    if(modelChanging||state.busy||projectBusy.current)return;
    setModelChanging(true);setModelSelectionError('');
    try {
      if(state.project){await invoke('model.reasoning',{effort,project_id:state.project_id,session_id:state.session_id});await refresh();}
      else setConfig(await invoke('config.reasoning',{id:config.defaultId,effort}));
      return true;
    }catch(e){setModelSelectionError(String(e));return false;}
    finally{setModelChanging(false);}
  };
  const choosePermission = async (mode:string) => {
    if(permissionChanging)return;
    setPermissionChanging(true);
    try {await perform('permissions.set',{mode});setConfirmFull(false);}
    finally {setPermissionChanging(false);}
  };
  const chooseMode = async (next:string) => {
    if(modeChanging||state.busy)return;
    setModeChanging(true);
    try {
      const result=await perform('mode.set',{mode:next});
      if(!result)return;
      // Goal mode needs an objective before it means anything; ask for it right away.
      if(next==='goal'&&!result.goal){setNotice('');setGoalOpen(true);}
      else if(next!=='plan')setNotice('');
    } finally {setModeChanging(false);}
  };
  const saveGoal = async (text:string,criteria:string[]) => {
    const result=await perform('goal.set',{goal:{text,criteria}});
    if(result)setNotice('目标已更新；模型会用 goal_update 逐条标记进度。');
    return !!result;
  };
  const clearGoal = async () => {
    if(await perform('goal.set',{goal:null}))setNotice('目标已清除。');
  };
  const runPlan = async () => {
    if(sending||state.busy)return;
    const switched=await perform('mode.set',{mode:'code'});
    if(!switched)return;
    // Hand the approved checklist over verbatim so the model works from the same
    // numbered list the user just read, and keeps updating it with todo.
    const steps=(state.tasks||[]).map((task:any,index:number)=>`${index+1}. ${task.content}`).join('\n');
    const prompt=steps
      ? `按上面的计划开始执行。已批准的计划清单：\n${steps}\n\n按顺序推进：开始一步时用 todo 把它标成 in_progress，真正完成（改动已落地、相关检查跑过）再标 completed。不要跳步，不要为了好看把没验证的标成完成。计划需要调整时说明原因再调整。`
      : '按上面的计划开始执行。先用 todo 记下这份计划的步骤，再按顺序推进；没有验证过的步骤不要标成完成。';
    const result=await perform('task.start',{prompt,attachments:[]});
    if(result)setNotice('已切回编码模式，按计划开始执行。');
  };
  const loadOlder = async () => {
    if(historyBusy.current)return;
    const before=cursor ?? Math.max(0,state.message_total-50);
    const session=state.session_id,project=state.project,backend=state.backend_id;
    historyBusy.current=true;setHistoryLoading(true);
    try {
      const result=await invoke('session.messages',{id:session,before,preview:true,project_id:state.project_id,session_id:session});
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
  useLayoutEffect(()=>{
    const input=promptInput.current;
    if(!input)return;
    const fit=()=>{input.style.height='auto';input.style.height=Math.min(input.scrollHeight,180)+'px';};
    fit();
    window.addEventListener('resize',fit);
    return()=>window.removeEventListener('resize',fit);
  },[prompt,empty,navCollapsed,detailsOpen]);
  const modelSource = state.project
    ? (state.settings?.source==='desktop'
      ? (state.model_selection?.choice==='default'?'桌面默认':'项目指定连接')+' · '+(state.model_selection?.name||'')
      : '项目配置与环境变量')
    : (config.model?'桌面默认模型':'添加一个模型连接即可开始');
  const projectName = state.project?.split(/[\\/]/).pop();
  const activeSession=state.sessions.find((session:any)=>session.id===state.session_id);
  const sessionTitle=activeSession?.title&&activeSession.title!=='New session'?activeSession.title:'新任务';
  const verificationStatus=state.suite?.status||state.verification?.status||'not_run';
  const stopReasons:Record<string,string>={repair_budget_exhausted:'已达到本次自动修复次数，失败记录已保留。',repeated_failure_same_source:'相同代码再次出现相同失败，已停止重复尝试。',unsafe_to_retry:'执行结果不确定或未获授权，未自动重试。'};
  const inspector = <>
    <div className="tabs" role="tablist" aria-label="任务详情">
      {[['changes','文件修改'],['checks','检查结果']].map(([id,text]) =>
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
          <p>{state.suite?.commands?.join(' · ')||state.verification?.command||'可在对话中要求 ECA 运行测试或构建；普通工具执行记录请在对话中查看。'}</p>
          {!!state.suite?.commands?.length&&<p>自动修复上限：{state.suite.repair_budget||0} 次 · 已进行 {Math.max(0,(state.suite.rounds?.length||0)-1)} 次</p>}
          {state.suite?.stop_reason&&<p role="status">{stopReasons[state.suite.stop_reason]||state.suite.stop_reason}</p>}
          {state.suite?.rounds?.map((round:any,i:number)=><div className="check-round" key={i}><div className="check-round-title">第 {i+1} 轮 · {label(round.status)}</div>{round.checks?.map((check:any,j:number)=><LazyDetail key={j} className="check-record" title={<><span className={check.status==='failed'?'failed':''}>{label(check.status)}</span><code>{check.command}</code></>} text={JSON.stringify(check,null,2)}/>)}</div>)}
          {verificationStatus==='passed'&&<p>仅代表上述命令通过；未覆盖的行为和视觉效果仍需检查。</p>}
        </div>
        {!!state.change_impact?.length&&<details className="impact-review"><summary>回归检查建议 · {state.change_impact.length} 个文件</summary><p className="fine-print">根据 Python 代码变化生成的线索；不代表已经验证，也不覆盖所有调用关系。</p>{state.change_impact.slice(-6).map((item:any)=><div key={item.path}><strong>{item.path}</strong><p>{item.risks.includes('transaction_mode')?'事务设置发生变化：检查调用方的提交、回滚及拒绝操作后数据是否保持不变。':'公共代码发生变化：检查调用方、异常行为和相关回归测试。'}{item.symbols.length>0&&` 涉及：${item.symbols.join('、')}`}</p></div>)}</details>}
      </>}
      <details className="review-extra"><summary>任务与活动</summary>
        <div className="panel-label">任务清单</div>
        {!state.tasks.length&&<EmptyState icon={<ListChecks size={25} weight="light"/>} title="等待任务计划">ECA 制定计划后，可以在这里跟踪进度。</EmptyState>}
        {state.tasks.map((t:any,i:number)=><div className="task-row" key={i}><span>{t.status==='completed'?'✓':'·'}</span><span>{t.content}</span><small>{({completed:'已完成',in_progress:'进行中',pending:'待处理'} as Record<string,string>)[t.status]||t.status}</small></div>)}
        <div className="panel-label verification-label">执行活动</div>
        {state.events.filter((event:any)=>!['text','usage','model_activity','title'].includes(event.event)).slice(-30).reverse().map((event:any)=><LazyDetail className="activity" key={event.seq} title={event.event==='subagent_progress'?'子 Agent 活动':({tool:'工具调用',result:'工具返回',request_start:'模型请求',request_end:'请求结束',notice:'运行提示',verification_suite:'验证结果',verification_progress:'验证进度',turn:'新一轮处理'} as Record<string,string>)[event.event]||event.event} text={shorten(typeof event.data==='string'?event.data:JSON.stringify(event.data,null,2),10000)}/>)}
      </details>
      <details className="review-extra"><summary>用量</summary>
        <div className="panel-label">当前会话、子任务与侧聊</div>
        <div className="metric"><span>模型请求</span><strong>{usage.requests||0}</strong></div>
        <div className="metric"><span>已报告 tokens</span><strong>{tokens.toLocaleString()}</strong></div>
        <div className="metric"><span>费用</span><strong>{!prices.length?'未知':prices.map(([currency,value])=>currency+' '+value).join(' / ')}</strong></div>
        {usage.incomplete_cost_requests>0&&<p className="muted">{usage.incomplete_cost_requests} 次请求缺少完整计价依据，已知金额仅为小计。</p>}
        <p className="fine-print">费用基于服务商用量与项目定价配置，不是账单。</p>
      </details>
    </div>
    <button className="diagnose" onClick={async()=>{const result=await perform('diagnostics');if(result)setDiagnostic(result);}} disabled={!state.project}><ArrowClockwise size={15}/>检查项目环境</button>
  </>;
  return <div className={'eca-app workspace'+(state.project&&detailsOpen?' with-inspector':'')+(navCollapsed?' nav-collapsed':'')}>
    <TitleBar title="ECA Desktop"/>
    <Sidebar state={state} config={config} blocked={sending||projectChanging||modelChanging||permissionChanging}
      onPick={pick} onRecent={index=>void perform('project.recent',{index})} onSession={(id,project_id)=>void perform('session.switch',{id,project_id:project_id||state.project_id})} onClose={project_id=>void perform('project.close',{project_id})} onSettings={()=>setSettingsOpen(true)} onHistory={()=>setHistoryOpen(true)} onSkills={()=>setSkillsOpen(true)} onAutomations={()=>setAutomationsOpen(true)}/>
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
          {empty?<Welcome project={projectName} choosing={projectChanging||sending} onProject={pick} onDraft={value=>{setPrompt(value);promptInput.current?.focus();}}/>:<div className="messages">
            {(cursor??state.message_total-50)>0&&<button className="load-older" disabled={historyLoading} onClick={loadOlder}>{historyLoading?'正在加载…':'加载更早的消息'}</button>}
            {older.length>=150&&<p className="fine-print">历史记录分段显示；继续加载查看更早内容。</p>}
            <Transcript key={viewKey} projectId={state.project_id} messages={messages} sessionId={state.session_id} root={state.project||''} busy={state.busy} agents={state.children} changes={state.changes} activity={state.activity} onOpenAgent={agent=>{setDetailsOpen(true);setAgentView(old=>({id:agent.id,nonce:(old?.nonce||0)+1}));}} onRegenerate={()=>{void perform('session.regenerate');}} onEditPrompt={editPrompt}/>
            {(state.children||[]).some((agent:ChildAgent)=>!agent.parent_call_id)&&<section aria-label="历史子任务"><p className="fine-print">其他子任务记录</p><AgentCards agents={state.children.filter((agent:ChildAgent)=>!agent.parent_call_id)} onOpen={agent=>{setDetailsOpen(true);setAgentView(old=>({id:agent.id,nonce:(old?.nonce||0)+1}));}}/></section>}
            {older.length>0&&<button className="log-more" onClick={()=>{setOlder([]);setCursor(null);bottom.current=true;setFollowing(true);if(scroll.current)scroll.current.scrollTop=scroll.current.scrollHeight;}}>返回最近记录</button>}
          </div>}
          {state.busy&&typeof state.activity?.reasoning_text==='string'&&state.activity.reasoning_text.trim()&&
            <article className="message assistant live"><div className="message-label">ECA <span>正在思考</span></div>
              <details className="message-reasoning" open><summary><Sparkle size={13}/><span>思考</span></summary>
                <div className="message-reasoning-text">{state.activity.reasoning_text}</div></details></article>}
          {state.stream&&<article className="message assistant live"><div className="message-label">ECA <span>正在输出</span></div><div className="stream-text">{state.stream}</div></article>}
          {!!(state.tasks||[]).length&&<PlanChecklist tasks={state.tasks} busy={state.busy} phase={state.settings?.mode==='plan'?'plan':'run'}/>}
        </div>
        <div className="composer-wrap">
          {!following&&!empty&&<div className="scroll-return"><button className="jump-latest" onClick={()=>{bottom.current=true;setFollowing(true);scroll.current?.scrollTo({top:scroll.current.scrollHeight});}}><ArrowDown size={14}/>回到最新</button></div>}
          {state.busy&&!waiting&&<RunActivity state={state} stopping={stopping}/>}
          {waiting&&<section className="approval" role="region" aria-label="等待确认">
            <div className="eyebrow">{waiting.kind==='approval'?'需要你的授权':'ECA 有一个问题'}</div><h3>{waiting.message}</h3>
            {waiting.detail&&<div className="approval-detail"><LogText text={waiting.detail}/></div>}
            {waiting.kind==='approval'?<div className="actions"><button disabled={answered===waiting.id} onClick={()=>reply(false)}>拒绝</button><button className="primary" disabled={answered===waiting.id} onClick={()=>reply(true)}>本次允许</button></div>
              :<form onSubmit={e=>{e.preventDefault();void reply(answer);setAnswer('');}}><input aria-label="回答" value={answer} onChange={e=>setAnswer(e.target.value)}/><button className="primary" type="submit" disabled={answered===waiting.id}>发送回答</button></form>}
          </section>}
          {empty&&<div className="composer-context"><button onClick={pick} disabled={projectChanging||sending} title={state.project||'选择项目文件夹'} aria-label="选择任务项目"><FolderOpen size={15}/><span>{projectName||'选择项目'}</span><CaretDown size={11}/></button><span className="local-context"><Desktop size={14}/>本地工作区</span></div>}
          {!!(state.queue||[]).length&&<div className="queue-strip" role="group" aria-label="排队中的消息">
            <div className="queue-label">排队中 · {state.queue.length} 条，当前任务结束后按顺序发送</div>
            {(state.queue||[]).map((item:any,index:number)=>
              <div className="queue-row" key={item.id} data-queue-id={item.id}>
                <span className="queue-order" aria-hidden="true">{index+1}</span>
                {queueEdit?.id===item.id
                  ?<form className="queue-edit" onSubmit={e=>{e.preventDefault();void saveQueued();}}>
                     <input autoFocus aria-label="编辑排队消息" value={queueEdit?.text??''} onChange={e=>setQueueEdit({id:item.id,text:e.target.value})}
                       onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();setQueueEdit(null);}}}/>
                   </form>
                  :<span className="queue-text" title={item.prompt}>{item.prompt}</span>}
                {item.attachments>0&&<span className="queue-files" title={item.attachments+' 个附件'}>{item.attachments} 附件</span>}
                <span className="queue-actions">
                  <button aria-label="上移这条排队消息" title="上移" disabled={index===0||sending} onClick={()=>{void perform('queue.move',{id:item.id,offset:-1});}}><ArrowUp size={14}/></button>
                  <button aria-label="下移这条排队消息" title="下移" disabled={index===state.queue.length-1||sending} onClick={()=>{void perform('queue.move',{id:item.id,offset:1});}}><ArrowDown size={14}/></button>
                  <button className="queue-send" title="打断当前任务，立刻执行这条；没有任务在跑时直接开始" disabled={sending} onClick={()=>{void perform('queue.send-now',{id:item.id});}}>立即发送</button>
                  <button aria-label="编辑这条排队消息" title="编辑" disabled={sending} onClick={()=>setQueueEdit({id:item.id,text:item.prompt})}><PencilSimple size={14}/></button>
                  <button aria-label="取消这条排队消息" title="取消排队" disabled={sending} onClick={()=>{void perform('queue.remove',{id:item.id});}}><X size={14}/></button>
                </span>
              </div>)}
          </div>}
          {state.project&&<GoalBar goal={state.goal||null} onEdit={()=>setGoalOpen(true)} onClear={()=>void clearGoal()}/>}
          {rewindPending&&state.project&&<div className="rewind-note" role="status">
            <span>发送时会先撤回上一轮的指令和回答，再按现在这段内容重跑。</span>
            <button type="button" onClick={()=>setRewindPending(false)}>只是发一条新消息</button>
          </div>}
          <div className="composer" {...attachments.events}>{attachments.preview}
            {!!pickedSkills.length&&<div className="skill-chips" role="group" aria-label="本条消息启用的技能">
              {pickedSkills.map(skill=><span className="skill-chip" key={skill.name}>{skill.name}
                <button type="button" aria-label={'移除技能 '+skill.name} onClick={()=>setPickedSkills(old=>old.filter(item=>item.name!==skill.name))}>×</button></span>)}
            </div>}
            {skillMenu&&skillMatches.length>0&&<SkillMenu items={skillMatches} index={Math.min(skillMenu.index,skillMatches.length-1)}
              onChoose={chooseSkill} onHover={index=>setSkillMenu(old=>old?{...old,index}:old)}/>}
            <textarea rows={3} ref={promptInput} id="prompt" aria-label="任务指令" disabled={projectChanging} placeholder={state.project?'描述你想完成的事…（输入 / 选择技能）':'写下想法，稍后选择项目…'} value={prompt}
              onChange={e=>{
                const value=e.target.value;
                setPrompt(value);
                const command=/^\/(\S*)$/.exec(value);
                if(command)void openSkillMenu(command[1]);
                else setSkillMenu(null);
              }}
              onCompositionStart={()=>{composing.current=true;}}
              onCompositionEnd={()=>{composing.current=false;compositionEndedAt.current=performance.now();}}
              onKeyDown={e=>{
                if(skillMenu){
                  if(e.key==='ArrowDown'||e.key==='ArrowUp'){
                    e.preventDefault();
                    const size=Math.max(1,skillMatches.length);
                    setSkillMenu(old=>old?{...old,index:(old.index+(e.key==='ArrowDown'?1:size-1))%size}:old);
                    return;
                  }
                  if((e.key==='Enter'||e.key==='Tab')&&skillMatches.length){
                    e.preventDefault();
                    chooseSkill(skillMatches[Math.min(skillMenu.index,skillMatches.length-1)]);
                    return;
                  }
                  if(e.key==='Escape'){e.preventDefault();setSkillMenu(null);return;}
                  if(e.key==='Enter'){e.preventDefault();setSkillMenu(null);return;}
                }
                if(e.key!=='Enter'||e.shiftKey||e.altKey)return;
                if(composing.current||e.nativeEvent.isComposing||e.nativeEvent.keyCode===229||performance.now()-compositionEndedAt.current<50)return;
                e.preventDefault();
                if(!e.repeat)void start();
              }}/>
            <div className="composer-toolbar">
              <div className="composer-options">{attachments.button}
              {state.project&&<PermissionControl mode={state.approval_mode||'ask'} busy={permissionChanging||projectChanging} onChange={mode=>mode==='full-access'?setConfirmFull(true):void choosePermission(mode)}/>}
              {state.project&&<ModeControl mode={state.settings?.mode||'code'} busy={modeChanging||state.busy||projectChanging} onChange={mode=>void chooseMode(mode)}/>}
              </div>
              <div className="composer-actions">
              <ContextMeter context={state.context} busy={state.busy} onCompact={async()=>{const result=await perform('context.compact'); if(result)setNotice('上下文已压缩，原始历史仍保留。');}}/>
              <button ref={modelButton} className="model-chip" aria-label="主对话模型" aria-haspopup="dialog" aria-expanded={modelPickerOpen} title={modelSource} disabled={state.busy||sending||projectChanging} onClick={()=>{setModelSelectionError('');setModelPickerOpen(v=>!v);}}><span className={model?'connection-dot':'status-dot'}/><span>{model||'配置模型'}</span>{model&&<span className="thinking-badge">{effortLabels[(state.project?state.settings?.reasoning:config.model?.reasoning)?.value]||'默认'}</span>}<CaretDown size={13}/></button>
              {state.busy?<>
                <button className="queue-button" aria-label="排队发送" title="当前任务结束后按顺序发送这条消息" disabled={(!prompt.trim()&&!attachments.items.length)||attachments.busy||sending||projectChanging} onClick={start}><ArrowUp size={15}/><span>排队</span></button>
                <button className="stop-button" disabled={stopping} onClick={()=>{setStopping(true);void perform('task.cancel',{run_id:state.run_id}).then(result=>{if(!result)setStopping(false);});}}><Stop size={13} weight="fill"/>{stopping?'正在停止':'停止'}</button>
              </>:<button className="send-button" aria-label="发送任务" title={state.project?'发送任务 · Enter':'选择项目后确认发送'} disabled={(!prompt.trim()&&!attachments.items.length)||attachments.busy||sending||modelChanging||projectChanging} onClick={start}>{!state.project&&<span>{sending?'正在打开…':'选择项目并继续'}</span>}<ArrowUp size={17}/></button>}
              </div>
            </div>
          </div>
          {notice&&<div className="composer-notice" role="status"><Check size={15}/>{notice}</div>}
          {state.project&&!state.busy&&state.settings?.mode==='plan'&&(state.messages||[]).some((m:any)=>m.role==='assistant')&&
            <div className="plan-next"><button className="primary" disabled={sending||modeChanging} onClick={()=>void runPlan()}>按此计划执行</button><span>切回编码模式，把上面的计划发给模型</span></div>}
          <div className="composer-meta"><span className="keyboard-hint" aria-label={state.busy?'Enter 排队，Shift 加 Enter 换行':'Enter 发送，Shift 加 Enter 换行'}><span><kbd>↵</kbd>{state.busy?'排队':'发送'}</span><span><kbd>Shift ↵</kbd>换行</span></span></div>
        </div>
      </div>
    </main>
    {state.project&&<Workspace key={viewKey} agentView={agentView} state={state} config={config} review={inspector} open={detailsOpen} onOpen={setDetailsOpen} narrow={narrow} blocked={!!(settingsOpen||modelPickerOpen||confirmFull||diff||diagnostic||waiting)} onDraft={(text:string)=>{setPrompt(p=>p?p+'\n\n'+text:text);setNotice('已放入主对话草稿，确认后发送。');promptInput.current?.focus();}}/>}
    {modelPickerOpen&&<ModelMenu anchor={modelButton} label="选择模型" connections={config.connections||[]} recent={config.recentModels||[]} selectedId={state.project?state.model_selection?.connection_id:config.defaultId} reasoning={state.project?state.settings?.reasoning:config.model?.reasoning} busy={state.busy||modelChanging} error={modelSelectionError} onClose={()=>setModelPickerOpen(false)} onChoose={id=>chooseModel(id,true)} onEffort={chooseEffort} onManage={()=>{setModelPickerOpen(false);setSettingsOpen(true);}} special={state.project?[{id:'default',label:'跟随桌面默认',selected:state.model_selection?.choice==='default',disabled:!config.defaultId},{id:'project',label:'沿用项目配置',selected:state.model_selection?.choice==='project'}]:[]}/>}
  {skillsOpen&&<SkillsPane onClose={()=>setSkillsOpen(false)}/>}
  {automationsOpen&&<AutomationsPane project={state.project||null} onClose={()=>setAutomationsOpen(false)}
    onOpenSession={(projectPath,sessionId)=>{const target=(state.projects||[]).find((item:any)=>String(item.path||'').toLowerCase()===projectPath.toLowerCase());
      setAutomationsOpen(false);
      void perform('session.switch',{id:sessionId,project_id:target?.id||state.project_id}).catch(()=>setNotice('这个项目还没在应用里打开，先打开项目再看这次运行的会话。'));}}/>}
  {historyOpen&&<ExternalHistory projectId={state.project_id} onImported={async(sessionId:string)=>{setHistoryOpen(false);if(sessionId){await perform('session.switch',{id:sessionId});setNotice('已导入为一个新的 ECA 会话，可以接着聊。');}}} onClose={()=>setHistoryOpen(false)}/>}
    <ModelSettings open={settingsOpen} config={config} state={state} onConfig={setConfig} onClose={()=>setSettingsOpen(false)} onUse={chooseModel} onOpened={async()=>{setSettingsOpen(false);await loadConfig().catch(()=>{});await refresh();setNotice('仓库已克隆并打开。');}}/>
    {confirmFull&&<Dialog title="开启完全访问" closeLabel="取消完全访问" onClose={()=>setConfirmFull(false)}><p>在当前会话中自动批准文件修改、命令、联网及外部工具操作，也会放行本会话正在等待的授权。</p><p>命令按当前系统账户权限执行，可能访问项目外文件和网络；不会获得管理员权限。文件工具仍保留路径和冲突检查，已有沙箱及只读模式继续生效。</p><p className="fine-print">不会改变其他会话的审批模式。重新打开项目后恢复项目审批设置；已执行的操作不会因切回逐次确认而撤销。</p><div className="actions"><button onClick={()=>setConfirmFull(false)}>取消</button><button className="primary" disabled={permissionChanging} onClick={()=>choosePermission('full-access')}>开启完全访问</button></div></Dialog>}
    {goalOpen&&state.project&&<GoalDialog goal={state.goal||null} onClose={()=>setGoalOpen(false)} onSave={saveGoal}/>}
    {diff&&<Dialog title={diff.path} name="文件差异" closeLabel="关闭差异" wide onClose={()=>setDiff(null)}><pre className="diff">{diff.diff.split('\n').map((line:string,i:number)=><span key={i} className={line.startsWith('+')?'added':line.startsWith('-')?'removed':''}>{line}{'\n'}</span>)}</pre></Dialog>}
    {diagnostic&&<Dialog title="项目环境" name="环境检查" closeLabel="关闭环境检查" onClose={()=>setDiagnostic(null)}>{diagnostic.checks.map((item:any,i:number)=><div className="diagnostic" key={i}><strong>{item.name} · {item.status}</strong><p>{item.message}</p></div>)}</Dialog>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
