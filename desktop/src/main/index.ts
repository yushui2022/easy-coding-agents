import { app, BrowserWindow, ipcMain, dialog, safeStorage, shell, screen, protocol, clipboard, nativeTheme } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { RpcClient } from './rpc-client';
import { Connections } from './connections';
import {BrowserManager} from './browser-manager';
import {TerminalManager} from './terminal-manager';
protocol.registerSchemesAsPrivileged([{scheme:'eca-preview',privileges:{standard:true,secure:true,supportFetchAPI:true,corsEnabled:true}}]);
let browsers:BrowserManager;
let terminals:TerminalManager;
let workspaceOwner='';
let activeProject='';
let activeSession='';
const workspaces=new Map<string,{project:string;session:string;browsers:BrowserManager;terminals:TerminalManager}>();
const contextKey=(project:string,session:string)=>JSON.stringify([project,session]);
let occluded=false;
let sideNotification:ReturnType<typeof setTimeout>|undefined;
let childNotification:ReturnType<typeof setTimeout>|undefined;

const home = process.env.ECA_DESKTOP_DATA_HOME || (process.platform === 'win32' && fs.existsSync('G:\\') ? 'G:\\Data\\ECA\\Desktop' : app.getPath('userData'));
const dataHomeGiven = !!process.env.ECA_DESKTOP_DATA_HOME;
fs.mkdirSync(home, {recursive: true});
app.setPath('userData', home);
const cacheHome = process.env.ECA_DESKTOP_CACHE_HOME || (!dataHomeGiven && fs.existsSync('G:/') ? 'G:/DevCache/eca-desktop' : path.join(home, 'cache'));
fs.mkdirSync(cacheHome, {recursive: true});
// Which projects were open last run: restored on launch so the sidebar shows the
// project and session tree instead of a bare list of recent folders.
const openProjectsFile = path.join(home, 'open-projects.json');
function readOpenProjects(): string[] {
  try {
    const rows = JSON.parse(fs.readFileSync(openProjectsFile, 'utf8'));
    return Array.isArray(rows) ? rows.filter((row: unknown) => typeof row === 'string').slice(0, 8) : [];
  } catch { return []; }
}
function rememberOpenProject(folder: string, remove = false) {
  const rows = readOpenProjects().filter(row => row !== folder);
  if (!remove) rows.unshift(folder);
  try { fs.writeFileSync(openProjectsFile, JSON.stringify(rows.slice(0, 8))); } catch { /* best effort */ }
}
app.setPath('sessionData', cacheHome);
const tempHome = path.join(cacheHome, 'temp');
fs.mkdirSync(tempHome, {recursive: true});
app.setPath('temp', tempHome);
process.env.TEMP = tempHome;
process.env.TMP = tempHome;
const root = path.resolve(__dirname, '../../..');
const html = path.resolve(__dirname, '../renderer/index.html');
const connections = new Connections(path.join(home, 'preferences.json'), safeStorage);
// The theme lives in its own small file: it is a display preference, not a model
// connection, and nativeTheme.themeSource drives prefers-color-scheme for the UI.
type ThemeSource = 'system' | 'light' | 'dark';
const themeFile = path.join(home, 'theme.json');
const themeSources: ThemeSource[] = ['system', 'light', 'dark'];
function readTheme(): ThemeSource {
  try {const raw = JSON.parse(fs.readFileSync(themeFile, 'utf8')); return themeSources.includes(raw?.source) ? raw.source : 'system';}
  catch {return 'system';}
}
function writeTheme(source: ThemeSource) {
  try {fs.writeFileSync(themeFile, JSON.stringify({source}), {mode: 0o600});} catch { /* a failed write must not block the window */ }
}
nativeTheme.themeSource = readTheme();

