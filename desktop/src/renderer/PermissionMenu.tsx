import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Check, CaretDown, ShieldCheck} from '@phosphor-icons/react';
import './permission-menu.css';

export const permissionLabels:Record<string,string>={ask:'逐次确认','accept-edits':'自动编辑','full-access':'完全访问'};
const descriptions:Record<string,string>={
  ask:'文件修改、命令和联网都先问你',
  'accept-edits':'文件修改自动批准，命令仍需确认',
  'full-access':'本会话内全部自动批准，含命令与联网',
};
const order=['ask','accept-edits','full-access'];

export function PermissionControl({mode,busy,onChange}:{mode:string;busy?:boolean;onChange:(mode:string)=>void}) {
  const [open,setOpen]=useState(false);
  const chip=useRef<HTMLButtonElement>(null),panel=useRef<HTMLDivElement>(null);
  const [position,setPosition]=useState<React.CSSProperties>({});
  const current=permissionLabels[mode]?mode:'ask';
  useLayoutEffect(()=>{
    if(!open)return;
    const place=()=>{
      const box=chip.current?.getBoundingClientRect();if(!box||!panel.current)return;
      const width=232,height=panel.current.offsetHeight;
      setPosition({width,left:Math.max(12,Math.min(box.left,window.innerWidth-width-12)),
        top:box.top-height-8>12?box.top-height-8:Math.min(box.bottom+8,window.innerHeight-height-12)});
    };
    place();
    window.addEventListener('resize',place);
    return()=>window.removeEventListener('resize',place);
  },[open]);
  useEffect(()=>{
    if(!open)return;
    const outside=(event:PointerEvent)=>{
      if(!panel.current?.contains(event.target as Node)&&!chip.current?.contains(event.target as Node))setOpen(false);
    };
    const escape=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){event.preventDefault();event.stopPropagation();setOpen(false);chip.current?.focus();}
    };
    document.addEventListener('pointerdown',outside);
    document.addEventListener('keydown',escape,true);
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape,true);};
  },[open]);
  const choose=(value:string)=>()=>{
    setOpen(false);chip.current?.focus();
    if(value!==current)onChange(value);
  };
  return <>
    <button ref={chip} type="button" className={'permission-chip'+(current==='full-access'?' is-full':'')}
      aria-haspopup="dialog" aria-expanded={open} aria-label={'审批模式：'+permissionLabels[current]}
      title="审批模式" disabled={busy} onClick={()=>setOpen(value=>!value)}>
      <ShieldCheck size={14}/><span>{permissionLabels[current]}</span><CaretDown size={11} className="permission-caret"/>
    </button>
    {open&&createPortal(<div ref={panel} className="permission-menu" style={position} role="dialog" aria-label="审批模式">
      <div className="permission-menu-head">审批模式<small>只影响当前会话</small></div>
      {order.map(value=><button key={value} type="button" role="menuitemradio" aria-checked={value===current}
          className={'permission-row'+(value===current?' is-current':'')+(value==='full-access'?' is-full':'')}
          onClick={choose(value)}>
        <span className="permission-row-text"><strong>{permissionLabels[value]}</strong><small>{descriptions[value]}</small></span>
        <span className="permission-row-check">{value===current&&<Check size={14}/>}</span>
      </button>)}
    </div>,document.querySelector('.eca-app')||document.body)}
  </>;
}
