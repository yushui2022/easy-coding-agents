import React,{memo,useEffect,useState} from 'react';
import {Minus, Square, Copy, X} from '@phosphor-icons/react';

// The window is frameless, so this bar replaces the native title bar. It carries
// nothing but the drag region and the three window buttons: the app name and logo
// already sit in the sidebar brand directly below, and repeating them up here made
// the top of the window read as a second, competing header.
export const TitleBar=memo(function TitleBar({title}:{title:string}) {
  const [maximized,setMaximized]=useState(false);
  useEffect(()=>{
    if(typeof window.eca?.onMaximized!=='function')return;
    const off=window.eca.onMaximized(setMaximized);
    return()=>{if(typeof off==='function')off();};
  },[]);
  const act=(action:string)=>{void window.eca?.windowControl?.(action);};
  return <header className="titlebar" aria-label={title+' 窗口标题栏'}>
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
