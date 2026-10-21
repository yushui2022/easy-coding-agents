import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {CaretDown, ChatCircleDots, Check, Code, ListChecks} from '@phosphor-icons/react';
import './permission-menu.css';
import './mode-menu.css';

// A workflow choice, not a permission: the approval chip still decides what may run.
export const modeLabels:Record<string,string>={code:'编码',plan:'计划',chat:'对话'};
const descriptions:Record<string,string>={
  code:'可以修改文件、运行命令和测试',
  plan:'只读调研，先给计划，不改任何文件',
  chat:'不使用工具，只按上下文回答',
};
const titleFor=(busy?:boolean)=>busy?'任务运行中不能切换工作模式':'工作模式';
const order=['code','plan','chat'];
const marks:Record<string,React.ReactNode>={
  code:<Code size={15}/>,plan:<ListChecks size={15}/>,chat:<ChatCircleDots size={15}/>,
};

export function ModeControl({mode,busy,onChange}:{mode:string;busy?:boolean;onChange:(mode:string)=>void}) {
  const [open,setOpen]=useState(false);
  const chip=useRef<HTMLButtonElement>(null),panel=useRef<HTMLDivElement>(null);
  const [position,setPosition]=useState<React.CSSProperties>({});
  const current=modeLabels[mode]?mode:'code';
  useLayoutEffect(()=>{
    if(!open)return;
    const place=()=>{
      const box=chip.current?.getBoundingClientRect();if(!box||!panel.current)return;
      const width=240,height=panel.current.offsetHeight;
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
    <button ref={chip} type="button" className={'permission-chip mode-chip'+(current==='plan'?' is-plan':'')}
      aria-haspopup="dialog" aria-expanded={open} aria-label={'工作模式：'+modeLabels[current]}
      title={titleFor(busy)}
      disabled={busy} onClick={()=>setOpen(value=>!value)}>
      {marks[current]}<span>{modeLabels[current]}</span><CaretDown size={11} className="permission-caret"/>
    </button>
    {open&&createPortal(<div ref={panel} className="permission-menu" style={position} role="dialog" aria-label="工作模式">
      <div className="permission-menu-head">工作模式<small>只影响当前会话</small></div>
      {order.map(value=><button key={value} type="button" role="menuitemradio" aria-checked={value===current}
          className={'permission-row'+(value===current?' is-current':'')}
          onClick={choose(value)}>
        <span className="mode-mark">{marks[value]}</span>
        <span className="permission-row-text"><strong>{modeLabels[value]}</strong><small>{descriptions[value]}</small></span>
        <span className="permission-row-check">{value===current&&<Check size={14}/>}</span>
      </button>)}
    </div>,document.querySelector('.eca-app')||document.body)}
  </>;
}
