import React,{useState} from 'react';
import {CaretDown, CheckCircle, Circle, CircleDashed, ListChecks, LockSimple, XCircle} from '@phosphor-icons/react';
import './plan-checklist.css';

type Task={content:string;status:string;id?:string;blocked?:boolean;blocked_by?:string[];failed_by?:string[]};

// The same list is the plan before approval and the running checklist afterwards.
// Items are written by the model through the todo tool; the UI only renders them.
// A task is blocked while a dependency is unfinished, and the todo tool refuses to
// mark a blocked task completed, so this badge is state the model cannot talk around.
export function PlanChecklist({tasks,phase,busy}:{tasks:Task[];phase:'plan'|'run';busy:boolean}) {
  const [open,setOpen]=useState(true);
  if(!tasks?.length)return null;
  const done=tasks.filter(task=>task.status==='completed').length;
  const blocked=tasks.filter(task=>task.blocked&&task.status!=='completed').length;
  const failed=tasks.filter(task=>task.status==='failed').length;
  const collapsed=!open&&tasks.length>3;
  const shown=collapsed?tasks.slice(0,3):tasks;
  const title=phase==='plan'?(busy?'正在整理计划':'计划步骤'):'执行清单';
  return <section className={'plan-checklist'+(phase==='plan'?' is-plan':'')+(done===tasks.length?' is-done':'')}
    aria-label={title}>
    <header>
      <ListChecks size={14} weight="bold"/>
      <span className="plan-title">{title}</span>
      <span className="plan-progress">{done}/{tasks.length}</span>
      {blocked>0&&<span className="plan-count is-blocked" title={tasks.filter(t=>t.blocked&&t.status!=='completed')
        .map(t=>`${t.content}：等待 ${(t.blocked_by||[]).join('、')}`).join('\n')}>{blocked} 阻塞</span>}
      {failed>0&&<span className="plan-count is-failed">{failed} 失败</span>}
      <button type="button" className="plan-toggle" aria-expanded={open}
        onClick={()=>setOpen(value=>!value)}>
        <span>{open?'收起':'展开'}</span><CaretDown size={11}/>
      </button>
    </header>
    <ol>
      {shown.map((task,index)=><li key={index}
        className={'plan-item is-'+task.status+(task.blocked&&task.status!=='completed'?' is-blocked':'')}
        title={task.blocked_by?.length?`依赖未完成：${task.blocked_by.join('、')}`:undefined}>
        {task.status==='completed'?<CheckCircle size={14} weight="fill"/>
          :task.status==='failed'?<XCircle size={14} weight="fill"/>
          :task.blocked?<LockSimple size={14}/>
          :task.status==='in_progress'?<CircleDashed size={14}/>:<Circle size={14}/>}
        <span>{task.content}</span>
        {task.blocked&&task.status!=='completed'&&<span className="plan-badge">阻塞</span>}
        {task.status==='failed'&&<span className="plan-badge is-failed">失败</span>}
      </li>)}
      {collapsed&&<li className="plan-more">还有 {tasks.length-shown.length} 步</li>}
    </ol>
    {phase==='plan'&&!busy&&<p className="plan-hint">确认无误后点下方「按此计划执行」，模型会按这份清单逐条推进。</p>}
  </section>;
}
