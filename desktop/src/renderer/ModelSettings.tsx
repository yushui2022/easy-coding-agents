import React, {useEffect, useRef, useState} from 'react';
import {Plus, Check, ArrowClockwise} from '@phosphor-icons/react';
import {Dialog} from './Dialog';

const presets = [
  {id:'deepseek',name:'DeepSeek',base_url:'https://api.deepseek.com/v1',api_format:'openai'},
  {id:'openai',name:'OpenAI',base_url:'https://api.openai.com/v1',api_format:'responses'},
  {id:'anthropic',name:'Anthropic',base_url:'https://api.anthropic.com/v1',api_format:'anthropic'},
  {id:'ollama',name:'Ollama 本地',base_url:'http://localhost:11434/v1',api_format:'openai'},
  {id:'custom',name:'自定义兼容服务',base_url:'',api_format:'openai'},
];
const blank = () => ({id:'',name:'',model:'',base_url:'https://api.deepseek.com/v1',api_format:'openai',thinking_mode:'fast',api_key:'',no_auth:false,persist:true,make_default:false});
type Form = ReturnType<typeof blank>;
const fromConnection = (c:any):Form => ({...blank(),...c,api_key:'',make_default:false});
const invoke = (method:string,params:Record<string,unknown>={}) => window.eca.invoke(method,params);

export function ModelPicker({config,state,busy,error,onClose,onChoose,onManage}:any) {
  const [search,setSearch]=useState('');
  const selected=state.project?state.model_selection?.choice:'default';
  const defaultModel=config.connections?.find((c:any)=>c.id===config.defaultId);
  return <Dialog title="选择模型" closeLabel="关闭模型选择" onClose={onClose}>
    <p className="dialog-intro">{state.project?'选择会保存在当前项目，下次打开继续使用。':'选择一个连接作为桌面默认模型。'}</p>
    <input className="model-search" aria-label="搜索模型" placeholder="搜索连接名称或模型 ID" value={search} onChange={e=>setSearch(e.target.value)}/>
    <div className="model-options">
      {state.project&&<button className="model-option" aria-pressed={selected==='default'} disabled={busy||!defaultModel} onClick={()=>onChoose('default')}><div><strong>跟随桌面默认</strong><span>{defaultModel?defaultModel.name+' · '+defaultModel.model:'尚未设置默认连接'}</span></div>{selected==='default'&&<Check size={17}/>}</button>}
      {(config.connections||[]).filter((c:any)=>(c.name+' '+c.model).toLowerCase().includes(search.toLowerCase())).map((c:any)=><button className="model-option" key={c.id} aria-pressed={state.project?selected===c.id:config.defaultId===c.id} disabled={busy||!c.credential_configured} onClick={()=>onChoose(c.id)}><div><strong>{c.name}{c.id===config.defaultId&&<small>默认</small>}</strong><span>{c.model}</span><span>{c.base_url}{!c.credential_configured?' · 需补充密钥':''}</span></div>{(state.project?selected===c.id:config.defaultId===c.id)&&<Check size={17}/>}</button>)}
      {state.project&&<button className="model-option project-model-option" aria-pressed={selected==='project'} disabled={busy} onClick={()=>onChoose('project')}><div><strong>沿用项目配置</strong><span>使用项目的 .env、eca.toml 与环境变量</span></div>{selected==='project'&&<Check size={17}/>}</button>}
    </div>
    {busy&&<p className="muted">任务结束或停止后可以切换模型。</p>}
    {error&&<p className="config-status" role="alert">{error}</p>}
    <button className="manage-models" onClick={onManage}><Plus size={16}/>添加或管理模型连接</button>
  </Dialog>;
}

