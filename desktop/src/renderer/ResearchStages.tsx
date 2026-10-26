import React,{useState} from 'react';
import {CaretDown, FileText, Flask} from '@phosphor-icons/react';
import './research-stages.css';

type Stage={id:string;label:string};
type Artifact={name:string;bytes:number};
export type Research={
  stage:string;label:string;stages:Stage[];artifacts:Artifact[];
  counts:{sources:number;verified_sources:number;claims:number;verified_claims:number;
          runs:number;reading:number;report:boolean;deviations:boolean};
  history:{from:string|null;to:string|null;at:string;note:string}[];
};

const size=(bytes:number)=>bytes<1024?`${bytes} B`:bytes<1024*1024?`${(bytes/1024).toFixed(1)} KB`:`${(bytes/1048576).toFixed(1)} MB`;

// The stage strip is state, not decoration: it shows where the workflow actually
// is and how much evidence is on disk. It never offers to tick a stage forward —
// that is the model's call through research_stage, and the gates are on disk.
export function ResearchStages({research,busy}:{research?:Research|null;busy?:boolean}) {
  const [open,setOpen]=useState(false);
  if(!research||!research.stages?.length)return null;
  const index=research.stages.findIndex(item=>item.id===research.stage);
  const counts=research.counts;
  const last=research.history?.[research.history.length-1];
  const back=last&&last.to===research.stage&&last.from&&research.stages.findIndex(item=>item.id===last.from)>index;
  return <section className="research-stages" aria-label="科研阶段">
    <div className="research-head">
      <span className="research-mark"><Flask size={14} weight="bold"/></span>
      <strong>科研</strong>
      <span className="research-now">{research.label}</span>
      {back&&<span className="research-back" title={last?.note||''}>回退{last?.note?`：${last.note}`:''}</span>}
      {!busy&&<span className="research-quiet">未在运行</span>}
      <span className="research-counts" title="已登记来源 / 其中在线核验过 · 断言 / 其中已验证 · 运行次数">
        <span>源 {counts.sources}<i>/{counts.verified_sources}核</i></span>
        <span>断言 {counts.claims}<i>/{counts.verified_claims}核</i></span>
        <span>运行 {counts.runs}</span>
      </span>
      <button type="button" className="research-toggle" aria-expanded={open}
        onClick={()=>setOpen(value=>!value)} title={open?'收起制品':'查看 .eca/research 制品'}>
        <FileText size={13}/><span>{research.artifacts.length}</span><CaretDown size={11}/>
      </button>
    </div>
    <ol className="research-track">
      {research.stages.map((item,position)=><li key={item.id}
        className={'research-step'+(position===index?' is-current':position<index?' is-done':' is-ahead')}
        aria-current={position===index?'step':undefined}>
        <span>{item.label}</span>
      </li>)}
    </ol>
    {open&&<div className="research-artifacts">
      {!research.artifacts.length&&<p>还没有制品。模型会先写 proposal.md，再登记来源。</p>}
      {!!research.artifacts.length&&<ul>{research.artifacts.map(item=><li key={item.name}>
        <code>.eca/research/{item.name}</code><small>{size(item.bytes)}</small></li>)}</ul>}
    </div>}
  </section>;
}
