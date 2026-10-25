import React,{useEffect,useRef,useState} from 'react';
import './selection-toolbar.css';

type Spot={text:string;top:number;left:number};

const MAX_CHARS=4000;
const WIDTH=250;
const HEIGHT=38;

// Selecting text in the transcript raises a small toolbar anchored to the
// selection. It follows scrolling (the selection rect moves), disappears on a
// collapsed selection or a click elsewhere, and never steals the selection before
// the click lands: the text is captured when the pill opens.
export function SelectionToolbar({scope,disabled,onAdd,onAsk}:{scope:string;disabled?:boolean;
  onAdd:(text:string)=>void;onAsk:(text:string)=>void}) {
  const [spot,setSpot]=useState<Spot|null>(null);
  const box=useRef<HTMLDivElement|null>(null);
  const frame=useRef<number|null>(null);
  // True while the pointer or focus is inside the pill, so the selection clearing
  // underneath does not unmount it before the button's click fires.
  const holding=useRef(false);

  useEffect(()=>{
    const measure=()=>{
      frame.current=null;
      if(holding.current)return;
      const selection=window.getSelection();
      if(!selection||selection.rangeCount===0||selection.isCollapsed){setSpot(null);return;}
      const range=selection.getRangeAt(0);
      const host=range.commonAncestorContainer;
      const element=host.nodeType===1?(host as Element):host.parentElement;
      if(!element||!element.closest(scope)){setSpot(null);return;}
      const text=range.toString().replace(/\s+/g,' ').trim();
      if(!text||text.length<2){setSpot(null);return;}
      const rect=range.getBoundingClientRect();
      if(!rect.width&&!rect.height){setSpot(null);return;}
      const left=Math.max(8,Math.min(rect.left+rect.width/2-WIDTH/2,window.innerWidth-WIDTH-8));
      const above=rect.top-HEIGHT-8;
      const top=above>=8?above:Math.min(rect.bottom+8,window.innerHeight-HEIGHT-8);
      setSpot({text:text.slice(0,MAX_CHARS),top,left});
    };
    const schedule=()=>{if(frame.current!==null)return;frame.current=requestAnimationFrame(measure);};
    const onPointerDown=(event:PointerEvent)=>{
      const target=event.target as Node|null;
      if(target&&box.current?.contains(target)){holding.current=true;return;}
      holding.current=false;
      setSpot(null);
    };
    const onPointerUp=(event:PointerEvent)=>{
      const target=event.target as Node|null;
      if(!(target&&box.current?.contains(target)))holding.current=false;
      schedule();
    };
    const onKey=(event:KeyboardEvent)=>{if(event.key==='Escape'){holding.current=false;setSpot(null);}else schedule();};
    document.addEventListener('selectionchange',schedule);
    window.addEventListener('pointerdown',onPointerDown,true);
    window.addEventListener('pointerup',onPointerUp,true);
    window.addEventListener('keyup',onKey);
    window.addEventListener('resize',()=>setSpot(null));
    window.addEventListener('scroll',schedule,true);
    return ()=>{
      if(frame.current!==null)cancelAnimationFrame(frame.current);
      document.removeEventListener('selectionchange',schedule);
      window.removeEventListener('pointerdown',onPointerDown,true);
      window.removeEventListener('pointerup',onPointerUp,true);
      window.removeEventListener('keyup',onKey);
      window.removeEventListener('scroll',schedule,true);
    };
  },[scope]);

  useEffect(()=>{if(disabled)setSpot(null);},[disabled]);

  if(!spot)return null;
  const act=(handler:(text:string)=>void)=>{
    const text=spot.text;
    holding.current=false;
    setSpot(null);
    window.getSelection()?.removeAllRanges();
    handler(text);
  };
  return <div className="selection-toolbar" ref={box} role="toolbar" aria-label="选中文字的可用操作"
    style={{top:spot.top,left:spot.left,width:WIDTH}} onFocus={()=>{holding.current=true;}}>
    <button type="button" onClick={()=>act(onAdd)}>添加到对话</button>
    <span className="selection-separator" aria-hidden="true"/>
    <button type="button" onClick={()=>act(onAsk)}>在侧边聊天中提问</button>
  </div>;
}
