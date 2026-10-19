import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

export type Model = {model: string; base_url: string; api_format: string; thinking_mode?: string};
function thinking(value:Model) {
  const supported=value.api_format==='openai'&&value.model.toLowerCase().startsWith('deepseek');
  return supported ? value.thinking_mode || 'fast' : 'default';
}
type Connection = Model & {id: string; name: string; no_auth: boolean; encryptedKey?: string};
type Preferences = {schema: 2; connections: Connection[]; defaultId?: string; projects: Record<string,string>; recent: string[]};
type Cipher = {isEncryptionAvailable(): boolean; encryptString(value:string): Buffer; decryptString(value:Buffer): string};

export class Connections {
  private data: Preferences;
  private keys = new Map<string,string>();
  constructor(private file: string, private cipher: Cipher) {
    let raw: any = {};
    try {raw=JSON.parse(fs.readFileSync(file,'utf8'));}
    catch(error:any) {if(error.code!=='ENOENT') throw new Error('模型配置文件无法读取，请保留文件并检查格式。');}
    if(raw.schema===2) {
      if(!Array.isArray(raw.connections)||!raw.projects||!Array.isArray(raw.recent)) throw new Error('模型配置格式不完整。');
      this.data=raw;
    } else {
      // Migrate ciphertext in memory; never decrypt/re-encrypt just to upgrade the schema.
      const migrated:Connection[] = raw.model ? [{...raw.model,id:'legacy-default',name:raw.model.model,no_auth:false,
        ...(raw.encryptedKey ? {encryptedKey:raw.encryptedKey} : {})}] : [];
      this.data={schema:2,connections:migrated,defaultId:migrated[0]?.id,projects:{},recent:raw.recent||[]};
    }
  }
  private write(next:Preferences) {
    fs.mkdirSync(path.dirname(this.file),{recursive:true});
    fs.writeFileSync(this.file+'.tmp',JSON.stringify(next,null,2),{mode:0o600});
    fs.renameSync(this.file+'.tmp',this.file);
    this.data=next;
  }
  private find(id:string) {
    const value=this.data.connections.find(c=>c.id===id);
    if(!value) throw new Error('模型连接不存在，请刷新设置。');
    return value;
  }
  private key(value:Connection) {
    if(this.keys.has(value.id)) return this.keys.get(value.id)!;
    if(value.encryptedKey) {
      try{return this.cipher.decryptString(Buffer.from(value.encryptedKey,'base64'));}
      catch {throw new Error('无法解密此连接的密钥，请重新输入。');}
    }
    return '';
  }
  public() {
    const connections=this.data.connections.map(c=>({id:c.id,name:c.name,model:c.model,base_url:c.base_url,api_format:c.api_format,
      thinking_mode:thinking(c),no_auth:c.no_auth,credential_configured:c.no_auth||!!(this.keys.get(c.id)||c.encryptedKey),persist:!!c.encryptedKey}));
    const selected=connections.find(c=>c.id===this.data.defaultId);
    return {connections,defaultId:this.data.defaultId,recent:this.data.recent,
      model:selected,credential_configured:!!selected?.credential_configured};
  }
  // Resolve a form without writing. Existing secrets are reusable only at the same endpoint/protocol.
  resolve(input:any, requireModel=true) {
    if(!input||typeof input!=='object') throw new Error('连接参数无效。');
    const old=input.id ? this.find(input.id) : undefined;
    const api_format=input.api_format;
    if(!['openai','responses','anthropic'].includes(api_format)) throw new Error('请选择支持的协议。');
    if(typeof input.base_url!=='string') throw new Error('请输入 API 地址。');
    let url:URL;
    try {url=new URL(input.base_url.trim());} catch {throw new Error('API 地址格式无效。');}
    if(!['https:','http:'].includes(url.protocol)||url.username||url.password||url.search||url.hash) throw new Error('API 地址不能包含密钥、参数或片段。');
    const base_url=url.toString().replace(/\/+$/,'');
    const no_auth=input.no_auth===true;
    if(no_auth&&!['localhost','127.0.0.1','[::1]'].includes(url.hostname)) throw new Error('免密钥模式仅适用于本机服务。');
    const model=typeof input.model==='string'?input.model.trim():'';
    if(requireModel&&!model) throw new Error('请选择模型或填写模型 ID。');
    if(model.length>256) throw new Error('模型 ID 过长。');
    if(input.thinking_mode!==undefined&&!['default','fast','balanced','deep'].includes(input.thinking_mode)) throw new Error('响应模式无效。');
    const thinking_mode=thinking({model,base_url,api_format,thinking_mode:input.thinking_mode});
    if(input.api_key!==undefined&&typeof input.api_key!=='string') throw new Error('密钥格式无效。');
    const fresh=(input.api_key||'').trim();
    const sameEndpoint=old&&old.base_url.replace(/\/+$/,'')===base_url&&old.api_format===api_format;
    const api_key=no_auth?'eca-local':fresh||(sameEndpoint?this.key(old):'');
    if(!api_key) throw new Error(old&&!sameEndpoint?'地址或协议已改变，请为新地址重新输入密钥。':'请输入 API 密钥；本地服务可选择免密钥模式。');
    return {model,base_url,api_format,api_key,no_auth,thinking_mode};
  }
  save(input:any) {
    const value=this.resolve(input);
    const name=typeof input.name==='string'&&input.name.trim()?input.name.trim():value.model;
    if(name.length>80) throw new Error('连接名称最多 80 个字符。');
    const id=input.id||randomUUID();
    const next:Connection={id,name,model:value.model,base_url:value.base_url,api_format:value.api_format,no_auth:value.no_auth,thinking_mode:value.thinking_mode};
    let warning='';
    if(!value.no_auth&&input.persist!==false) {
      if(this.cipher.isEncryptionAvailable()) next.encryptedKey=this.cipher.encryptString(value.api_key).toString('base64');
      else warning='系统加密不可用，密钥仅供本次运行使用。';
    }
    const connections=this.data.connections.filter(c=>c.id!==id);
    const oldIndex=this.data.connections.findIndex(c=>c.id===id);
    connections.splice(oldIndex<0?connections.length:oldIndex,0,next);
    this.write({...this.data,connections,defaultId:input.make_default||!this.data.defaultId?id:this.data.defaultId});
    if(value.no_auth||next.encryptedKey) this.keys.delete(id); else this.keys.set(id,value.api_key);
    return {...this.public(),savedId:id,warning};
  }
  runtime(id:string) {
    const value=this.find(id);
    const api_key=value.no_auth?'eca-local':this.key(value);
    if(!api_key) throw new Error('此连接的临时密钥已失效，请在模型设置中重新输入。');
    return {model:value.model,base_url:value.base_url,api_format:value.api_format,api_key,thinking_mode:thinking(value)};
  }
  setDefault(id:string) {this.find(id);this.write({...this.data,defaultId:id});return this.public();}
  remove(id:string) {
    this.find(id);
    if(this.data.defaultId===id||Object.values(this.data.projects).includes(id)) throw new Error('此连接仍是默认模型或被项目使用，请先切换后再移除。');
    this.write({...this.data,connections:this.data.connections.filter(c=>c.id!==id)});
    this.keys.delete(id);return this.public();
  }
  private projectKey(folder:string) {const key=path.resolve(folder);return process.platform==='win32'?key.toLowerCase():key;}
  choice(folder:string) {return this.data.projects[this.projectKey(folder)]||'default';}
  selection(choice:string) {
    const id=choice==='default'?this.data.defaultId:choice;
    if(choice==='project'||!id) return {choice,connection_id:null,name:'项目配置',model:{}};
    const c=this.find(id);
    return {choice,connection_id:id,name:c.name,model:this.runtime(id)};
  }
  remember(folder:string,choice:string) {
    if(!['default','project'].includes(choice)) this.find(choice);
    const projects={...this.data.projects};
    if(choice==='default') delete projects[this.projectKey(folder)]; else projects[this.projectKey(folder)]=choice;
    this.write({...this.data,projects});
  }
  opened(folder:string) {this.write({...this.data,recent:[folder,...this.data.recent.filter(p=>this.projectKey(p)!==this.projectKey(folder))].slice(0,12)});}
}
