import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Check,MagnifyingGlass} from '@phosphor-icons/react';
import './model-menu.css';

export const effortLabels:Record<string,string>={default:'默认',none:'关闭',minimal:'极低',low:'低',medium:'中',high:'高',xhigh:'极高',max:'最高'};
type Reasoning={value:string;options:string[];note?:string};
type Connection={id:string;name:string;model:string;api_format:string;base_url:string;credential_configured:boolean};
type Props={
  anchor:React.RefObject<HTMLButtonElement|null>;label:string;connections:Connection[];recent:string[];
  selectedId?:string|null;reasoning?:Reasoning;busy:boolean;error?:string;
  onChoose:(id:string)=>Promise<unknown>;onEffort:(value:string)=>Promise<unknown>;onClose:()=>void;
  onManage?:()=>void;align?:'start'|'end';special?:{id:string;label:string;selected?:boolean;disabled?:boolean}[];
};
function provider(c:Connection) {
  const model=c.model.toLowerCase();
  if(model.startsWith('deepseek'))return 'DeepSeek';
  if(/^(gpt-|o[134](?:-|$))/.test(model))return 'OpenAI';
  if(model.startsWith('claude-'))return 'Anthropic';
  if(c.base_url.includes('localhost')||c.base_url.includes('127.0.0.1'))return '本地';
  return c.name;
}
export function ModelMenu({anchor,label,connections,recent,selectedId,reasoning,busy,error,onChoose,onEffort,onClose,onManage,align='end',special=[]}:Props) {
  const [query,setQuery]=useState(''),[preview,setPreview]=useState(reasoning?.value||'default');
  const panel=useRef<HTMLDivElement>(null),search=useRef<HTMLInputElement>(null);
  const applying=useRef(false);
  const [position,setPosition]=useState<React.CSSProperties>({});
  const options=reasoning?.options||['default'];
  useEffect(()=>setPreview(reasoning?.value||'default'),[reasoning?.value,selectedId]);
  useLayoutEffect(()=>{
    const place=()=>{const box=anchor.current?.getBoundingClientRect();if(!box||!panel.current)return;
      const width=Math.min(330,window.innerWidth-24),height=panel.current.offsetHeight;
      const top=box.top-height-10;
      setPosition({width,left:Math.max(12,Math.min(align==='start'?box.left:box.right-width,window.innerWidth-width-12)),top:Math.max(12,top>=12?top:Math.min(box.bottom+10,window.innerHeight-height-12))});
    };
    place();const observer=new ResizeObserver(place);if(panel.current)observer.observe(panel.current);
    window.addEventListener('resize',place);return()=>{observer.disconnect();window.removeEventListener('resize',place);};
  },[anchor]);
  useEffect(()=>{
    search.current?.focus();
    const outside=(e:PointerEvent)=>{if(!panel.current?.contains(e.target as Node)&&!anchor.current?.contains(e.target as Node))onClose();};
    const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();onClose();anchor.current?.focus();}};
    document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape,true);
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape,true);};
  },[]);
  const needle=query.trim().toLowerCase();
  const matches=connections.filter(c=>[c.name,c.model,provider(c)].join(' ').toLowerCase().includes(needle));
  const recentRows=needle?[]:recent.map(id=>matches.find(c=>c.id===id)).filter(Boolean) as Connection[];
  const otherRows=matches.filter(c=>!recentRows.some(r=>r.id===c.id));
  const choose=(id:string)=>{if(!busy)void onChoose(id);};
  const apply=async(value:string)=>{
    if(busy||applying.current||value===reasoning?.value)return;
    applying.current=true;setPreview(value);
    try{if(await onEffort(value)===false)setPreview(reasoning?.value||'default');}
    finally{applying.current=false;}
  };
  const row=(c:Connection)=><button key={c.id} className="model-menu-row" role="option" aria-selected={selectedId===c.id} disabled={busy||!c.credential_configured} title={`${c.name} · ${c.model}${!c.credential_configured?' · 需补充密钥':''}`} onClick={()=>choose(c.id)}>
    <span className="model-menu-name">{c.model}<small>{c.name!==c.model?c.name:''}{!c.credential_configured?' · 需配置':''}</small></span><span className="model-menu-provider">{provider(c)}</span><span className="model-menu-check">{selectedId===c.id&&<Check size={15}/>}</span>
  </button>;
  return createPortal(<div ref={panel} className="model-menu" style={position} role="dialog" aria-label={label} aria-busy={busy} onBlur={e=>{
    if(e.relatedTarget&&!e.currentTarget.contains(e.relatedTarget as Node)&&e.relatedTarget!==anchor.current)onClose();
  }} onKeyDown={e=>{
    if(e.target instanceof HTMLInputElement&&e.target.type==='range')return;
    if(!['ArrowDown','ArrowUp','Home','End'].includes(e.key)||e.target===search.current&&!['ArrowDown','ArrowUp'].includes(e.key))return;
    const rows=[...panel.current!.querySelectorAll<HTMLButtonElement>('[role="option"]:not(:disabled)')];if(!rows.length)return;
    e.preventDefault();const index=rows.indexOf(document.activeElement as HTMLButtonElement);
    rows[e.key==='Home'?0:e.key==='End'?rows.length-1:(index+(e.key==='ArrowDown'?1:-1)+rows.length)%rows.length]?.focus();
  }}>
    <div className="model-menu-search"><MagnifyingGlass size={16}/><input ref={search} aria-label="搜索模型" placeholder="搜索模型或连接" value={query} onChange={e=>setQuery(e.target.value)}/></div>
    <div className="model-menu-list" role="listbox" aria-label="模型连接">
      {[...recentRows,...otherRows].map(row)}
      {!matches.length&&<p className="model-menu-empty">{connections.length?'没有匹配的模型':'还没有模型连接'}</p>}
    </div>
    <div className="model-menu-effort">
      <span className="model-effort-label">推理强度<strong>{effortLabels[preview]||preview}</strong></span>
      {options.length>1?<><input aria-label="推理强度" aria-valuetext={effortLabels[preview]||preview} type="range" style={{'--effort-fill':`${100*Math.max(0,options.indexOf(preview))/(options.length-1)}%`} as React.CSSProperties} min={0} max={options.length-1} step={1} value={Math.max(0,options.indexOf(preview))} disabled={busy} onChange={e=>setPreview(options[Number(e.target.value)])} onPointerUp={e=>void apply(options[Number(e.currentTarget.value)])} onKeyUp={e=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'].includes(e.key))void apply(options[Number(e.currentTarget.value)]);}} onBlur={()=>void apply(preview)}/>
        <div className="model-effort-stops">{options.map(value=><button key={value} disabled={busy} aria-label={'推理强度：'+effortLabels[value]} aria-pressed={preview===value} onClick={()=>apply(value)}>{effortLabels[value]}</button>)}</div></>:null}
      <p>{busy?'当前正在处理，请稍候。':reasoning?.note||'默认跟随服务；较高强度通常需要更长时间。'}</p>
    </div>
    {error&&<p className="model-menu-error" role="alert">{error}</p>}
  </div>,document.querySelector('.eca-app')!);
}
