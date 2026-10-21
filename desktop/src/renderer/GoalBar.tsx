import React,{useState} from 'react';
import {CaretDown, CheckCircle, Circle, Flag, PencilSimple, Target, X} from '@phosphor-icons/react';
import {Dialog} from './Dialog';
import './goal-bar.css';

export type Goal = {text:string;status:string;criteria:{text:string;done:boolean}[]};

// The user writes the goal; the model may only tick criteria through goal_update.
export function GoalDialog({goal,onClose,onSave}:{goal:Goal|null;onClose:()=>void;
  onSave:(text:string,criteria:string[])=>Promise<boolean>}) {
  const [text,setText]=useState(goal?.text||'');
  const [lines,setLines]=useState((goal?.criteria||[]).map(item=>item.text).join('\n'));
  const [saving,setSaving]=useState(false);
  const criteria=lines.split('\n').map(value=>value.trim()).filter(Boolean);
  const save=async()=>{
    if(!text.trim()||!criteria.length||saving)return;
    setSaving(true);
    try {if(await onSave(text.trim(),criteria))onClose();} finally {setSaving(false);}
  };
  return <Dialog title={goal?'编辑目标':'设定目标'} closeLabel="关闭目标" className="goal-dialog" onClose={onClose}>
    <label className="goal-field"><span>目标</span>
      <textarea rows={2} value={text} onChange={event=>setText(event.target.value)}
        placeholder="这次要做到什么，一句话说清楚"/>
    </label>
    <label className="goal-field"><span>验收标准 · 每行一条</span>
      <textarea rows={5} value={lines} onChange={event=>setLines(event.target.value)}
        placeholder={'例如：\n登录后刷新仍保持登录\n退出后不再显示个人菜单'}/>
    </label>
    <p className="fine-print">模型用 goal_update 逐条标记进度；标记是它的判断，不等于测试通过或代码正确。</p>
    <div className="actions">
      <button onClick={onClose}>取消</button>
      <button className="primary" disabled={saving||!text.trim()||!criteria.length} onClick={save}>{goal?'保存目标':'开始跟踪'}</button>
    </div>
  </Dialog>;
}

export function GoalChip({active,disabled,onClick}:{active:boolean;disabled?:boolean;onClick:()=>void}) {
  return <button type="button" className={'permission-chip goal-chip'+(active?' is-active':'')} disabled={disabled}
    title={active?'查看或修改当前目标':'设定目标与验收标准'} aria-label={active?'当前目标':'设定目标'} onClick={onClick}>
    <Flag size={14}/><span>目标</span>
  </button>;
}

export function GoalBar({goal,onEdit,onClear}:{goal:Goal|null;onEdit:()=>void;onClear:()=>void}) {
  const [open,setOpen]=useState(false);
  if(!goal||!goal.criteria?.length)return null;
  const criteria=goal.criteria;
  const done=criteria.filter(item=>item.done).length;
  const finished=goal.status==='done';
  return <section className={'goal-bar'+(finished?' is-done':'')} aria-label="当前目标">
    <button type="button" className="goal-summary" aria-expanded={open}
      title={goal.text} onClick={()=>setOpen(value=>!value)}>
      <Target size={15} weight="bold"/>
      <span className="goal-text">{goal.text}</span>
      <span className="goal-progress">{done}/{criteria.length}</span>
      <CaretDown size={11} className="goal-caret"/>
    </button>
    <span className="goal-actions">
      <button type="button" aria-label="编辑目标" title="编辑目标" onClick={onEdit}><PencilSimple size={13}/></button>
      <button type="button" aria-label="清除目标" title="清除目标" onClick={onClear}><X size={13}/></button>
    </span>
    {open&&<ul className="goal-criteria">
      {criteria.map((item,index)=><li key={index} className={item.done?'is-done':''}>
        {item.done?<CheckCircle size={14} weight="fill"/>:<Circle size={14}/>}<span>{item.text}</span></li>)}
      <li className="goal-note">标记由模型填写，仍需你确认结果；{finished?'已全部标记完成。':'未标记完成前不视为达标。'}</li>
    </ul>}
  </section>;
}
