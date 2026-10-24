import React,{useEffect,useMemo,useRef,useState} from 'react';
import {ArrowClockwise, CalendarCheck, CheckCircle, PauseCircle, PencilSimple, PlayCircle, Plus, Trash} from '@phosphor-icons/react';
import './automations.css';

type Automation={id:string;name:string;prompt:string;status:string;rrule:string;schedule:string;project:string;
  permission:string;notification:string;next_run_at:number|null;next_run_nominal_at:number|null;
  last_run_at:number|null;last_status:string|null;last_error:string|null;last_session:string|null;
  model?:string;reasoning_effort?:string};
type View={automations:Automation[];running:string[];permissions:{value:string;label:string}[];
  notifications:string[];enabled:boolean};
type Run={started_at:number;finished_at:number;status:string;trigger:string;session_id:string|null;error:string|null;summary?:string};
type Form={id:string;name:string;prompt:string;freq:string;time:string;interval:number;weekdays:number[];
  start:string;permission:string;notification:string;project:string;rrule:string};

const emptyForm=(project:string):Form=>({id:'',name:'',prompt:'',freq:'DAILY',time:'09:00',interval:2,
  weekdays:[0,1,2,3,4],start:'',permission:'read_only',notification:'always',project,rrule:''});

const stamp=(value:number|null|undefined)=>{
  if(!value)return '—';
  const date=new Date(value),diff=Date.now()-value;
  const text=`${date.getMonth()+1}/${date.getDate()} ${String(date.getHours()).padStart(2,'0')}:${String(date.getMinutes()).padStart(2,'0')}`;
  if(diff<0&&-diff<86400000){
    const minutes=Math.round(-diff/60000);
    return minutes<60?`${text}（${minutes} 分钟后）`:`${text}（${Math.round(minutes/60)} 小时后）`;
  }
  if(diff>=0&&diff<86400000)return `${text}（${Math.max(1,Math.round(diff/60000))} 分钟前）`;
  return text;
};
const statusText:Record<string,string>={ACTIVE:'启用',PAUSED:'已暂停'};
const runText:Record<string,string>={succeeded:'成功',failed:'失败',interrupted:'中断',running:'运行中',limit:'到达轮数上限'};

