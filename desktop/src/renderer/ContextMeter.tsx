import React,{memo,useEffect,useRef,useState} from 'react';

// A local estimate of how full the context budget is. It is not a billing count:
// the percentage comes from eca.context.ContextBudget on the Python side.
export const ContextMeter=memo(function ContextMeter({context,busy,onCompact}:{context:any;busy?:boolean;onCompact?:()=>Promise<void>}) {
  const [open,setOpen]=useState(false),[working,setWorking]=useState(false),[error,setError]=useState('');
  const root=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    if(!open)return;
    const outside=(event:PointerEvent)=>{if(!root.current?.contains(event.target as Node))setOpen(false);};
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();setOpen(false);root.current?.querySelector('button')?.focus();}};
    document.addEventListener('pointerdown',outside);
    document.addEventListener('keydown',escape,true);
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape,true);};
  },[open]);
  if(!context)return null;
  const ratio=Number(context.ratio);
  if(!Number.isFinite(ratio)||ratio<0)return null;
  const percent=Math.max(0,Math.min(100,Math.round(ratio*100)));
  const level=ratio>=0.95?'danger':ratio>=0.85?'warn':'ok';
  const radius=6.5,circumference=2*Math.PI*radius,used=Math.min(1,ratio);
  const tokens=Number(context.estimated_tokens)||0;
  const limit=Number(context.input_limit)||0;
  const partNames:Record<string,string>={system:'系统提示',tools:'工具定义',user:'你说的话',assistant:'模型回答',tool:'工具结果',summary:'历史摘要',progress:'进度索引'};
  const parts:any[]=Array.isArray(context.parts)?[...context.parts].sort((a,b)=>Number(b.tokens)-Number(a.tokens)):[];
  const compact=async()=>{
    if(!onCompact||working)return;
    setWorking(true);setError('');
    try {await onCompact();setOpen(false);}
    catch(e){setError(String(e));}
    finally {setWorking(false);}
  };
  const blocked=busy||!onCompact;
  const title=`上下文约 ${tokens.toLocaleString()} / ${limit.toLocaleString()} tokens（本地估算，不是计费）`
    +(context.auto_compact?'；接近上限时自动压缩':'')
    +(level==='danger'?'；已接近预算，建议压缩或新建会话':'');
  return <div className="context-meter-wrap" ref={root}>
    <button type="button" className={'context-meter '+level} onClick={()=>setOpen(value=>!value)}
      aria-haspopup="dialog" aria-expanded={open} aria-label={`上下文占用 ${percent}%`} title={title}>
      <svg viewBox="0 0 16 16" width={14} height={14} aria-hidden="true">
        <circle className="track" cx={8} cy={8} r={radius}/>
        <circle className="arc" cx={8} cy={8} r={radius} transform="rotate(-90 8 8)"
          strokeDasharray={circumference} strokeDashoffset={circumference*(1-used)}/>
      </svg>
      <span>{percent}%</span>
    </button>
    {open&&<div className="context-menu" role="dialog" aria-label="上下文设置">
      <p className="context-menu-title">上下文约 {tokens.toLocaleString()} / {limit.toLocaleString()} tokens</p>
      {parts.length>0&&<div className="context-parts">
        {parts.map(part=><div className="context-part" key={part.id}>
          <span className="context-part-label">{partNames[part.id]||part.id}</span>
          <span className="context-part-bar"><i style={{width:`${Math.max(2,Math.round(100*part.tokens/(tokens||1)))}%`}}/></span>
          <span className="context-part-value">{Math.round(100*part.tokens/(tokens||1))}%</span>
        </div>)}
      </div>}
      <p className="fine-print">本地估算，不是计费；{context.auto_compact?'接近上限会自动压缩':'自动压缩已关闭'}。</p>
      <button type="button" className="context-compact" disabled={blocked||working} onClick={compact}>
        {working?'正在压缩…':busy?'任务运行中，稍后可压缩':'压缩上下文'}
      </button>
      <p className="fine-print">压缩由模型生成摘要，原始历史仍保存在磁盘，不会删除会话记录。</p>
      {error&&<p role="alert" className="context-error">{error}</p>}
    </div>}
  </div>;
});