// User-level context that applies to every project. The backend reads these two
// files on each turn, so edits take effect without restarting it.
const profileFile = path.join(home, 'profile.json');
const globalAgentsFile = path.join(home, 'AGENTS.md');
process.env.ECA_USER_PROFILE = profileFile;
process.env.ECA_GLOBAL_AGENTS = globalAgentsFile;
type Personalization = {name:string; notes:string; instructions:string};
const limits = {name:80, notes:2000, instructions:20000};
function readPersonalization(): Personalization {
  let name = '', notes = '';
  try {
    const raw = JSON.parse(fs.readFileSync(profileFile, 'utf8'));
    if (typeof raw?.name === 'string') name = raw.name;
    if (typeof raw?.notes === 'string') notes = raw.notes;
  } catch { /* a missing or corrupt profile is simply empty */ }
  let instructions = '';
  try {instructions = fs.readFileSync(globalAgentsFile, 'utf8');} catch { /* not created yet */ }
  return {name:name.slice(0,limits.name), notes:notes.slice(0,limits.notes),
    instructions:instructions.slice(0,limits.instructions)};
}
function savePersonalization(params:any): Personalization {
  const text = (value:unknown, limit:number) => typeof value === 'string' ? value.slice(0,limit) : '';
  const name = text(params?.name, limits.name).trim();
  const notes = text(params?.notes, limits.notes).trim();
  const instructions = text(params?.instructions, limits.instructions);
  fs.mkdirSync(home, {recursive:true});
  try {
    if (name || notes) fs.writeFileSync(profileFile, JSON.stringify({name, notes}), {mode:0o600});
    else fs.rmSync(profileFile, {force:true});
    if (instructions.trim()) fs.writeFileSync(globalAgentsFile, instructions, {mode:0o600});
    else fs.rmSync(globalAgentsFile, {force:true});
  } catch (error) {throw new Error('无法写入个人设置：' + (error instanceof Error ? error.message : String(error)));}
  return readPersonalization();
}
let activeSelection: {choice:string; connection_id:string|null; name:string}|undefined;
const sessionSelections=new Map<string,NonNullable<typeof activeSelection>>();
let selecting = false;
let window: BrowserWindow;
let rpc: RpcClient | undefined;
let starting: Promise<RpcClient> | undefined;
let quitting = false;
let closing = false;
let opening = false;
let liveNotification: ReturnType<typeof setTimeout>|undefined;
const publish = (channel: string, data?: unknown) => {if (window && !window.isDestroyed()) window.webContents.send(channel, data);};
async function publicConfig() {
  const value=connections.public();
  const capabilities=await (await backend()).call('model.capabilities',{models:value.connections});
  const models=value.connections.map((c,i)=>({...c,reasoning:capabilities[i]}));
  return {...value,connections:models,model:models.find(c=>c.id===value.defaultId),dataHome:home,version:app.getVersion()};
}
function usedModel(id?:string|null) {connections.used(id);publish('eca:changed',{event:'config'});}
function decorate(value:any) {
  return value?.project ? {...value,workspace_owner:contextKey(value.project_id,value.session_id),
    model_selection:sessionSelections.get(contextKey(value.project_id,value.session_id))} : value;
}
async function bindWorkspace(value:any) {
  browsers?.hide();
  activeProject=value.project_id||'';activeSession=value.session_id||'';
  workspaceOwner=value.project?contextKey(activeProject,activeSession):'';
  activeSelection=sessionSelections.get(workspaceOwner);
  if(!workspaceOwner){terminals=new TerminalManager();browsers=new BrowserManager(window);return;}
  let entry=workspaces.get(workspaceOwner);
  if(!entry){
    const browser=new BrowserManager(window),terminal=new TerminalManager();
    terminal.root=value.project;await browser.bind(value.project);
    entry={project:activeProject,session:activeSession,browsers:browser,terminals:terminal};
    workspaces.set(workspaceOwner,entry);
  }
  browsers=entry.browsers;terminals=entry.terminals;
}
async function closeWorkspaces(project?:string) {
  const entries=[...workspaces].filter(([,w])=>!project||w.project===project);
  await Promise.all(entries.map(async([key,w])=>{
    w.browsers.closeAll();await w.terminals.closeAll();
    if(workspaces.get(key)===w){workspaces.delete(key);sessionSelections.delete(key);}
  }));
}
async function backend() {
  if (starting) return starting;
  if (rpc && !rpc.exited) return rpc;
  const command = app.isPackaged ? path.join(process.resourcesPath, 'backend', 'eca-backend.exe') : (process.env.ECA_PYTHON || 'python');
  rpc = new RpcClient(command, app.isPackaged ? [] : ['-B', '-m', 'eca.desktop_rpc'], app.isPackaged ? home : root);
  rpc.on('event', data => {
    if(data.event==='subagent_progress'&&['text','model_activity'].includes(data.data?.event)) {
      if(!childNotification)childNotification=setTimeout(()=>{childNotification=undefined;publish('eca:changed',{event:'subagent_live'});},120);
      return;
    }
    if(data.event==='sidechat') {
      if(!sideNotification)sideNotification=setTimeout(()=>{sideNotification=undefined;publish('eca:changed',{event:'sidechat'});},80);
      return;
    }
    if(data.event==='text'||data.event==='model_activity') {
      if(!liveNotification)liveNotification=setTimeout(()=>{liveNotification=undefined;publish('eca:changed',{event:'text'});},80);
    } else {clearTimeout(liveNotification);liveNotification=undefined;publish('eca:changed', {event:data.event});}
  });
  rpc.on('failure', message => {
    clearTimeout(liveNotification);liveNotification=undefined;
    workspaceOwner='';activeProject='';activeSession='';activeSelection=undefined;sessionSelections.clear();
    void closeWorkspaces().catch(()=>{});publish('eca:failure', message);
  });
  const client = rpc;
  starting = client.call('initialize', {protocol: 1}).then(() => client);
  try {return await starting;} finally {starting = undefined;}
}
async function openProject(folder: string) {
  if (opening) throw new Error('正在打开项目，请稍候。');
  opening = true;
  try {
    const client = await backend();
    const selection=connections.selection(connections.choice(folder));
    const {model,...metadata}=selection;
    const result = await client.call('project.open', {path:folder,model,preview:true});
    const key=contextKey(result.project_id,result.session_id);
    if(!sessionSelections.has(key))sessionSelections.set(key,metadata);
    await bindWorkspace(result);
    usedModel(sessionSelections.get(key)?.connection_id);
    connections.opened(result.project);
    rememberOpenProject(result.project);
    return decorate(result);
  } finally {opening = false;}
}
const allowed = new Set(['snapshot', 'live', 'permissions.set', 'mode.set', 'goal.set', 'project.close', 'session.switch', 'session.messages', 'session.message', 'sessions.name-missing', 'session.regenerate', 'queue.add', 'queue.update', 'queue.move', 'queue.priority', 'queue.send-now', 'queue.remove', 'subagent.snapshot', 'task.start', 'task.cancel', 'input.reply', 'changes.diff', 'changes.accept', 'changes.undo', 'diagnostics']);
function trusted(event: Electron.IpcMainInvokeEvent) {
  try {return event.sender === window.webContents && event.senderFrame === window.webContents.mainFrame && path.resolve(fileURLToPath(event.senderFrame.url)) === html;}
  catch {return false;}
}
async function action(method: string, params: any = {}) {
  if(typeof method!=='string'||!params||typeof params!=='object'||Array.isArray(params))throw new Error('无效的桌面请求');
  // Capture project identity before the first await. Stale view requests must
  // never be reinterpreted against the project the user just switched to.
  if(params.owner&&!method.startsWith('browser.')&&!method.startsWith('terminal.')&&!method.startsWith('workspace.')){
    if(params.owner!==workspaceOwner)throw new Error('项目会话已变化，请重新打开工作区');
    params={...params,owner:activeSession,project_id:activeProject,session_id:activeSession};
  }
  params={project_id:activeProject,...params};
  if(method.startsWith('browser.')||method.startsWith('terminal.')||method==='workspace.snapshot'||method==='workspace.occluded') {
    if(opening)throw new Error('项目正在切换');
    if(params.owner!==workspaceOwner||!workspaceOwner)throw new Error('项目会话已变化，请重新打开工作区');
    if(method==='workspace.snapshot')return {browsers:browsers.snapshot(),terminals:terminals.list()};
    if(method==='workspace.occluded'){occluded=params.value===true;if(occluded)browsers.hide();return true;}
    if(method==='browser.bounds'&&occluded)return false;
    return method.startsWith('browser.')?browsers.action(method,params):terminals.action(method,params);
  }
  if(method==='project.close'&&[...workspaces.values()].some(w=>w.project===params.project_id&&w.terminals.list().some(t=>t.status!=='exited'))) {
    browsers.hide();
    const choice=await dialog.showMessageBox(window,{type:'question',message:'关闭项目会停止其中的终端。',buttons:['保留项目','停止终端并关闭'],defaultId:0,cancelId:0});
    if(choice.response===0)throw new Error('已保留当前会话和终端。');
  }
  if(['sidechat.open','sidechat.snapshot','sidechat.context','sidechat.send','sidechat.cancel','sidechat.model','sidechat.reasoning'].includes(method)) {
    if(method==='sidechat.model') {
      const {model,connection_id}=connections.selection(params.choice||'default');
      const result=await (await backend()).call(method,{id:params.id,session_id:params.session_id,project_id:params.project_id,model,connection_id});
      usedModel(connection_id);return result;
    }
    const result=await (await backend()).call(method,method==='sidechat.open'?{...params,connection_id:sessionSelections.get(contextKey(params.project_id,params.session_id))?.connection_id}:params);
    if(method==='sidechat.send')usedModel(result.connection_id);
    return result;
  }
  if((selecting||opening)&&['config.save','config.default','config.remove','model.use','project.pick','project.recent','project.close','session.switch','task.start'].includes(method)) throw new Error('项目或模型正在切换，请稍候。');
  if (method === 'config.get') return publicConfig();
  if (method === 'personalization.get') return readPersonalization();
  if (method === 'personalization.save') return savePersonalization(params);
  if (method === 'config.save') {const saved=connections.save(params);return {...await publicConfig(),savedId:saved.savedId,warning:saved.warning};}
  if (method === 'config.default') {connections.setDefault(params.id);usedModel(params.id);return publicConfig();}
  if (method === 'config.reasoning') {
    const model=connections.public().connections.find(c=>c.id===params.id);
    if(!model)throw new Error('模型连接不存在。');
    const [capability]=await (await backend()).call('model.capabilities',{models:[model]});
    if(!capability.options.includes(params.effort))throw new Error('此模型不支持所选推理强度。');
    connections.setEffort(params.id,params.effort);publish('eca:changed',{event:'config'});return publicConfig();
  }
  if (method === 'model.reasoning') {
    if(selecting||opening)throw new Error('项目或模型正在切换，请稍候。');
    selecting=true;
    try{return decorate(await (await backend()).call(method,{effort:params.effort,session_id:params.session_id,project_id:params.project_id}));}
    finally{selecting=false;}
  }
  if (method === 'config.remove') {
    if([...sessionSelections.values()].some(s=>s.connection_id===params.id)) throw new Error('已打开的会话正在使用此连接，请先切换模型或关闭项目。');
    connections.remove(params.id);return publicConfig();
  }
  if (method === 'config.check' || method === 'config.models') {
    const resolved=params.draft ? connections.resolve(params.draft,method==='config.check') : connections.runtime(params.id||connections.public().defaultId!);
    const {model,base_url,api_format,api_key,thinking_mode}=resolved;
    const reasoning_effort='reasoning_effort' in resolved?resolved.reasoning_effort:'';
    return (await backend()).call(method==='config.check'?'connection.check':'connection.models',
      {model:{model:model||'catalogue',base_url,api_format,api_key,thinking_mode,reasoning_effort},root:home});
  }
  if (method === 'model.use') {
    selecting=true;
    try {
      const client=await backend();
      const before=await client.call('live');
      if(!before.project) throw new Error('请先打开项目。');
      const {model,...metadata}=connections.selection(params.choice||'default');
      const result=await client.call('model.select',{model,preview:true,session_id:params.session_id||before.session_id,project_id:params.project_id});
      const key=contextKey(result.project_id,result.session_id);
      sessionSelections.set(key,metadata);
      if(key===workspaceOwner)activeSelection=metadata;
      connections.remember(result.project,metadata.choice);
      usedModel(metadata.connection_id);
      return decorate(result);
    } finally {selecting=false;}
  }
  if (method === 'project.pick') {
    browsers.hide();
    const result = await dialog.showOpenDialog(window, {properties: ['openDirectory'], title: '选择项目文件夹'});
    return result.canceled ? null : openProject(result.filePaths[0]);
  }
  if (method === 'project.recent') {
    if (!Number.isInteger(params.index) || !connections.public().recent[params.index]) throw new Error('项目不存在。');
    return openProject(connections.public().recent[params.index]);
  }
  if (method === 'link.open') {
    const url = new URL(params.url);
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('仅支持 HTTP(S) 链接。');
    await shell.openExternal(url.toString()); return true;
  }
  if (!allowed.has(method)) throw new Error('不支持的桌面操作。');
  const switching=method==='session.switch'||method==='project.close';
  if(switching)opening=true;
  try {
    const prior=switching?await (await backend()).call('live'):null;
    const result=await (await backend()).call(method, params);
    if(method==='task.start')usedModel(sessionSelections.get(contextKey(params.project_id,result.session_id))?.connection_id);
    if(switching){
      const key=contextKey(result.project_id,result.session_id);
      const source=prior?.projects?.find((p:any)=>p.id===result.project_id);
      const inherited=source&&sessionSelections.get(contextKey(source.id,source.session_id));
      if(result.session_id&&!sessionSelections.has(key)&&inherited)sessionSelections.set(key,inherited);
      if(method==='project.close'){
        const closed=prior?.projects?.find((p:any)=>p.id===params.project_id)?.path;
        if(closed)rememberOpenProject(closed,true);
        await closeWorkspaces(params.project_id);
      }
      await bindWorkspace(result);
    }
    return decorate(result);
  } finally {if(switching)opening=false;}
}
async function closeWindow() {
  if (closing || quitting) return;
  closing = true;
  try {
    let busy = false;
    if (rpc && !rpc.exited) {
      try {const live=await rpc.call('live');busy = live.any_busy||live.busy||live.side_busy;} catch {busy = true;}
    }
    if (busy||[...workspaces.values()].some(w=>w.terminals.list().some(t=>t.status!=='exited'))) {
      browsers.hide();
      const choice = await dialog.showMessageBox(window, {type: 'question', title: '任务仍在运行', message: '退出前需要停止所有项目、所有会话中的任务、侧聊和终端。已完成的修改会保留。', buttons: ['继续运行并留在窗口', '停止并退出'], defaultId: 0, cancelId: 0});
      if (choice.response === 0) return;
    }
    if (rpc && !await rpc.close()) {
      const choice = await dialog.showMessageBox(window, {type: 'warning', message: '清理尚未完成。强制结束后，下次恢复需检查未完成操作。', buttons: ['继续等待', '强制结束并退出'], defaultId: 0, cancelId: 0});
      if (choice.response === 0) return;
      await rpc.forceClose();
    }
    await closeWorkspaces();quitting = true; app.quit();
  } finally {closing = false;}
}
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => {window?.show(); window?.focus();});
  app.whenReady().then(() => {
    const area = screen.getPrimaryDisplay().workAreaSize;
    const width = Math.min(1360, area.width - 32);
    const height = Math.min(860, area.height - 32);
    window = new BrowserWindow({width, height, minWidth: Math.min(800, width), minHeight: Math.min(560, height), center: true, title: 'ECA Desktop', frame: false, backgroundColor: '#18191c', autoHideMenuBar: true, show: process.env.ECA_DESKTOP_TEST_HIDDEN !== '1',
      webPreferences: {preload: path.join(__dirname, '../preload/index.cjs'), contextIsolation: true, sandbox: true, nodeIntegration: false}});
    window.webContents.setWindowOpenHandler(() => ({action: 'deny'}));
    browsers=new BrowserManager(window);terminals=new TerminalManager();
    window.webContents.on('will-navigate', event => event.preventDefault());
    window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    ipcMain.handle('eca:invoke', async (event, method, params) => {
      if (!trusted(event)) return {ok: false, error: 'Untrusted window'};
      try {return {ok: true, value: await action(method, params)};}
      catch (error) {return {ok: false, error: error instanceof Error ? error.message : '操作失败'};}
    });
    ipcMain.handle('eca:theme', async (event, payload) => {
      if (!trusted(event)) return nativeTheme.themeSource;
      if (payload?.action === 'set') {
        const next = payload?.source;
        if (!themeSources.includes(next)) return nativeTheme.themeSource;
        nativeTheme.themeSource = next;
        writeTheme(next);
        publish('eca:theme', next);
      }
      return nativeTheme.themeSource;
    });
    // The window has no native frame, so the renderer draws the title bar and
    // asks for these three actions. Close keeps the existing task confirmation.
    ipcMain.handle('eca:window', async (event, action) => {
      if (!trusted(event) || !window) return false;
      if (action === 'minimize') window.minimize();
      else if (action === 'maximize') {window.isMaximized() ? window.unmaximize() : window.maximize();}
      else if (action === 'close') {void closeWindow();}
      else return false;
      return window.isMaximized();
    });
    window.on('maximize', () => publish('eca:maximized', true));
    window.on('unmaximize', () => publish('eca:maximized', false));
    // Copy stays in the desktop process: the renderer keeps no clipboard, shell
    // or filesystem access of its own.
    ipcMain.handle('eca:copy', async (event, text) => {
      if (!trusted(event)) return false;
      const value = typeof text === 'string' ? text : '';
      if (!value || value.length > 1_000_000) return false;
      clipboard.writeText(value);
      return true;
    });
    window.on('close', event => {if (!quitting) {event.preventDefault(); void closeWindow();}});
    void window.loadFile(html);
    // Come back to the projects that were open last time, in the same order, so the
    // sidebar shows the project/session tree instead of a bare recent-folder list.
    window.webContents.once('did-finish-load', () => {
      const saved = readOpenProjects();
      if (!saved.length) return;
      void (async () => {
        for (const folder of [...saved].reverse()) {
          if (!fs.existsSync(folder)) continue;
          try { await openProject(folder); } catch { /* keep going; skip a locked or missing project */ }
        }
        publish('eca:changed', {event: 'project'});
      })();
    });
  });
  app.on('before-quit', event => {if (!quitting && window && !window.isDestroyed()) {event.preventDefault(); void closeWindow();}});
  app.on('window-all-closed', () => app.quit());
}