// Schedules are files on this machine, written and validated by the backend; this
// pane edits them and shows what the scheduler will actually do next.
export function AutomationsPane({onClose,project,onOpenSession}:{onClose:()=>void;project:string|null;
  onOpenSession:(projectPath:string,sessionId:string)=>void}) {
  const [view,setView]=useState<View|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [form,setForm]=useState<Form|null>(null);
  const [preview,setPreview]=useState('');
  const [history,setHistory]=useState<{id:string;runs:Run[];memory:string}|null>(null);
  const timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);

  const load=async()=>{
    try{setView(await window.eca.invoke('automations.list') as View);}
    catch(err){setError(String(err));}
  };
  useEffect(()=>{void load();return ()=>{clearTimeout(timer.current);};},[]);
  useEffect(()=>{
    // The scheduler pushes its own events; a run also adds a session.
    const off=window.eca.subscribe(data=>{
      if(data.event!=='automations'&&data.event!=='automation_run')return;
      clearTimeout(timer.current);
      timer.current=setTimeout(()=>void load(),150);
    });
    return off;
  },[]);
  useEffect(()=>{
    if(!form)return;
    const query:Record<string,unknown>={freq:form.freq,time:form.time,
      interval:Number(form.interval)||1,weekdays:form.weekdays};
    if(form.freq==='ONCE')query.start=form.start||new Date(Date.now()+3600000).toISOString().slice(0,16);
    void window.eca.invoke('automations.rrule',query)
      .then((result:any)=>{setPreview(result.schedule);setForm(old=>old?{...old,rrule:result.rrule}:old);})
      .catch((err:unknown)=>setPreview(String(err)));
  },[form?.freq,form?.time,form?.interval,form?.weekdays,form?.start]);

  const save=async()=>{
    if(!form)return;
    setBusy(true);setError('');
    try{
      await window.eca.invoke('automations.save',{automation:{id:form.id||undefined,name:form.name,
        prompt:form.prompt,rrule:form.rrule,project:form.project,permission:form.permission,
        notification:form.notification}});
      setForm(null);await load();
    }catch(err){setError(String(err));} finally {setBusy(false);}
  };
  const act=async(method:string,params:Record<string,unknown>={})=>{
    setBusy(true);setError('');
    try{await window.eca.invoke(method,params);await load();}
    catch(err){setError(String(err));} finally {setBusy(false);}
  };
  const edit=(row:Automation)=>{
    setHistory(null);
    const freq=row.rrule.includes('COUNT=1')?'ONCE':row.rrule.includes('FREQ=WEEKLY')?'WEEKLY':
      row.rrule.includes('FREQ=HOURLY')?'HOURLY':row.rrule.includes('FREQ=MINUTELY')?'MINUTELY':'DAILY';
    setForm({...emptyForm(row.project),id:row.id,name:row.name,prompt:row.prompt,
      permission:row.permission,notification:row.notification,project:row.project,freq,rrule:row.rrule});
  };
  const openHistory=async(row:Automation)=>{
    if(history?.id===row.id){setHistory(null);return;}
    try{
      const result:any=await window.eca.invoke('automations.history',{id:row.id,limit:12});
      setHistory({id:row.id,runs:result.runs||[],memory:result.memory||''});
    }catch(err){setError(String(err));}
  };

  const rows=view?.automations||[];
  const running=useMemo(()=>new Set(view?.running||[]),[view]);

  return <div className="automations-pane" role="dialog" aria-label="定时任务">
    <header>
      <CalendarCheck size={16} weight="bold"/>
      <h2>定时任务</h2>
      <span className="automations-count">{rows.length} 个计划</span>
      <button className="automations-refresh" aria-label="重新读取" onClick={()=>void load()}><ArrowClockwise size={14}/></button>
      <button className="automations-close" aria-label="关闭定时任务" onClick={onClose}>×</button>
    </header>
    <div className="automations-body">
      {!!view&&!view.enabled&&<p className="automations-note">当前后端没有启用调度：计划会保存，但不会自动运行。</p>}
      {!!error&&<p className="automations-error">{error}</p>}
      <p className="automations-hint">到点后在这个计划绑定的项目里新开一个会话执行；无人值守时只有下面写明的权限范围可用，跑完的结论会自动追加到它的记忆文件。</p>
      {!!view&&!rows.length&&!form&&<p className="automations-empty">还没有定时任务。创建一个：给它一段任务说明和一个时间。</p>}
      {!form&&<button className="automations-create" disabled={!project}
        onClick={()=>{setForm(emptyForm(project||''));setError('');}}>
        <Plus size={14}/>新建定时任务{!project&&'（先打开一个项目）'}</button>}
      {form&&<section className="automation-form" aria-label="编辑定时任务">
        <div className="automation-grid">
          <label>名称<input value={form.name} maxLength={120} placeholder="例：每日构建巡检"
            onChange={event=>setForm({...form,name:event.target.value})}/></label>
          <label>频率<select value={form.freq} onChange={event=>setForm({...form,freq:event.target.value})}>
            <option value="DAILY">每天</option><option value="WEEKLY">每周</option>
            <option value="HOURLY">每 N 小时</option><option value="MINUTELY">每 N 分钟</option>
            <option value="ONCE">单次</option></select></label>
          {(form.freq==='DAILY'||form.freq==='WEEKLY'||form.freq==='HOURLY')&&
            <label>时间<input type="time" value={form.time} onChange={event=>setForm({...form,time:event.target.value})}/></label>}
          {(form.freq==='HOURLY'||form.freq==='MINUTELY')&&
            <label>间隔<input type="number" min={1} max={form.freq==='HOURLY'?24:1440} value={form.interval}
              onChange={event=>setForm({...form,interval:Number(event.target.value)})}/></label>}
          {form.freq==='ONCE'&&<label>时间<input type="datetime-local" value={form.start}
            onChange={event=>setForm({...form,start:event.target.value})}/></label>}
          <label>权限<select value={form.permission} onChange={event=>setForm({...form,permission:event.target.value})}>
            {(view?.permissions||[]).map(item=><option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label>通知<select value={form.notification} onChange={event=>setForm({...form,notification:event.target.value})}>
            <option value="always">每次运行都提醒</option><option value="failed_only">只在失败时提醒</option></select></label>
        </div>
        {form.freq==='WEEKLY'&&<div className="automation-weekdays" role="group" aria-label="星期">
          {['一','二','三','四','五','六','日'].map((label,day)=><button key={label} type="button"
            className={form.weekdays.includes(day)?'is-on':''}
            onClick={()=>setForm({...form,weekdays:form.weekdays.includes(day)
              ?form.weekdays.filter((value:number)=>value!==day):[...form.weekdays,day].sort((a,b)=>a-b)})}>{label}</button>)}
        </div>}
        <label className="automation-prompt">任务说明<textarea rows={5} value={form.prompt} maxLength={8000}
          placeholder="写清它每次要做的事、依据什么、输出成什么样。这段话会作为每一轮的开场指令。"
          onChange={event=>setForm({...form,prompt:event.target.value})}/></label>
        <p className="automation-project">项目：{form.project||'（未选择）'}</p>
        {!!preview&&<p className="automation-preview">计划：{preview}</p>}
        <div className="automation-actions">
          <button onClick={()=>{setForm(null);setError('');}}>取消</button>
          <button className="primary" disabled={busy||!form.name.trim()||!form.prompt.trim()||!form.project}
            onClick={()=>void save()}>{form.id?'保存修改':'创建'}</button>
        </div>
      </section>}
      <ul className="automation-list">
        {rows.map(row=><li key={row.id} className={'automation-row is-'+(row.status||'').toLowerCase()}>
          <div className="automation-summary">
            <span className={'automation-dot is-'+(row.status||'').toLowerCase()} title={statusText[row.status]||row.status}/>
            <button className="automation-name" onClick={()=>void openHistory(row)}>
              <strong>{row.name}</strong>
              <small>{row.schedule} · 下次 {stamp(row.next_run_at)}</small>
            </button>
            <span className="automation-state">
              {running.has(row.id)?<em>运行中</em>:
                <em className={row.last_status?'is-known':''}>{row.last_status?runText[row.last_status]||row.last_status:'还没运行过'}</em>}
            </span>
            <div className="automation-buttons">
              <button title="立即运行一次" disabled={busy||running.has(row.id)}
                onClick={()=>void act('automations.run',{id:row.id})}><PlayCircle size={15}/></button>
              <button title={row.status==='ACTIVE'?'暂停':'启用'} disabled={busy}
                onClick={()=>void act('automations.save',{automation:{id:row.id,
                  status:row.status==='ACTIVE'?'PAUSED':'ACTIVE'}})}>
                {row.status==='ACTIVE'?<PauseCircle size={15}/>:<CheckCircle size={15}/>}</button>
              <button title="编辑" disabled={busy} onClick={()=>edit(row)}><PencilSimple size={15}/></button>
              <button title="删除" disabled={busy} onClick={()=>{
                if(window.confirm(`删除定时任务「${row.name}」？运行记录和记忆文件会一起删掉，已产生的会话保留。`))
                  void act('automations.delete',{id:row.id});}}><Trash size={15}/></button>
            </div>
          </div>
          {history?.id===row.id&&<div className="automation-history">
            {!history.runs.length&&<p>还没有运行记录。</p>}
            {history.runs.map((run,index)=><div key={index} className={'automation-run is-'+run.status}>
              <span>{stamp(run.started_at)}</span>
              <span className="automation-run-status">{runText[run.status]||run.status}{run.trigger==='manual'?'（手动）':''}</span>
              {!!run.session_id&&<button onClick={()=>onOpenSession(row.project,String(run.session_id))}>打开会话</button>}
              {!!run.error&&<span className="automation-run-error" title={run.error}>{run.error.slice(0,90)}</span>}
            </div>)}
            {!!history.memory&&<details className="automation-memory"><summary>记忆文件</summary>
              <pre>{history.memory}</pre></details>}
          </div>}
          {!!row.last_error&&<p className="automation-error-line">{row.last_error.slice(0,160)}</p>}
        </li>)}
      </ul>
    </div>
  </div>;
}
