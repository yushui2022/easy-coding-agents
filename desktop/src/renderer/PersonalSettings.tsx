import React,{useEffect,useMemo,useState} from 'react';
import {Check, PaintBrush, UserCircle, FileText, GithubLogo} from '@phosphor-icons/react';

export type Personal = {name:string; role:string; about:string; style:string; instructions:string};
export const emptyPersonal:Personal = {name:'',role:'',about:'',style:'',instructions:''};
type Stats = {total_tokens:number; requests:number; active_days:number;
  peak:{date:string; tokens:number}|null; current_streak:number; longest_streak:number;
  days:{date:string; tokens:number}[]; models:{model:string; requests:number}[]};

const THEMES:[string,string][] = [['system','跟随系统'],['light','浅色'],['dark','深色']];
const WEEKS = 26;
const compact = (value:number) => value >= 100_000_000 ? `${(value/100_000_000).toFixed(1)} 亿`
  : value >= 10_000 ? `${(value/10_000).toFixed(1)} 万` : String(value);

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

// Activity grid: one column per week, one row per weekday, coloured by daily tokens.
// Only recorded requests are drawn; a day without a request stays empty.
function Heatmap({days}:{days:{date:string; tokens:number}[]}) {
  const [mode,setMode]=useState<'day'|'week'>('day');
  const {cells, weeks, months, peak} = useMemo(()=>{
    const byDate = new Map(days.map(row=>[row.date, row.tokens]));
    const today = new Date(); today.setHours(0,0,0,0);
    // Start on the Monday of the first of 26 weeks so columns are whole weeks.
    const start = new Date(today);
    start.setDate(today.getDate() - (WEEKS*7 - 1) - ((today.getDay()+6)%7));
    const peak = days.reduce((max,row)=>Math.max(max,row.tokens),0);
    const cells:{key:string; level:number; label:string}[] = [];
    const weeks:{key:string; tokens:number; level:number; label:string}[] = [];
    const months:[string,number][] = [];
    let lastMonth = '';
    for(let week=0; week<WEEKS; week+=1){
      let weekTokens = 0;
      let weekLabel = '';
      for(let day=0; day<7; day+=1){
        const date = new Date(start);
        date.setDate(start.getDate() + week*7 + day);
        const key = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
        const tokens = byDate.get(key) || 0;
        weekTokens += tokens;
        if(!weekLabel && tokens) weekLabel = `${date.getMonth()+1}月${date.getDate()}日`;
        if(date>today){cells.push({key, level:-1, label:''});continue;}
        const level = tokens===0 ? 0 : Math.min(4, 1+Math.floor((tokens/(peak||1))*3.999));
        cells.push({key, level, label:`${date.getMonth()+1}月${date.getDate()}日 · ${compact(tokens)} Token`});
        const month = `${date.getMonth()+1}月`;
        if(month!==lastMonth){months.push([month, week]);lastMonth=month;}
      }
      weeks.push({key:`w${week}`, tokens:weekTokens, label:`${weekLabel||''} 那周 · ${compact(weekTokens)} Token`,
        level:weekTokens===0?0:Math.min(4, 1+Math.floor((weekTokens/(peak*7||1))*3.999))});
    }
    return {cells, weeks, months, peak};
  }, [days]);
  return <div className="heatmap">
    <div className="heatmap-head">
      <span className="heatmap-caption">近 {WEEKS} 周</span>
      <div className="heatmap-modes" role="group" aria-label="统计粒度">
        <button type="button" aria-pressed={mode==='day'} className={mode==='day'?'active':''} onClick={()=>setMode('day')}>每天</button>
        <button type="button" aria-pressed={mode==='week'} className={mode==='week'?'active':''} onClick={()=>setMode('week')}>每周</button>
      </div>
    </div>
    {mode==='day'
      ? <div className="heatmap-grid" role="img" aria-label={`近 ${WEEKS} 周每天消耗的 token，峰值 ${peak}`}>
          {cells.map(cell=>cell.level<0?<span key={cell.key} className="heat-day is-empty"/>
            :<span key={cell.key} className={'heat-day level-'+cell.level} title={cell.label}/>)}
        </div>
      : <div className="heatmap-grid is-weekly" role="img" aria-label={`近 ${WEEKS} 周每周消耗的 token`}>
          {weeks.map(week=><span key={week.key} className={'heat-week level-'+week.level} title={week.label}/>)}
        </div>}
    <div className="heatmap-months">{months.map(([label,week])=><span key={label+week} style={{gridColumn:week+1}}>{label}</span>)}</div>
  </div>;
}

