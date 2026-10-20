import React,{memo} from 'react';

// A local estimate of how full the context budget is. It is not a billing count:
// the percentage comes from eca.context.ContextBudget on the Python side.
export const ContextMeter=memo(function ContextMeter({context}:{context:any}) {
  if(!context)return null;
  const ratio=Number(context.ratio);
  if(!Number.isFinite(ratio)||ratio<0)return null;
  const percent=Math.max(0,Math.min(100,Math.round(ratio*100)));
  const level=ratio>=0.95?'danger':ratio>=0.85?'warn':'ok';
  const radius=6.5,circumference=2*Math.PI*radius,used=Math.min(1,ratio);
  const tokens=Number(context.estimated_tokens)||0;
  const limit=Number(context.input_limit)||0;
  const title=`上下文约 ${tokens.toLocaleString()} / ${limit.toLocaleString()} tokens（本地估算，不是计费）`
    +(context.auto_compact?'；接近上限时自动压缩':'')
    +(level==='danger'?'；已接近预算，建议压缩或新建会话':'');
  return <div className={'context-meter '+level} role="img" aria-label={`上下文占用 ${percent}%`} title={title}>
    <svg viewBox="0 0 16 16" width={14} height={14} aria-hidden="true">
      <circle className="track" cx={8} cy={8} r={radius}/>
      <circle className="arc" cx={8} cy={8} r={radius} transform="rotate(-90 8 8)"
        strokeDasharray={circumference} strokeDashoffset={circumference*(1-used)}/>
    </svg>
    <span>{percent}%</span>
  </div>;
});
