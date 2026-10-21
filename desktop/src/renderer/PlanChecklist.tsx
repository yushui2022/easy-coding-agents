import React,{useState} from 'react';
import {CaretDown, CheckCircle, Circle, CircleDashed, ListChecks} from '@phosphor-icons/react';
import './plan-checklist.css';

type Task={content:string;status:string};

// The same list is the plan before approval and the running checklist afterwards.
// Items are written by the model through the todo tool; the UI only renders them.
export function PlanChecklist({tasks,phase,busy}:{tasks:Task[];phase:'plan'|'run';busy:boolean}) {
  const [open,setOpen]=useState(true);
  if(!tasks?.length)return null;
  const done=tasks.filter(task=>task.status==='completed').length;
  const collapsed=!open&&tasks.length>3;
  const shown=collapsed?tasks.slice(0,3):tasks;
  const title=phase==='plan'?(busy?'正在整理计划':'计划步骤'):'执行清单';
  return <section className={'plan-checklist'+(phase==='plan'?' is-plan':'')+(done===tasks.length?' is-done':'')}
    aria-label={title}>
    <header>
      <ListChecks size={14} weight="bold"/>
      <span className="plan-title">{title}</span>
      <span className="plan-progress">{done}/{tasks.length}</span>
      <button type="button" className="plan-toggle" aria-expanded={open}
        onClick={()=>setOpen(value=>!value)}>
        <span>{open?'收起':'展开'}</span><CaretDown size={11}/>
      </button>
    </header>
    <ol>
      {shown.map((task,index)=><li key={index} className={'plan-item is-'+task.status}>
        {task.status==='completed'?<CheckCircle size={14} weight="fill"/>
          :task.status==='in_progress'?<CircleDashed size={14}/>:<Circle size={14}/>}
        <span>{task.content}</span>
      </li>)}
      {collapsed&&<li className="plan-more">还有 {tasks.length-shown.length} 步</li>}
    </ol>
    {phase==='plan'&&!busy&&<p className="plan-hint">确认无误后点下方「按此计划执行」，模型会按这份清单逐条推进。</p>}
  </section>;
}