export function ProfilePane({value,onChange,onSave,saving,status,busy}:
  {value:Personal;onChange:(value:Personal)=>void;onSave:()=>void;saving:boolean;status:string;busy?:boolean}) {
  const [stats,setStats]=useState<Stats|null>(null);
  const [statsNote,setStatsNote]=useState('');
  const [handle,setHandle]=useState('');
  useEffect(()=>{
    let live = true;
    void window.eca.invoke('usage.stats')
      .then((value:Stats)=>{if(live)setStats(value);})
      .catch(()=>{if(live)setStatsNote('打开一个项目后，这里会显示这个项目的用量统计。');});
    void window.eca.invoke('github.status')
      .then((value:any)=>{if(live)setHandle(value?.connected?String(value.login||''):'');})
      .catch(()=>{});
    return ()=>{live=false;};
  },[]);
  const initial = (value.name||'你').trim().slice(0,1);
  const days = stats?.days || [];
  const average = stats && stats.requests ? Math.round(stats.total_tokens/stats.requests) : 0;
  return <Pane title="个人信息" label="个人信息" lead="让模型知道它在和谁合作，以及你希望它怎么回答。">
    <div className="profile-hero">
      <span className="profile-avatar-lg" aria-hidden="true">{initial}</span>
      <strong className="profile-name">{value.name||'未命名'}</strong>
      <small className="profile-handle">{handle?`@${handle}`:'本地账号'}</small>
    </div>
    <div className="profile-stats" role="list" aria-label="本地使用统计">
      {[['累计 Token', stats?compact(stats.total_tokens):'—'],
        ['活跃天数', stats?String(stats.active_days):'—'],
        ['当前连续', stats?`${stats.current_streak} 天`:'—'],
        ['最长连续', stats?`${stats.longest_streak} 天`:'—'],
        ['请求数', stats?String(stats.requests):'—']].map(([label,value])=>
        <div key={label} role="listitem"><strong>{value}</strong><span>{label}</span></div>)}
    </div>
    <section className="connection-section profile-activity" aria-labelledby="profile-activity-heading">
      <h4 id="profile-activity-heading"><UserCircle size={15}/>Token 活动</h4>
      {days.length ? <Heatmap days={days}/> : <p className="fine-print">{statsNote||'这个项目还没有记录用量；跑一次任务就会出现。'}</p>}
      <p className="fine-print">统计来自当前项目的本地用量账本（最多近 {WEEKS} 周），不上传，不含未回报 token 的请求。</p>
    </section>
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
    {(stats?.models?.length||average)?<section className="connection-section" aria-labelledby="profile-insight-heading">
      <h4 id="profile-insight-heading"><GithubLogo size={15}/>洞察</h4>
      <dl className="profile-insight">
        <div><dt>平均每次请求</dt><dd>{average} tokens</dd></div>
        {stats?.models?.[0]&&<div><dt>最常用模型</dt><dd>{stats.models[0].model} · {stats.models[0].requests} 次</dd></div>}
        {stats?.peak&&<div><dt>单日峰值</dt><dd>{stats.peak.date} · {compact(stats.peak.tokens)}</dd></div>}
      </dl>
    </section>:null}
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
