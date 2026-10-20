import React,{useEffect,useRef,useState} from 'react';
import {Plus,FileText,X} from '@phosphor-icons/react';
import './attachments.css';
type Attachment={name:string;mime:string;size:number;data:string};
const imageTypes:Record<string,string>={png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp'};
const textTypes=new Set('txt md mdx csv tsv json jsonl yaml yml toml xml html css scss js jsx ts tsx py rs go java c h cpp hpp cs sql sh ps1 bat ini cfg log gitignore dockerfile'.split(' '));
const db=new Promise<IDBDatabase>((resolve,reject)=>{
  const req=indexedDB.open('eca-attachment-drafts',1);
  req.onupgradeneeded=()=>req.result.createObjectStore('drafts');
  req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);
});
async function stored(key:string,value?:Attachment[]){
  const database=await db;
  return new Promise<Attachment[]>((resolve,reject)=>{
    const tx=database.transaction('drafts',value?'readwrite':'readonly'),store=tx.objectStore('drafts');
    const req=value?store.put(value,key):store.get(key);
    tx.oncomplete=()=>resolve(value||req.result||[]);tx.onerror=()=>reject(tx.error);
  });
}
export function useAttachments(scope:string,disabled=false){
  const [state,setState]=useState<{scope:string;items:Attachment[]}>({scope,items:[]});
  const [error,setError]=useState(''),[loading,setLoading]=useState(true),[reading,setReading]=useState(false);
  const input=useRef<HTMLInputElement>(null),current=useRef(scope),lock=useRef(false);
  current.current=scope;
  const items=state.scope===scope?state.items:[];
  useEffect(()=>{let disposed=false;setLoading(true);setError('');void stored(scope).then(items=>{if(!disposed)setState({scope,items});}).catch(()=>{if(!disposed)setError('附件草稿读取失败，请重新添加。');}).finally(()=>{if(!disposed)setLoading(false);});return()=>{disposed=true;};},[scope]);
  const save=async(next:Attachment[],key=scope)=>{await stored(key,next);if(current.current===key)setState({scope:key,items:next});};
  const add=async(files:File[])=>{
    if(disabled||loading||lock.current||!files.length)return;
    lock.current=true;setReading(true);setError('');
    try{
      if(items.length+files.length>6)throw Error('每次最多添加 6 个附件。');
      const batch:Attachment[]=[];
      for(const file of files){
        const ext=file.name.split('.').pop()!.toLowerCase();
        const mime=imageTypes[ext]||(file.type.startsWith('image/')?file.type:'text/plain');
        if(!Object.values(imageTypes).includes(mime)&&!(textTypes.has(ext)||file.type.startsWith('text/')))throw Error(`${file.name}：暂不支持此格式，请使用图片、代码或文本文件。`);
        if(file.size>(mime==='text/plain'?256*1024:4*1024*1024))throw Error(`${file.name} 太大：图片最大 4 MB，文本最大 256 KB。`);
        const bytes=await file.arrayBuffer();
        if(mime==='text/plain'){const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);if(text.includes('\0'))throw Error(`${file.name} 不是文本文件。`);}
        const data=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('无法读取附件'));reader.readAsDataURL(file);});
        batch.push({name:file.name,mime,size:file.size,data});
      }
      const next=[...items,...batch];
      if(next.reduce((n,a)=>n+a.size,0)>12*1024*1024)throw Error('附件总大小不能超过 12 MB。');
      await save(next);
    }catch(e){if(current.current===scope)setError(String(e));}
    finally{lock.current=false;setReading(false);}
  };
  const busy=disabled||loading||reading;
  return {items,busy,clear:()=>save([]),moveTo:async(key:string)=>{await save(items,key);await stored(scope,[]);},
    events:{
      onDragOver:(e:React.DragEvent)=>{if(e.dataTransfer.types.includes('Files'))e.preventDefault();},
      onDrop:(e:React.DragEvent)=>{if(e.dataTransfer.files.length){e.preventDefault();void add(Array.from(e.dataTransfer.files));}},
      onPaste:(e:React.ClipboardEvent)=>{if(e.clipboardData.files.length){e.preventDefault();void add(Array.from(e.clipboardData.files));}}
    },
    button:<><input hidden ref={input} type="file" multiple aria-label="选择附件" onChange={e=>{void add(Array.from(e.target.files||[]));e.target.value='';}}/><button className="attach-button" aria-label="添加文件或图片" title="添加文件或图片，也可以拖入或粘贴截图" disabled={busy} onClick={()=>input.current?.click()}><Plus size={18}/></button></>,
    preview:<>{!!items.length&&<div className="attachment-tray">{items.map((a,i)=><div className="attachment-chip" key={i}>{a.mime.startsWith('image/')?<img src={`data:${a.mime};base64,${a.data}`} alt={a.name}/>:<FileText size={22}/>}<span title={a.name}>{a.name}<small>{Math.max(1,Math.ceil(a.size/1024))} KB</small></span><button disabled={busy} aria-label={'移除 '+a.name} onClick={()=>void save(items.filter((_,j)=>i!==j)).catch(e=>setError(String(e)))}><X size={13}/></button></div>)}</div>}
      {items.some(a=>a.mime.startsWith('image/'))&&<small className="attachment-hint">图片将发送给当前模型，请选择支持看图的模型。</small>}
      {reading&&<small className="attachment-hint" role="status">正在读取附件…</small>}
      {error&&<p className="attachment-error" role="alert">{error}</p>}</>
  };
}
export function AttachmentNames({items=[]}:{items?:any[]}){
  return items.length?<div className="sent-attachments">{items.map((a,i)=><span key={i}><FileText size={14}/>{a.name}<small>{Math.max(1,Math.ceil(a.size/1024))} KB</small></span>)}</div>:null;
}
