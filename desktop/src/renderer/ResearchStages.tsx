import React,{useState} from 'react';
import {CaretDown, ChartLineUp, FileText, Flask} from '@phosphor-icons/react';
import './research-stages.css';

type Stage={id:string;label:string};
type Artifact={name:string;bytes:number};
export type Research={
  stage:string;label:string;stages:Stage[];artifacts:Artifact[];
  counts:{sources:number;verified_sources:number;claims:number;verified_claims:number;
          runs:number;reading:number;report:boolean;deviations:boolean};
  history:{from:string|null;to:string|null;at:string;note:string}[];
};
export type Business={
  stage:string;label:string;stages:Stage[];artifacts:Artifact[];
  counts:{sources:number;claims:number;verified_claims:number;contradicted_claims:number;
          unit:boolean;verdict:boolean};
  history:{from:string|null;to:string|null;at:string;note:string}[];
  verdict?:{key:string|null;label:string|null;confidence:string|null}|null;
};

const size=(bytes:number)=>bytes<1024?`${bytes} B`:`${(bytes/1024).toFixed(1)} KB`;

type Metric={label:string;value:string|number;detail?:string;title?:string};

// The stage strip is state, not decoration: it shows where the workflow actually
// is and how much evidence is on disk. It never offers to tick a stage forward —
// that is the model's call through the workflow tools, and the gates are on disk.
function StageStrip({workflow,title,folder,mark,busy,metrics,empty,hint}:{
  workflow:{stage:string;label:string;stages:Stage[];artifacts:Artifact[];
            history:{from:string|null;to:string|null;at:string;note:string}[]};
  title:string;folder:string;mark:React.ReactNode;busy?:boolean;metrics:Metric[];empty:string;hint:string;
}) {
  const [open,setOpen]=useState(false);
  if(!workflow||!workflow.stages?.length)return null;
  const index=workflow.stages.findIndex(item=>item.id===workflow.stage);
  const last=workflow.history?.[workflow.history.length-1];
  const back=last&&last.to===workflow.stage&&last.from&&workflow.stages.findIndex(item=>item.id===last.from)>index;
  return <section className="research-stages" aria-label={`${title}阶段`}>
    <div className="research-head">
      <span className="research-mark">{mark}</span>
      <strong>{title}</strong>
      <span className="research-now">{workflow.label}</span>
      {back&&<span className="research-back" title={last?.note||''}>回退{last?.note?`：${last.note}`:''}</span>}
      {!busy&&<span className="research-quiet">未在运行</span>}
      <span className="research-counts" title={hint}>
        {metrics.map(item=><span key={item.label} title={item.title}>
          {item.label} {item.value}{item.detail&&<i>{item.detail}</i>}
        </span>)}
      </span>
      <button type="button" className="research-toggle" aria-expanded={open}
        onClick={()=>setOpen(value=>!value)} title={open?'收起制品':`查看 ${folder} 制品`}>
        <FileText size={13}/><span>{workflow.artifacts.length}</span><CaretDown size={11}/>
      </button>
    </div>
    <ol className="research-track">
      {workflow.stages.map((item,position)=><li key={item.id}
        className={'research-step'+(position===index?' is-current':position<index?' is-done':' is-ahead')}
        aria-current={position===index?'step':undefined}>
        <span>{item.label}</span>
      </li>)}
    </ol>
    {open&&<div className="research-artifacts">
      {!workflow.artifacts.length&&<p>{empty}</p>}
      {!!workflow.artifacts.length&&<ul>{workflow.artifacts.map(item=><li key={item.name}>
        <code>{folder}/{item.name}</code><small>{size(item.bytes)}</small></li>)}</ul>}
    </div>}
  </section>;
}

export function ResearchStages({research,busy}:{research?:Research|null;busy?:boolean}) {
  if(!research?.stages?.length)return null;
  const c=research.counts;
  return <StageStrip workflow={research} title="科研" folder=".eca/research" busy={busy}
    mark={<Flask size={14} weight="bold"/>}
    hint="已登记来源 / 其中在线核验过 · 断言 / 其中已验证 · 运行次数"
    metrics={[{label:'源',value:c.sources,detail:`/${c.verified_sources}核`},
              {label:'断言',value:c.claims,detail:`/${c.verified_claims}核`},
              {label:'运行',value:c.runs}]}
    empty="还没有制品。模型会先写 proposal.md，再登记来源。"/>;
}

// Business mode reads markets, not code: the strip shows sources, claims and the
// verdict the gates allowed, and nothing here can be ticked by hand either.
export function VentureStages({business,busy}:{business?:Business|null;busy?:boolean}) {
  if(!business?.stages?.length)return null;
  const c=business.counts;
  const verdict=business.verdict?.label;
  return <StageStrip workflow={business} title="商业" folder=".eca/business" busy={busy}
    mark={<ChartLineUp size={14} weight="bold"/>}
    hint="已登记来源 · 断言 / 其中已验证 · 结论是否已落盘"
    metrics={[{label:'源',value:c.sources},
              {label:'断言',value:c.claims,detail:`/${c.verified_claims}核`},
              ...(c.contradicted_claims?[{label:'反证',value:c.contradicted_claims}]:[]),
              {label:'结论',value:verdict||'未出'}]}
    empty="还没有制品。模型会先写 brief.md，再登记公开来源。"/>;
}