export function ModelSettings({open,config,state,onConfig,onClose,onUse}:any) {
  const [form,setForm]=useState<Form>(blank);
  const [provider,setProvider]=useState('deepseek');
  const [models,setModels]=useState<string[]>([]);
  const [catalogueStatus,setCatalogueStatus]=useState('');
  const [discovering,setDiscovering]=useState(false);
  const catalogueRequest=useRef(0);
  const catalogueTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const [status,setStatus]=useState('');
  const [busy,setBusy]=useState(false);
  const [confirmRemove,setConfirmRemove]=useState(false);
  const initialized=useRef(false);
  const drafts=useRef(new Map<string,Form>());
  useEffect(()=>{
    if(!initialized.current&&config.connections){
      initialized.current=true;
      const first=config.connections.find((c:any)=>c.id===config.defaultId)||config.connections[0];
      if(first){setForm(fromConnection(first));setProvider('custom');}
    }
  },[config.connections]);
  const current=config.connections?.find((c:any)=>c.id===form.id);
  // A response belongs to one endpoint, credential and connection only. Closing or
  // editing the form invalidates it; a slow request must never replace another list.
  useEffect(()=>{
    ++catalogueRequest.current;
    setModels([]);setCatalogueStatus('');setDiscovering(false);
    if(!open)return;
    let url:URL;
    try {url=new URL(form.base_url.trim());} catch {return;}
    if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)return;
    const local=form.no_auth&&['localhost','127.0.0.1','[::1]'].includes(url.hostname);
    const saved=!current?.no_auth&&current?.credential_configured&&current.api_format===form.api_format&&current.base_url.replace(/\/+$/,'')===url.toString().replace(/\/+$/,'');
    if(!local&&!form.api_key.trim()&&!saved)return;
    const timer=setTimeout(()=>{void discover();},900);
    catalogueTimer.current=timer;
    return ()=>{clearTimeout(timer);++catalogueRequest.current;};
  },[open,form.id,form.base_url,form.api_format,form.api_key,form.no_auth,current?.credential_configured]);
  const dirty=!current||!!form.api_key||form.make_default||['name','model','base_url','api_format','thinking_mode','no_auth','persist'].some(key=>form[key as keyof Form]!==current[key]);
  function select(c?:any) {
    drafts.current.set(form.id,form);
    setForm(drafts.current.get(c?.id||'')||(c?fromConnection(c):blank()));
    setProvider(c?'custom':'deepseek');setModels([]);setStatus('');setConfirmRemove(false);
  }
  async function action(method:string,params:any,onResult?:(value:any)=>void) {
    setBusy(true);setStatus('');
    try {const result=await invoke(method,params);onResult?.(result);return result;}
    catch(e){setStatus(String(e));return null;}finally{setBusy(false);}
  }
  async function save() {
    await action('config.save',form,result=>{
      onConfig(result);const saved=result.connections.find((c:any)=>c.id===result.savedId);
      drafts.current.delete(form.id);setForm(fromConnection(saved));setStatus(result.warning||'配置已保存。可测试连接，或用于当前项目。');
    });
  }
  async function discover() {
    clearTimeout(catalogueTimer.current);
    const request=++catalogueRequest.current;
    setDiscovering(true);setCatalogueStatus('正在获取可用模型…');
    try {
      const result=await invoke('config.models',{draft:form});
      if(request!==catalogueRequest.current)return;
      setModels(result.models||[]);
      setCatalogueStatus(result.message+(result.models?.length?'':' 可手动填写模型 ID。'));
    } catch(e) {
      if(request===catalogueRequest.current){setModels([]);setCatalogueStatus(String(e)+' 可重试或手动填写模型 ID。');}
    } finally {if(request===catalogueRequest.current)setDiscovering(false);}
  }
  async function check() {
    await action('config.check',{draft:form},result=>setStatus((result.status==='ok'?'连接成功':'连接失败')+' · '+result.message));
  }
  if(!open)return null;
  return <Dialog title="模型与设置" closeLabel="关闭设置" wide onClose={onClose}>
    <p className="dialog-intro">选择服务商并输入密钥，自动获取可用模型；选择模型后保存即可。</p>
    <div className="connection-layout">
      <div className="connection-sidebar">
        <button className="add-connection" disabled={busy} onClick={()=>select()}><Plus size={15}/>添加连接</button>
        <nav aria-label="已保存的模型连接">{config.connections?.map((c:any)=><button key={c.id} className={c.id===form.id?'selected':''} disabled={busy} onClick={()=>select(c)}><strong>{c.name}</strong><span>{c.model}</span><small>{c.id===config.defaultId?'桌面默认':c.credential_configured?'已配置':'需补充密钥'}</small></button>)}</nav>
        <p className="fine-print">每个连接分别保存密钥。项目中的配置文件不会被改写。</p>
      </div>
      <div className="connection-editor">
        <fieldset disabled={busy}>
          {!form.id&&<div className="field"><label htmlFor="provider">服务商</label><select id="provider" value={provider} onChange={e=>{
            const selected=presets.find(p=>p.id===e.target.value)!;setProvider(selected.id);setModels([]);setStatus('');
            setForm({...blank(),name:selected.id==='custom'?'':selected.name,base_url:selected.base_url,api_format:selected.api_format,no_auth:selected.id==='ollama'});
          }}>{presets.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></div>}
          <div className="field"><label htmlFor="connection-name">连接名称</label><input id="connection-name" placeholder="例如：我的 DeepSeek" maxLength={80} value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></div>
          <div className="form-row">
            <div className="field"><label htmlFor="api-format">协议</label><select id="api-format" value={form.api_format} onChange={e=>{setForm({...form,api_format:e.target.value,api_key:''});setModels([]);}}><option value="openai">OpenAI Chat 兼容</option><option value="responses">OpenAI Responses</option><option value="anthropic">Anthropic Messages</option></select></div>
            <div className="field"><label htmlFor="base-url">API 地址</label><input id="base-url" spellCheck={false} value={form.base_url} onChange={e=>{setForm({...form,base_url:e.target.value,api_key:''});setModels([]);}}/></div>
          </div>
          <div className="field"><label htmlFor="api-key">API 密钥 <span>{current?.credential_configured&&!current.no_auth?'已配置 · 同地址留空保留':''}</span></label><input id="api-key" type="password" autoComplete="off" disabled={form.no_auth} value={form.api_key} onChange={e=>setForm({...form,api_key:e.target.value})} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();void discover();}}}/></div>
          <div className="credential-options"><label className="checkbox"><input type="checkbox" checked={form.no_auth} onChange={e=>setForm({...form,no_auth:e.target.checked})}/>本机服务无需密钥</label><label className="checkbox"><input type="checkbox" disabled={form.no_auth} checked={form.persist} onChange={e=>setForm({...form,persist:e.target.checked})}/>系统加密保存</label></div>
          <div className="field model-field"><label htmlFor="available-models">选择模型{models.length>0?`（${models.length}）`:''}</label><div><select id="available-models" aria-label="服务返回的模型" disabled={!models.length||discovering} value={models.includes(form.model)?form.model:''} onChange={e=>setForm({...form,model:e.target.value})}><option value="" disabled>{discovering?'正在获取模型…':form.model?`当前模型：${form.model}`:'请选择可用模型'}</option>{models.map(id=><option key={id} value={id}>{id}</option>)}</select><button onClick={discover} disabled={discovering}><ArrowClockwise size={15}/>{discovering?'正在获取…':'刷新模型列表'}</button></div></div>
          <p className="fine-print catalogue-status" aria-live="polite">{catalogueStatus||'输入密钥后自动获取模型列表，也可以手动填写模型 ID。'}</p>
          <details className="manual-model"><summary>手动填写模型 ID</summary><div className="field"><label htmlFor="model-name">模型名称</label><input id="model-name" spellCheck={false} placeholder="服务不提供列表时，在这里填写模型 ID" value={form.model} onChange={e=>setForm({...form,model:e.target.value})}/></div></details>
          {form.api_format==='openai'&&form.model.toLowerCase().startsWith('deepseek')&&<div className="field"><label htmlFor="thinking-mode">响应模式</label><select id="thinking-mode" value={form.thinking_mode} onChange={e=>setForm({...form,thinking_mode:e.target.value})}><option value="fast">快速 · 关闭深度思考</option><option value="balanced">均衡 · 轻量思考</option><option value="deep">深入 · 高强度思考</option><option value="default">跟随服务默认</option></select><p className="fine-print">日常修改默认使用快速模式。复杂推理可切换深入模式，会增加等待时间和用量。兼容服务需要支持 DeepSeek thinking 参数。</p></div>}
          <label className="checkbox"><input type="checkbox" checked={form.make_default||current?.id===config.defaultId} disabled={current?.id===config.defaultId} onChange={e=>setForm({...form,make_default:e.target.checked})}/>设为桌面默认模型</label>
          <div className="actions config-actions">{dirty&&<span className="unsaved">尚未保存</span>}<button onClick={check} disabled={!form.model.trim()}>测试连接</button><button className="primary" onClick={save} disabled={!form.model.trim()}>保存配置</button></div>
        </fieldset>
        {busy&&<div className="config-status" role="status">正在处理…</div>}
        {!busy&&status&&<div className="config-status" role="status">{status}</div>}
        <p className="fine-print">获取的是服务端模型列表，无需下载模型文件。连接测试发送一次小请求，可能产生费用。修改地址或协议后，需要重新输入密钥。</p>
        {current&&<div className="connection-actions">
          {state.project&&<button className="primary" disabled={busy||state.busy||dirty} onClick={async()=>{setBusy(true);try{if(!await onUse(current.id))setStatus('切换失败，请确认当前任务已停止，或在模型选择器中查看原因。');}finally{setBusy(false);}}}>用于当前项目</button>}
          {current.id!==config.defaultId&&<button disabled={busy||dirty} onClick={()=>action('config.default',{id:current.id},result=>{onConfig(result);setStatus('桌面默认模型已更新；当前项目通过模型选择器切换。');})}>设为默认</button>}
          <button disabled={busy||state.busy} onClick={()=>setConfirmRemove(true)}>移除连接</button>
        </div>}
        {current&&confirmRemove&&<div className="config-status"><p>移除「{current.name}」及其保存的密钥？正在使用或被项目指定的连接需要先切换。</p><div className="actions"><button onClick={()=>setConfirmRemove(false)}>取消</button><button disabled={busy||state.busy} onClick={()=>action('config.remove',{id:current.id},result=>{onConfig(result);drafts.current.delete(current.id);setForm(blank());setModels([]);setConfirmRemove(false);setStatus('连接已移除。');})}>确认移除</button></div></div>}
      </div>
    </div>
    {state.project&&<p className="current-model-note">当前项目：{state.settings?.model} · {state.settings?.source==='desktop'?'桌面连接':'项目配置与环境变量'}。保存连接不会中断正在执行的任务。</p>}
    <p className="data-location">应用数据 · {config.dataHome}</p>
  </Dialog>;
}
