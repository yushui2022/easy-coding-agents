import React,{memo,useEffect,useState} from 'react';
import {Minus, Square, Copy, X} from '@phosphor-icons/react';

// The window is frameless, so this bar replaces the native title bar. The bar is
// draggable; the three buttons talk to the desktop process and never touch files.
export const TitleBar=memo(function TitleBar({title}:{title:string}) {
  const [maximized,setMaximized]=useState(false);
  useEffect(()=>{
    if(typeof window.eca?.onMaximized!=='function')return;
    const off=window.eca.onMaximized(setMaximized);
    return()=>{if(typeof off==='function')off();};
  },[]);
  const act=(action:string)=>{void window.eca?.windowControl?.(action);};
  return <header className="titlebar" aria-label="窗口标题栏">
    <span className="titlebar-brand"><span className="titlebar-mark" aria-hidden="true"/><span>{title}</span></span>
    <div className="titlebar-drag" onDoubleClick={()=>act('maximize')}/>
    <div className="titlebar-controls">
      <button type="button" aria-label="最小化" title="最小化" onClick={()=>act('minimize')}><Minus size={13}/></button>
      <button type="button" aria-label={maximized?'还原':'最大化'} title={maximized?'还原':'最大化'} onClick={()=>act('maximize')}>
        {maximized?<Copy size={11}/>:<Square size={11}/>}
      </button>
      <button type="button" className="titlebar-close" aria-label="关闭窗口" title="关闭窗口" onClick={()=>act('close')}><X size={13}/></button>
    </div>
  </header>;
});
