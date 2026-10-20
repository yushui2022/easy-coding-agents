import React from 'react';
import {CaretRight, Circle, CheckCircle, WarningCircle, PauseCircle} from '@phosphor-icons/react';
import blue from '../assets/agent-marks/square-blue.png';
import sage from '../assets/agent-marks/circle-sage.png';
import lavender from '../assets/agent-marks/triangle-lavender.png';
import honey from '../assets/agent-marks/hexagon-honey.png';
import coral from '../assets/agent-marks/doubleloop-coral.png';
import teal from '../assets/agent-marks/quatrefoil-teal.png';
import './agents.css';

export type ChildAgent = {
  id:string; title:string; status:string; mode:string; model?:string; model_profile?:string;
  isolated?:boolean; ordinal:number; parent_call_id?:string; parent_message_index?:number;
  stop_reason?:string;
};
const marks=[blue,sage,lavender,honey,coral,teal];
export const agentName=(agent:ChildAgent)=>`子智能体 ${String(agent.ordinal||1).padStart(2,'0')}`;
export function AgentMark({agent,size=24}:{agent:ChildAgent;size?:number}) {
  return <img className="agent-mark" src={marks[((agent.ordinal||1)-1)%marks.length]} width={size} height={size} alt="" draggable={false}/>;
}
export function AgentStatus({status}:{status:string}) {
  const labels:Record<string,string>={preparing:'准备中',queued:'排队中',running:'正在工作',idle:'已返回',error:'出错',timeout:'已超时',interrupted:'已停止',blocked:'需要处理',limit:'达到上限'};
  const active=['preparing','queued','running'].includes(status);
  const Icon=active?Circle:status==='idle'?CheckCircle:status==='interrupted'?PauseCircle:WarningCircle;
  return <span className={'agent-status status-'+status}><Icon size={12} weight={active?'fill':'regular'}/>{labels[status]||status||'状态未知'}</span>;
}
export function AgentCards({agents,onOpen}:{agents:ChildAgent[];onOpen:(agent:ChildAgent)=>void}) {
  return <div className="agent-cards">{agents.map(agent=><button key={agent.id} className="agent-card" title={`${agent.title} · ${agent.model||agent.model_profile||'沿用主模型'}\n点击查看子任务内容`} aria-label={`查看 ${agentName(agent)}：${agent.title}`} onClick={()=>onOpen(agent)}>
    <AgentMark agent={agent}/><span className="agent-task">{agent.title||agentName(agent)}</span><AgentStatus status={agent.status}/><CaretRight className="agent-card-arrow" size={12}/>
  </button>)}</div>;
}

export function agentsForCall(entry:any,agents:ChildAgent[]) {
  const direct=agents.filter(agent=>agent.parent_call_id===entry.call.id&&agent.parent_message_index===entry.source.message_index);
  if(direct.length)return direct;
  // Older sessions have child IDs in the completed tool result, without origin metadata.
  try {
    const data=JSON.parse(entry.result?.content||'null');
    const ids=(Array.isArray(data)?data:[data]).map(row=>row?.session);
    return agents.filter(agent=>ids.includes(agent.id));
  } catch {return [];}
}
