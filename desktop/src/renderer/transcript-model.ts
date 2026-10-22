// Presentation only: never change the stored conversation or replay a tool.
export type Outcome = 'returned' | 'error' | 'denied' | 'stopped' | 'pending' | 'unknown';
export type ToolEntry = {key:string; call:any; source:any; result?:any};
export type TranscriptNode =
  | {kind:'message'; key:string; message:any}
  | {kind:'gap'; key:string; count:number}
  | {kind:'tools'; key:string; entries:ToolEntry[]};

export function transcriptNodes(messages:any[]):TranscriptNode[] {
  const nodes:TranscriptNode[]=[];
  let group:Extract<TranscriptNode,{kind:'tools'}>|undefined;
  const calls=new Map<string,ToolEntry>();
  messages.forEach((message,index)=>{
    const key=String(message.message_index??index);
    const previous=messages[index-1];
    if(previous && message.message_index>previous.message_index+1) {
      nodes.push({kind:'gap',key:'gap-'+key,count:message.message_index-previous.message_index-1});
      group=undefined;calls.clear();
    }
    if(message.role==='tool') {
      const entry=calls.get(message.tool_call_id);
      if(entry && !entry.result)entry.result=message;
      else {group=undefined;nodes.push({kind:'message',key,message});}
      return;
    }
    if(message.role!=='assistant'||(typeof message.content==='string'&&message.content.trim())) {
      group=undefined;
      if(message.role==='user'||message.role==='system')calls.clear();
      if(message.role!=='system')nodes.push({kind:'message',key,message});
    }
    for(const call of message.tool_calls||[]) {
      if(!group) {group={kind:'tools',key:'tools-'+key,entries:[]};nodes.push(group);}
      const entry={key:key+'-'+call.id,call,source:message};
      group.entries.push(entry);calls.set(call.id,entry);
    }
  });
  return nodes;
}

export function resultInfo(result:any,pending=false):{kind:Outcome;label:string;hint:string} {
  if(!result)return pending?{kind:'pending',label:'等待结果',hint:'尚未收到工具结果'}:{kind:'unknown',label:'未记录结果',hint:'可能被中断；继续前需核对实际状态'};
  const text=typeof result.content==='string'?result.content.trim():'';
  let data=result.tool_summary;
  if(!data)try{data=JSON.parse(text);}catch{/* Text is a valid tool result. */}
  const status=String(data?.status||'').toLowerCase();
  if(/^(Denied|Permission denied)\b/i.test(text))return {kind:'denied',label:'已拒绝',hint:text};
  // An interrupted call is not a failure. Say what actually happened instead of
  // echoing the model-facing English sentence in red under the tool name.
  if(/^Interrupted\b/i.test(text)||['cancelled','canceled','interrupted'].includes(status)){
    const safe=/read-only|nothing was changed/i.test(text);
    return {kind:'stopped',label:'已中断',hint:safe?'这一步被中断，没有返回结果。只读操作不改变任何东西，可以直接重试。':'这一步被中断，结果未知。重试前先核对当前文件和进程状态。'};
  }
  if(/^(Stopped|Cancelled|Canceled)\b/i.test(text))return {kind:'stopped',label:'已中断',hint:text};
  if(data?.timed_out)return {kind:'error',label:'已超时',hint:'执行超过时限'};
  if(typeof data?.exit_code==='number')return {kind:data.exit_code===0?'returned':'error',label:data.exit_code===0?'完成':'退出码 '+data.exit_code,hint:'退出码 '+data.exit_code};
  if(/^(Error\b|Failed\b|Tool (error|failed)\b)/i.test(text)||data?.isError===true||data?.success===false||['failed','error'].includes(status))return {kind:'error',label:'失败',hint:text};
  return {kind:'returned',label:'已返回',hint:'工具已返回结果，不代表任务验证通过'};
}

export function toolArgs(call:any):Record<string,any> {
  const raw=call.function?.arguments||'';
  try {return JSON.parse(raw)||{};}catch {
    // Preview may end mid-JSON; recover only a complete, correctly quoted field.
    const match=raw.match(/"(path|command|query|symbol|pattern|url)"\s*:\s*("(?:\\.|[^"\\])*")/);
    try{return match?{[match[1]]:JSON.parse(match[2])}:{};}catch{return {};}
  }
}

export function relativeTarget(target:string,root:string):string {
  const normalized=target.replace(/\\/g,'/'),base=root.replace(/\\/g,'/').replace(/\/$/,'');
  const windows=/^(?:[a-z]:|\/\/)/i.test(base);
  const comparable=windows?normalized.toLowerCase():normalized,prefix=(windows?base.toLowerCase():base)+'/';
  // Do not abbreviate outside-root paths or unresolved parent traversal.
  if(base&&comparable.startsWith(prefix)&&!normalized.split('/').includes('..'))return normalized.slice(base.length+1);
  return target;
}

export function toolTarget(call:any,root='') {
  const args=toolArgs(call),raw=String(args.path||args.command||args.query||args.symbol||args.pattern||args.url||'');
  return {raw,text:args.path?relativeTarget(raw,root):raw.replace(/\s+/g,' ').trim()};
}

export function failureHint(entry:ToolEntry):string {
  const text=String(entry.result?.content||'');
  if(entry.call.function.name==='read'&&(/Image input is not supported/.test(text)||(/\.(png|jpe?g|webp|gif|bmp|ico|avif)$/i.test(String(toolArgs(entry.call).path||''))&&/utf-8.*decode|Binary files/.test(text))))
    return '文本读取工具无法查看图片内容';
  if(/^(Error|Tool failed|Denied|Stopped|Interrupted)\b/i.test(text))return text.split('\n')[0].slice(0,140);
  return '';
}

export function visibleEntries(entries:ToolEntry[],expanded:boolean,pending:boolean,pinned=new Set<string>()) {
  // Never hide errors, denied actions, unknown outcomes or unfinished operations.
  return entries.map((entry,index)=>({entry,index})).filter(({entry,index})=>expanded||pinned.has(entry.key)||index>=entries.length-3||resultInfo(entry.result,pending).kind!=='returned');
}
