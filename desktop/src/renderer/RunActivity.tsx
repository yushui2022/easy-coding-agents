import React,{useEffect,useId,useState} from 'react';
import {CaretDown} from '@phosphor-icons/react';
import workMark from './assets/activity/clay-work-loop.png';
import './run-activity.css';

const actions:Record<string,string>={
  grep:'正在搜索代码',search:'正在搜索代码',code_search:'正在搜索代码',
  glob:'正在定位文件',read:'正在读取文件',write:'正在写入文件',
  edit:'正在修改文件',edit_many:'正在修改文件',apply_patch:'正在应用修改',delete:'正在删除文件',
  shell:'正在运行命令',repo_map:'正在梳理项目',code_relations:'正在查找代码关联',
  web_fetch:'正在读取网页',web_search:'正在搜索资料',todo:'正在更新计划',
  process_start:'正在启动后台命令',process_wait:'正在等待命令输出',process_logs:'正在读取命令输出',
  process_stop:'正在停止命令',lsp:'正在查询代码符号',lsp_rename:'正在预览重命名',lsp_apply:'正在应用重命名',
};
const phases:Record<string,string>={
  preparing:'正在准备任务',waiting_model:'等待模型响应',thinking:'正在思考',
  responding:'正在生成回答',tool_arguments:'正在准备工具调用',executing:'正在执行操作',
  verifying:'正在运行验证',repairing:'正在修复问题',approval:'等待你的授权',question:'等待你的回答',
  tool_done:'工具已返回',
};
const count=(value:unknown)=>Math.max(0,Number(value)||0).toLocaleString();

export function RunActivity({state,stopping=false}:{state:any;stopping?:boolean}) {
  const [now,setNow]=useState(Date.now()),[expanded,setExpanded]=useState(false);
  const detailsId=useId(),activity=state.activity||{},phase=activity.phase||'preparing';
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);
  const elapsed=Math.max(0,Math.floor(now/1000-(state.started_at||now/1000)));
const formatClock=(seconds:number)=>seconds>=60?`${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`:`${seconds}s`;
  const phaseElapsed=Math.max(0,Math.floor(now/1000-(activity.since||now/1000)));
  const time=`${Math.floor(elapsed/60)}:${String(elapsed%60).padStart(2,'0')}`;
  const activeChildren=(state.children||[]).filter((child:any)=>['preparing','queued','running'].includes(child.status)).length;
  const delegating=['tool_arguments','executing'].includes(phase)&&(['delegate','delegate_parallel'].includes(activity.tool)||phase==='executing'&&activeChildren);
  const title=stopping?'正在停止并清理':delegating?(activeChildren?'子任务执行中':'正在安排子任务'):phase==='executing'
    ?actions[activity.tool]||(activity.tool?.startsWith('mcp')?'正在调用外部工具':phases.executing)
    :phases[phase]||'正在处理任务';
  const detail=stopping?'正在等待当前操作结束并释放资源，已完成的文件修改会保留。'
    :delegating&&activeChildren?`${activeChildren} 个子任务正在运行，点击对话中的子任务查看独立进度。`
    :phase==='tool_arguments'?`已生成 ${count(activity.tool_argument_chars)} 个参数字符，工具尚未执行。`
    :phase==='thinking'?`已接收 ${count(activity.reasoning_chars)} 个思考字符。`
    :phase==='waiting_model'?'请求已发出，正在等待服务返回。你可以随时停止任务。'
    :phase==='verifying'?'验证结果将在检查完成后显示。'
    :phase==='executing'||phase==='tool_done'?activity.target||'返回结果会显示在对话的执行记录中。'
    :phase==='responding'?'正在接收模型输出。'
    :phase==='repairing'?'正在处理验证中发现的问题。'
    :phase==='approval'||phase==='question'?'任务正在等待你的回复。'
    :'任务仍在进行，尚无可显示的结果。';
  const subtitle=phase==='tool_arguments'?`参数生成中 · ${count(activity.tool_argument_chars)} 字符 · 尚未执行`
    :phase==='thinking'?`持续 ${formatClock(phaseElapsed)} · 已接收 ${count(activity.reasoning_chars)} 个思考字符`
    :phase==='responding'?`已接收 ${count(activity.text_chars)} 个回答字符`
    :detail;
  // The phase clock runs locally, so it keeps moving even when the backend has
  // nothing new to report (a long tool call, or a provider that is just slow).
  const clocked=['preparing','waiting_model','thinking','responding','tool_arguments','executing','verifying','repairing'].includes(phase)?`${subtitle} · 持续 ${formatClock(phaseElapsed)}`:subtitle;
  // A stream can stay connected while producing nothing; say so instead of looking frozen.
  const silent=typeof activity.updated_at==='number'?Math.floor(now/1000-activity.updated_at):0;
  const stall=['waiting_model','thinking','responding'].includes(phase)&&silent>=15
    ?`${clocked} · 已 ${silent} 秒没有新数据`:`${clocked}`;
  // Prefer this round's live figure. Fall back to the finished request's average,
  // but say so: a frozen number labelled plainly reads as a broken clock.
  const usable=(value:any)=>typeof value?.tokens_per_second==='number'&&Number.isFinite(value.tokens_per_second)&&value.throughput_source!=='unavailable';
  const liveUsable=usable(activity),lastUsable=usable(state.last_request);
  const metrics=liveUsable?activity:lastUsable?state.last_request:{};
  const available=liveUsable||lastUsable,stale=available&&!liveUsable;
  const speed=available?(metrics.throughput_source==='estimate'?'≈':'')+metrics.tokens_per_second.toFixed(1):'—';
  const speedNote=metrics.throughput_unavailable_reason==='unobserved_reasoning'
    ?'服务端包含不可观测的推理用量，无法可靠计算速度。'
    :available?(metrics.throughput_source==='estimate'?'按流式字符估算本轮平均生成速度，不用于计费。':'按服务端输出 token 与内容流的生成时长计算。')
    :'尚无足够的流式计时数据，暂不计算生成速度。';
  return <section className={'run-activity'+(stopping?' is-stopping':'')} aria-label="任务运行状态">
    <div className="activity-row">
      <img className="activity-mark" src={workMark} alt="" width={32} height={32} draggable={false}/>
      <div className="activity-main">
        <div className="activity-heading"><span className="activity-title" role="status" aria-live="polite" aria-atomic="true">{title}</span>{activity.tool&&<span className="activity-tool-name" title={activity.tool}>{activity.tool}</span>}</div>
        <div className="activity-subtitle" title={stall}>{stall}</div>
      </div>
      <div className="activity-metrics" title={speedNote}>
        <div className={'activity-speed'+(stale?' is-stale':'')}><strong>{speed}</strong><span>tokens/s{stale?' · 上轮':''}</span></div>
        <div className="activity-timing"><time className="activity-time" aria-label={`任务已用时 ${Math.floor(elapsed/60)} 分 ${elapsed%60} 秒`}>{time}</time></div>
      </div>
      <button className="activity-disclosure" aria-label={expanded?'收起运行详情':'展开运行详情'} aria-expanded={expanded} aria-controls={detailsId} onClick={()=>setExpanded(value=>!value)}><CaretDown size={14}/></button>
    </div>
    {expanded&&<div className="activity-detail" id={detailsId}>
      <p>{detail}</p>
      {activity.tool&&<div className="activity-tool"><span>{phase==='tool_arguments'?'待调用工具':'当前工具'}</span><code>{activity.tool}</code></div>}
      <p>{speedNote}</p>
    </div>}
  </section>;
}
