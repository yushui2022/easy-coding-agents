import React, {useEffect, useRef, useState} from 'react';
import {Plus, Check, ArrowClockwise, PlugsConnected, Desktop, Key, Cpu, SlidersHorizontal, LockSimple, Trash, PaintBrush, UserCircle, FileText} from '@phosphor-icons/react';
import {Dialog} from './Dialog';
import './model-settings.css';

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
  const [view,setView]=useState<'connections'|'personal'>('connections');
  const [personal,setPersonal]=useState({name:'',notes:'',instructions:''});
  const [personalStatus,setPersonalStatus]=useState('');
  const [savingPersonal,setSavingPersonal]=useState(false);
  const [theme,setTheme]=useState('system');
  useEffect(()=>{
    if(!open)return;
    void invoke('personalization.get')
      .then((value:any)=>setPersonal({name:value?.name||'',notes:value?.notes||'',instructions:value?.instructions||''}))
      .catch(()=>{});
    void window.eca?.theme?.().then((value:string)=>setTheme(String(value))).catch(()=>{});
  },[open]);
  const savePersonal = async () => {
    setSavingPersonal(true);setPersonalStatus('');
    try {
      const value:any = await invoke('personalization.save', personal);
      setPersonal({name:value.name,notes:value.notes,instructions:value.instructions});
      setPersonalStatus('已保存，下一轮对话生效。');
    } catch (error) {setPersonalStatus(String(error));}
    finally {setSavingPersonal(false);}
  };
  const chooseTheme = async (next:string) => {
    const applied = await window.eca?.setTheme?.(next).catch(()=>null);
    setTheme(String(applied||next));
  };
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
  const isDefault=!!current&&current.id===config.defaultId;
  return <Dialog title="模型与设置" closeLabel="关闭设置" wide className="model-settings" onClose={onClose}>
    <div className={'connection-layout'+(view==='personal'?' showing-personal':'')}>
      <aside className="connection-sidebar">
        <div className="settings-switch" role="tablist" aria-label="设置分区">
          <button type="button" role="tab" aria-selected={view==='connections'} className={view==='connections'?'active':''} onClick={()=>setView('connections')}>模型连接</button>
          <button type="button" role="tab" aria-selected={view==='personal'} className={view==='personal'?'active':''} onClick={()=>setView('personal')}>个人与全局</button>
        </div>
        <div className="connections-label"><span>模型连接</span><span>{config.connections?.length||0}</span></div>
        <button className="add-connection" disabled={busy} onClick={()=>select()}><Plus size={15}/>添加连接</button>
        <nav aria-label="已保存的模型连接">{config.connections?.map((c:any)=><button key={c.id} className={c.id===form.id?'selected':''} aria-pressed={c.id===form.id} disabled={busy} onClick={()=>select(c)}>
          <span className="connection-symbol">{c.no_auth?<Desktop size={17}/>:<PlugsConnected size={17}/>}</span>
          <span className="connection-item-copy"><strong>{c.name}</strong><span className="connection-model-id">{c.model}</span><small>{c.id===config.defaultId?'桌面默认':c.no_auth?'本机服务':c.credential_configured?'密钥已配置':'需补充密钥'}</small></span>
        </button>)}</nav>
        {!config.connections?.length&&<div className="connections-empty"><PlugsConnected size={24}/><p>从一个模型开始</p><span>添加 API 连接，或接入本机服务。</span></div>}
        <div className="connections-note"><LockSimple size={15}/><p>每个连接独立保存密钥。<br/>可选择系统加密保存。</p></div>
      </aside>
      {view==='personal'&&<section className="connection-editor personal-pane" aria-label="个人与全局">
        <div className="connection-scroll">
          <header className="connection-heading"><div><h3>个人与全局</h3><p>外观、对模型的自述，以及适用于所有项目的指令。</p></div></header>
          <section className="connection-section" aria-labelledby="personal-theme-heading">
            <h4 id="personal-theme-heading"><PaintBrush size={15}/>背景主题</h4>
            <div className="theme-choices" role="radiogroup" aria-label="背景主题">
              {[['system','跟随系统'],['light','浅色'],['dark','深色']].map(([value,label])=>
                <button key={value} type="button" role="radio" aria-checked={theme===value} aria-label={label}
                  className={'theme-choice'+(theme===value?' active':'')} onClick={()=>void chooseTheme(value)}>
                  {theme===value?<Check size={13}/>:<span className="theme-dot"/>}<span>{label}</span></button>)}
            </div>
            <p className="fine-print">只改变界面显示，不影响模型、项目或审批档位。</p>
          </section>
          <section className="connection-section" aria-labelledby="personal-profile-heading">
            <h4 id="personal-profile-heading"><UserCircle size={15}/>个人信息</h4>
            <div className="field"><label htmlFor="personal-name">称呼</label><input id="personal-name" maxLength={80} placeholder="模型怎么称呼你，可留空" value={personal.name} onChange={e=>setPersonal({...personal,name:e.target.value})}/></div>
            <div className="field"><label htmlFor="personal-notes">补充说明</label><textarea id="personal-notes" rows={3} maxLength={2000} placeholder="例如：偏好中文回答，解释先给结论" value={personal.notes} onChange={e=>setPersonal({...personal,notes:e.target.value})}/></div>
            <p className="fine-print">这两项会写进每轮对话的系统提示词，所有项目共用。</p>
          </section>
          <section className="connection-section" aria-labelledby="personal-agents-heading">
            <h4 id="personal-agents-heading"><FileText size={15}/>全局指令（AGENTS.md）</h4>
            <div className="field"><label htmlFor="personal-instructions">适用于所有项目的长期要求</label>
              <textarea id="personal-instructions" rows={8} maxLength={20000} spellCheck={false}
                placeholder={'每行一条，例如：\n回答前先说结论\n提交信息用英文'}
                value={personal.instructions} onChange={e=>setPersonal({...personal,instructions:e.target.value})}/></div>
            <p className="fine-print">保存到数据目录的 AGENTS.md，每轮对话都会带上；项目自己的 AGENTS.md 仍然优先。它不能改动审批权限或工具限制。</p>
          </section>
        </div>
        <footer className="connection-editor-footer">
          {(savingPersonal||personalStatus)&&<div className="config-status" role="status">{savingPersonal?'正在保存…':personalStatus}</div>}
          <div className="actions config-actions"><span className="save-state"><span/>保存在本机</span><button className="primary" disabled={savingPersonal} onClick={()=>void savePersonal()}>保存个人设置</button></div>
        </footer>
      </section>}
      <section className="connection-editor" aria-label="连接设置">
        <div className="connection-scroll">
          <header className="connection-heading"><div><h3>{current?current.name:'添加模型连接'}</h3><p>{current?'管理此连接使用的服务与模型。':'接入你喜欢的模型，开始协作。'}</p></div>{isDefault&&<span className="connection-default-badge"><Check size={12}/>桌面默认</span>}</header>
          <fieldset disabled={busy}>
            <section className="connection-section" aria-labelledby="connection-service-heading">
              <h4 id="connection-service-heading"><Key size={15}/>连接信息</h4>
              <div className={!form.id?'form-row connection-identity':''}>
                {!form.id&&<div className="field"><label htmlFor="provider">服务商</label><select id="provider" value={provider} onChange={e=>{
                  const selected=presets.find(p=>p.id===e.target.value)!;setProvider(selected.id);setModels([]);setStatus('');
                  setForm({...blank(),name:selected.id==='custom'?'':selected.name,base_url:selected.base_url,api_format:selected.api_format,no_auth:selected.id==='ollama'});
                }}>{presets.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></div>}
                <div className="field"><label htmlFor="connection-name">连接名称</label><input id="connection-name" placeholder="例如：我的 DeepSeek" maxLength={80} value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></div>
              </div>
              <div className="form-row connection-endpoint">
                <div className="field"><label htmlFor="api-format">协议</label><select id="api-format" value={form.api_format} onChange={e=>{setForm({...form,api_format:e.target.value,api_key:''});setModels([]);}}><option value="openai">OpenAI Chat 兼容</option><option value="responses">OpenAI Responses</option><option value="anthropic">Anthropic Messages</option></select></div>
                <div className="field"><label htmlFor="base-url">API 地址</label><input id="base-url" spellCheck={false} value={form.base_url} onChange={e=>{setForm({...form,base_url:e.target.value,api_key:''});setModels([]);}}/></div>
              </div>
              <div className="field credential-field"><label htmlFor="api-key">API 密钥 <span>{current?.credential_configured&&!current.no_auth?'已配置 · 同地址留空保留':''}</span></label><input id="api-key" type="password" autoComplete="off" placeholder={form.no_auth?'本机服务无需密钥':'输入密钥以获取可用模型'} disabled={form.no_auth} value={form.api_key} onChange={e=>setForm({...form,api_key:e.target.value})} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();void discover();}}}/></div>
              <div className="credential-options"><label className="checkbox"><input type="checkbox" checked={form.no_auth} onChange={e=>setForm({...form,no_auth:e.target.checked})}/>本机服务无需密钥</label><label className="checkbox"><input type="checkbox" disabled={form.no_auth} checked={form.persist} onChange={e=>setForm({...form,persist:e.target.checked})}/>系统加密保存</label></div>
            </section>
            <section className="connection-section" aria-labelledby="connection-model-heading">
              <h4 id="connection-model-heading"><Cpu size={15}/>模型与响应</h4>
              <div className="field model-field"><label htmlFor="available-models">选择模型{models.length>0?`（${models.length}）`:''}</label><div><select id="available-models" aria-label="服务返回的模型" disabled={!models.length||discovering} value={models.includes(form.model)?form.model:''} onChange={e=>setForm({...form,model:e.target.value})}><option value="" disabled>{discovering?'正在获取模型…':form.model?`当前模型：${form.model}`:'请选择可用模型'}</option>{models.map(id=><option key={id} value={id}>{id}</option>)}</select><button onClick={discover} disabled={discovering} aria-label="刷新模型列表" title="刷新模型列表"><ArrowClockwise size={15}/><span>{discovering?'获取中':'刷新'}</span></button></div></div>
              <p className="fine-print catalogue-status" aria-live="polite">{catalogueStatus||'输入密钥后自动获取可用模型，无需下载模型文件。'}</p>
              <details className="manual-model"><summary>手动填写模型 ID</summary><div className="field"><label htmlFor="model-name">模型名称</label><input id="model-name" spellCheck={false} placeholder="服务不提供列表时，在这里填写模型 ID" value={form.model} onChange={e=>setForm({...form,model:e.target.value})}/></div></details>
              {form.api_format==='openai'&&form.model.toLowerCase().startsWith('deepseek')&&<div className="field response-mode"><label htmlFor="thinking-mode">响应模式</label><select id="thinking-mode" value={form.thinking_mode} onChange={e=>setForm({...form,thinking_mode:e.target.value})}><option value="fast">快速 · 关闭深度思考</option><option value="balanced">均衡 · 轻量思考</option><option value="deep">深入 · 高强度思考</option><option value="default">跟随服务默认</option></select><p className="fine-print">深入模式会增加等待时间和用量；兼容服务需支持 DeepSeek thinking 参数。</p></div>}
            </section>
            <section className="connection-section connection-usage" aria-labelledby="connection-usage-heading">
              <h4 id="connection-usage-heading"><SlidersHorizontal size={15}/>使用方式</h4>
              <label className="checkbox"><input type="checkbox" checked={form.make_default||isDefault} disabled={isDefault} onChange={e=>setForm({...form,make_default:e.target.checked})}/>设为桌面默认模型</label>
              <p className="fine-print">项目可单独选择其他模型。保存连接不会中断当前任务。</p>
              {current&&<div className="connection-actions">
                {state.project&&<button disabled={busy||state.busy||dirty} onClick={async()=>{setBusy(true);try{if(!await onUse(current.id))setStatus('切换失败，请确认当前任务已停止，或在模型选择器中查看原因。');}finally{setBusy(false);}}}>用于当前项目</button>}
                {current.id!==config.defaultId&&<button disabled={busy||dirty} onClick={()=>action('config.default',{id:current.id},result=>{onConfig(result);setStatus('桌面默认模型已更新；当前项目通过模型选择器切换。');})}>设为默认</button>}
                <button className="remove-connection" disabled={busy||state.busy} onClick={()=>setConfirmRemove(true)}><Trash size={14}/>移除连接</button>
              </div>}
            </section>
          </fieldset>
          {current&&confirmRemove&&<div className="connection-remove-confirm"><p>移除「{current.name}」及其保存的密钥？正在使用或被项目指定的连接需要先切换。</p><div className="actions"><button onClick={()=>setConfirmRemove(false)}>取消</button><button disabled={busy||state.busy} onClick={()=>action('config.remove',{id:current.id},result=>{onConfig(result);drafts.current.delete(current.id);setForm(blank());setModels([]);setConfirmRemove(false);setStatus('连接已移除。');})}>确认移除</button></div></div>}
        </div>
        <footer className="connection-editor-footer">
          {(busy||status)&&<div className="config-status" role="status">{busy?'正在处理…':status}</div>}
          <div className="actions config-actions"><span className={'save-state'+(dirty?' unsaved':'')}><span/>{dirty?'尚未保存':'已保存'}</span><button onClick={check} disabled={busy||!form.model.trim()}>测试连接</button><button className="primary" onClick={save} disabled={busy||!form.model.trim()}>保存配置</button></div>
          <p className="connection-test-note">连接测试会发送一次小请求，可能产生费用。</p>
        </footer>
      </section>
    </div>
    <footer className="model-settings-footer">
      {state.project?<p className="current-model-note" title={state.settings?.model}>当前项目 <strong>{state.settings?.model}</strong><span>{state.settings?.source==='desktop'?'桌面连接':'项目配置'}</span></p>:<p className="current-model-note"><Desktop size={13}/>本地工作区</p>}
      <p className="data-location" title={config.dataHome}><LockSimple size={13}/><span>{config.dataHome}</span></p>
    </footer>
  </Dialog>;
}
