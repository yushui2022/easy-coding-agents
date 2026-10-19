import React, {useEffect, useRef} from 'react';
import {CaretDown, TestTube} from '@phosphor-icons/react';

type Props = {open:boolean; onOpenChange:(open:boolean)=>void; checks:string; attempts:number; busy:boolean; codeMode:boolean; onChange:(checks:string,attempts:number)=>void};

export function TaskVerification({open,onOpenChange,checks,attempts,busy,codeMode,onChange}:Props) {
  const root=useRef<HTMLDetailsElement>(null);
  const count=checks.split('\n').filter(command=>command.trim()).length;
  useEffect(()=>{
    if(!open)return;
    const outside=(event:PointerEvent)=>{if(!root.current?.contains(event.target as Node))onOpenChange(false);};
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();onOpenChange(false);root.current?.querySelector('summary')?.focus();}};
    document.addEventListener('pointerdown',outside);
    document.addEventListener('keydown',escape,true);
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape,true);};
  },[open,onOpenChange]);
  return <details ref={root} className="checks" open={open} onToggle={e=>onOpenChange(e.currentTarget.open)}>
    <summary aria-label="验证与自动修复" title="配置任务完成后的检查与修复" onClick={e=>{if(busy)e.preventDefault();}}><TestTube size={16}/><span>验证</span>{count>0&&<span className="check-count">{count}</span>}<CaretDown size={11} className="checks-caret"/></summary>
    <div className="check-settings">
      <div className="check-settings-heading"><label htmlFor="verification-commands">完成任务后运行</label><span>每行一条命令</span></div>
      <textarea id="verification-commands" aria-label="验证命令" placeholder={'npm test\nnpm run build'} value={checks} onChange={e=>onChange(e.target.value,attempts)} disabled={busy}/>
      <label className="repair-option">检查失败时<select aria-label="自动修复次数" value={attempts} disabled={busy||!checks.trim()||!codeMode} onChange={e=>onChange(checks,Number(e.target.value))}><option value={0}>停止，保留结果</option>{[1,2,3].map(count=><option key={count} value={count}>最多自动修复 {count} 次</option>)}</select></label>
      <p className="fine-print">修复后重跑全部检查。授权被拒绝、超时或取消时停止。</p>
    </div>
  </details>;
}
