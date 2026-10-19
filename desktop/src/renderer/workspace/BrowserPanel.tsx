import React,{useEffect,useRef,useState} from 'react';
import {Globe,ArrowLeft,ArrowRight,ArrowClockwise} from '@phosphor-icons/react';
import {EmptyState} from '../ui/EmptyState';
export function BrowserPanel({id,owner,active,blocked,onDraft}:any) {
  const [url,setUrl]=useState(''),[state,setState]=useState<any>({}),[error,setError]=useState('');const area=useRef<HTMLDivElement>(null),dirty=useRef(false);
  const call=(method:string,p:any={})=>window.eca.invoke(method,{owner,id,...p});
  useEffect(()=>{if(!active)return;let disposed=false,inflight=false;
    const poll=async()=>{if(inflight)return;inflight=true;try{const rows=await call('browser.list');const t=rows.find((r:any)=>r.id===id);if(!disposed&&t){setState(t);if(!dirty.current)setUrl(t.url);}}catch(e){if(!disposed)setError(String(e));}finally{inflight=false;}};
    void poll();const timer=setInterval(poll,500);return()=>{disposed=true;clearInterval(timer);};
  },[active,id,owner]);
  useEffect(()=>{
    if(!active||blocked||!state.url){void call('browser.hide').catch(()=>{});return;}
    const position=()=>{const b=area.current?.getBoundingClientRect();if(!b)return;const bounds={x:b.x,y:b.y,width:b.width,height:b.height};void call('browser.bounds',{bounds}).catch(e=>setError(String(e)));};
    position();const timer=setInterval(position,100);return()=>{clearInterval(timer);void call('browser.hide').catch(()=>{});};
  },[active,blocked,id,owner,state.url]);
  const act=async(method:string,p:any={})=>{try{setError('');return await call(method,p);}catch(e){setError(String(e));return null;}};
  return <section className="browser-panel"><form className="browser-toolbar" onSubmit={e=>{e.preventDefault();dirty.current=false;void act('browser.navigate',{url});}}>
    <button type="button" aria-label="后退" title="后退" disabled={!state.back} onClick={()=>act('browser.back')}><ArrowLeft size={16}/></button><button type="button" aria-label="前进" title="前进" disabled={!state.forward} onClick={()=>act('browser.forward')}><ArrowRight size={16}/></button><button type="button" aria-label="刷新页面" title="刷新页面" onClick={()=>act('browser.reload')}><ArrowClockwise size={16}/></button>
    <input aria-label="浏览器地址" placeholder="网址或 localhost:3000" value={url} onChange={e=>{dirty.current=true;setUrl(e.target.value);}}/><button type="submit">前往</button></form>
    <div className="browser-actions"><button onClick={async()=>{const v=await act('browser.pick');if(v){setUrl(v.url);dirty.current=false;await act('browser.navigate',v);}}}>预览项目 HTML</button><button onClick={async()=>{const v=await act('browser.quote');if(v)onDraft(`网页引用 · ${v.url}\n${v.text}`);}}>引用页面文字</button><span>{state.loading?'加载中':state.title||'网页预览'}</span></div>
    {(error||state.error)&&<p role="alert" className="workspace-error">{error||state.error}</p>}
    <div className="browser-viewport" ref={area}>{!state.url&&<EmptyState icon={<Globe size={25} weight="light"/>} title="查看你的项目">输入开发服务器地址，或选择项目内的 HTML。</EmptyState>}</div>
  </section>;
}
