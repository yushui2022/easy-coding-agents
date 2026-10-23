import React from 'react';
import './skill-menu.css';

export type SkillRow = {name: string; source: string; description?: string; scope?: string};

const labels:Record<string,string>={project:'项目',eca:'ECA',codex:'Codex',claude:'Claude',workbuddy:'WorkBuddy'};

// Rendered above the composer. mousedown (not click) so the textarea keeps focus.
export function SkillMenu({items,index,onChoose,onHover}:{
  items:SkillRow[];index:number;onChoose:(row:SkillRow)=>void;onHover:(index:number)=>void;
}) {
  return <div className="skill-menu" role="listbox" aria-label="选择技能">
    <div className="skill-menu-head"><span>技能</span><small>↑↓ 选择 · Enter 插入 · Esc 取消</small></div>
    {items.map((row,position)=>
      <button key={row.source+row.name} type="button" role="option" aria-selected={position===index}
        className={'skill-option'+(position===index?' is-active':'')}
        onMouseEnter={()=>onHover(position)}
        onMouseDown={event=>{event.preventDefault();onChoose(row);}}>
        <span className="skill-option-top">
          <span className="skill-badge" data-source={row.source}>{labels[row.source]||row.source}</span>
          <span className="skill-name">{row.name}</span>
        </span>
        {row.description?<small className="skill-desc">{row.description}</small>:null}
      </button>)}
  </div>;
}
