import React from 'react';
import {Check, PaintBrush, UserCircle, FileText} from '@phosphor-icons/react';

export type Personal = {name:string; role:string; about:string; style:string; instructions:string};
export const emptyPersonal:Personal = {name:'',role:'',about:'',style:'',instructions:''};

const THEMES:[string,string][] = [['system','跟随系统'],['light','浅色'],['dark','深色']];

function Pane({title,lead,label,children}:{title:string;lead:string;label:string;children:React.ReactNode}) {
  return <section className="connection-editor personal-pane" aria-label={label}>
    <div className="connection-scroll">
      <header className="connection-heading"><div><h3>{title}</h3><p>{lead}</p></div></header>
      {children}
    </div>
  </section>;
}

export function AppearancePane({theme,onTheme}:{theme:string;onTheme:(value:string)=>void}) {
  return <Pane title="外观主题" label="外观主题" lead="只改变界面显示，不影响模型、项目和审批档位。">
    <section className="connection-section" aria-labelledby="appearance-theme-heading">
      <h4 id="appearance-theme-heading"><PaintBrush size={15}/>背景主题</h4>
      <div className="theme-choices" role="radiogroup" aria-label="背景主题">
        {THEMES.map(([value,label])=>
          <button key={value} type="button" role="radio" aria-checked={theme===value} aria-label={label}
            className={'theme-choice'+(theme===value?' active':'')} onClick={()=>onTheme(value)}>
            {theme===value?<Check size={13}/>:<span className="theme-dot"/>}<span>{label}</span></button>)}
      </div>
      <p className="fine-print">跟随系统会随 Windows 的浅色/深色切换。</p>
    </section>
  </Pane>;
}

export function ProfilePane({value,onChange,onSave,saving,status,busy}:
  {value:Personal;onChange:(value:Personal)=>void;onSave:()=>void;saving:boolean;status:string;busy?:boolean}) {
  const initial = (value.name||'你').trim().slice(0,1);
  return <Pane title="个人信息" label="个人信息" lead="让模型知道它在和谁合作，以及你希望它怎么回答。">
    <div className="profile-identity">
      <span className="profile-avatar" aria-hidden="true">{initial}</span>
      <div><strong>{value.name||'还没有称呼'}</strong><small>{value.role||'在下面填写你的身份'}</small></div>
    </div>
    <section className="connection-section" aria-labelledby="profile-basic-heading">
      <h4 id="profile-basic-heading"><UserCircle size={15}/>基本</h4>
      <div className="form-row">
        <div className="field"><label htmlFor="personal-name">称呼</label>
          <input id="personal-name" maxLength={80} placeholder="模型怎么称呼你" value={value.name}
            onChange={event=>onChange({...value,name:event.target.value})}/></div>
        <div className="field"><label htmlFor="personal-role">身份</label>
          <input id="personal-role" maxLength={120} placeholder="例如：后端工程师 / 产品设计" value={value.role}
            onChange={event=>onChange({...value,role:event.target.value})}/></div>
      </div>
    </section>
    <section className="connection-section" aria-labelledby="profile-custom-heading">
      <h4 id="profile-custom-heading"><UserCircle size={15}/>自定义</h4>
      <div className="field"><label htmlFor="personal-about">关于我</label>
        <textarea id="personal-about" rows={4} maxLength={2000}
          placeholder="你希望模型了解的背景：常做的项目、技术栈、正在解决的问题"
          value={value.about} onChange={event=>onChange({...value,about:event.target.value})}/></div>
      <div className="field"><label htmlFor="personal-style">回答偏好</label>
        <textarea id="personal-style" rows={3} maxLength={1000}
          placeholder="例如：先给结论再给依据；用中文回答；少用列表"
          value={value.style} onChange={event=>onChange({...value,style:event.target.value})}/></div>
      <p className="fine-print">这几项会写进每轮对话的系统提示词，所有项目共用，只影响措辞与偏好，不改变权限。</p>
    </section>
    <div className="personal-actions">
      {(saving||status)&&<span className="config-status" role="status">{saving?'正在保存…':status}</span>}
      <button className="primary" disabled={saving||busy} onClick={onSave}>保存个人信息</button>
    </div>
  </Pane>;
}

export function InstructionsPane({value,onChange,onSave,saving,status,busy}:
  {value:Personal;onChange:(value:Personal)=>void;onSave:()=>void;saving:boolean;status:string;busy?:boolean}) {
  return <Pane title="全局指令" label="全局指令" lead="适用于所有项目的长期要求，等同数据中心里的 AGENTS.md。">
    <section className="connection-section" aria-labelledby="instructions-body-heading">
      <h4 id="instructions-body-heading"><FileText size={15}/>内容</h4>
      <div className="field"><label htmlFor="personal-instructions">每轮对话都会带上</label>
        <textarea id="personal-instructions" rows={12} maxLength={20000} spellCheck={false}
          placeholder={'每行一条，例如：\n回答前先说结论\n提交信息用英文\n不要自动提交或推送'}
          value={value.instructions} onChange={event=>onChange({...value,instructions:event.target.value})}/></div>
      <p className="fine-print">项目自己的 AGENTS.md 仍然优先；这里不能改动审批权限或工具限制。</p>
    </section>
    <div className="personal-actions">
      {(saving||status)&&<span className="config-status" role="status">{saving?'正在保存…':status}</span>}
      <button className="primary" disabled={saving||busy} onClick={onSave}>保存全局指令</button>
    </div>
  </Pane>;
}
