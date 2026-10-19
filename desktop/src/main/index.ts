import { app, BrowserWindow, ipcMain, dialog, safeStorage, shell, screen, protocol } from 'electron';
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
let occluded=false;
let sideNotification:ReturnType<typeof setTimeout>|undefined;

const home = process.env.ECA_DESKTOP_DATA_HOME || (process.platform === 'win32' && fs.existsSync('G:\\') ? 'G:\\Data\\ECA\\Desktop' : app.getPath('userData'));
fs.mkdirSync(home, {recursive: true});
app.setPath('userData', home);
const cacheHome = process.env.ECA_DESKTOP_CACHE_HOME || (!process.env.ECA_DESKTOP_DATA_HOME && fs.existsSync('G:/') ? 'G:/DevCache/eca-desktop' : path.join(home, 'cache'));
fs.mkdirSync(cacheHome, {recursive: true});
app.setPath('sessionData', cacheHome);
const tempHome = path.join(cacheHome, 'temp');
fs.mkdirSync(tempHome, {recursive: true});
app.setPath('temp', tempHome);
process.env.TEMP = tempHome;
process.env.TMP = tempHome;
const root = path.resolve(__dirname, '../../..');
const html = path.resolve(__dirname, '../renderer/index.html');
const connections = new Connections(path.join(home, 'preferences.json'), safeStorage);
let activeSelection: {choice:string; connection_id:string|null; name:string}|undefined;
let selecting = false;
let window: BrowserWindow;
let rpc: RpcClient | undefined;
let starting: Promise<RpcClient> | undefined;
let quitting = false;
let closing = false;
let opening = false;
let liveNotification: ReturnType<typeof setTimeout>|undefined;
const publish = (channel: string, data?: unknown) => {if (window && !window.isDestroyed()) window.webContents.send(channel, data);};
function publicConfig() {return {...connections.public(), dataHome:home, version:app.getVersion()};}
function decorate(value:any) {
  return value?.project ? {...value,model_selection:activeSelection} : value;
}
async function backend() {
  if (starting) return starting;
  if (rpc && !rpc.exited) return rpc;
  const command = app.isPackaged ? path.join(process.resourcesPath, 'backend', 'eca-backend.exe') : (process.env.ECA_PYTHON || 'python');
  rpc = new RpcClient(command, app.isPackaged ? [] : ['-B', '-m', 'eca.desktop_rpc'], app.isPackaged ? home : root);
  rpc.on('event', data => {
    if(data.event==='sidechat') {
      if(!sideNotification)sideNotification=setTimeout(()=>{sideNotification=undefined;publish('eca:changed',{event:'sidechat'});},80);
      return;
    }
    if(data.event==='text'||data.event==='model_activity') {
      if(!liveNotification)liveNotification=setTimeout(()=>{liveNotification=undefined;publish('eca:changed',{event:'text'});},80);
    } else {clearTimeout(liveNotification);liveNotification=undefined;publish('eca:changed', {event:data.event});}
  });
  rpc.on('failure', message => {clearTimeout(liveNotification);liveNotification=undefined;publish('eca:failure', message);});
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
    await terminals.closeAll();terminals.root=result.project;await browsers.bind(result.project);workspaceOwner=result.session_id;
    activeSelection=metadata;
    connections.opened(result.project);
    return decorate(result);
  } finally {opening = false;}
}
const allowed = new Set(['snapshot', 'live', 'permissions.set', 'project.close', 'session.switch', 'session.messages', 'session.message', 'task.start', 'task.cancel', 'input.reply', 'changes.diff', 'changes.accept', 'changes.undo', 'diagnostics']);
function trusted(event: Electron.IpcMainInvokeEvent) {
  try {return event.sender === window.webContents && event.senderFrame === window.webContents.mainFrame && path.resolve(fileURLToPath(event.senderFrame.url)) === html;}
  catch {return false;}
}
async function action(method: string, params: any = {}) {
  if(typeof method!=='string'||!params||typeof params!=='object'||Array.isArray(params))throw new Error('无效的桌面请求');
  if(method.startsWith('browser.')||method.startsWith('terminal.')||method==='workspace.snapshot'||method==='workspace.occluded') {
    if(opening)throw new Error('项目正在切换');
    if(params.owner!==workspaceOwner||!workspaceOwner)throw new Error('项目会话已变化，请重新打开工作区');
    if(method==='workspace.snapshot')return {browsers:browsers.snapshot(),terminals:terminals.list()};
    if(method==='workspace.occluded'){occluded=params.value===true;if(occluded)browsers.hide();return true;}
    if(method==='browser.bounds'&&occluded)return false;
    return method.startsWith('browser.')?browsers.action(method,params):terminals.action(method,params);
  }
  if(['project.pick','project.recent','project.close','session.switch'].includes(method)&&terminals.list().some(t=>t.status!=='exited')) {
    const live=await (await backend()).call('live');
    if(live.busy||live.side_busy)throw new Error('请先等待当前任务和侧聊完成。');
    browsers.hide();
    const choice=await dialog.showMessageBox(window,{type:'question',message:'切换项目或会话会关闭当前工作区，并停止其中的终端。',buttons:['留在当前会话','停止终端并切换'],defaultId:0,cancelId:0});
    if(choice.response===0)throw new Error('已保留当前会话和终端。');
  }
  if(['sidechat.open','sidechat.snapshot','sidechat.context','sidechat.send','sidechat.cancel','sidechat.model'].includes(method)) {
    if(method==='sidechat.model') {
      const {model}=connections.selection(params.choice||'default');
      return (await backend()).call(method,{id:params.id,session_id:params.session_id,model});
    }
    return (await backend()).call(method,params);
  }
  if((selecting||opening)&&['config.save','config.default','config.remove','model.use','project.pick','project.recent','project.close','session.switch','task.start'].includes(method)) throw new Error('项目或模型正在切换，请稍候。');
  if (method === 'config.get') return publicConfig();
  if (method === 'config.save') return {...connections.save(params),dataHome:home,version:app.getVersion()};
  if (method === 'config.default') return {...connections.setDefault(params.id),dataHome:home,version:app.getVersion()};
  if (method === 'config.remove') {
    if(activeSelection?.connection_id===params.id) throw new Error('当前会话正在使用此连接，请先切换模型。');
    return {...connections.remove(params.id),dataHome:home,version:app.getVersion()};
  }
  if (method === 'config.check' || method === 'config.models') {
    const resolved=params.draft ? connections.resolve(params.draft,method==='config.check') : connections.runtime(params.id||connections.public().defaultId!);
    const {model,base_url,api_format,api_key,thinking_mode}=resolved;
    return (await backend()).call(method==='config.check'?'connection.check':'connection.models',
      {model:{model:model||'catalogue',base_url,api_format,api_key,thinking_mode},root:home});
  }
  if (method === 'model.use') {
    selecting=true;
    try {
      const client=await backend();
      const before=await client.call('live');
      if(!before.project) throw new Error('请先打开项目。');
      const {model,...metadata}=connections.selection(params.choice||'default');
      const result=await client.call('model.select',{model,preview:true});
      activeSelection=metadata;
      connections.remember(before.project,metadata.choice);
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
  const result=await (await backend()).call(method, params);
  if(method==='session.switch'||method==='project.close'){
    await terminals.closeAll();browsers.closeAll();workspaceOwner=result.session_id||'';
    if(result.project){terminals.root=result.project;await browsers.bind(result.project);}else terminals.root='';
  }
  if(method==='project.close') activeSelection=undefined;
  return decorate(result);
}
async function closeWindow() {
  if (closing || quitting) return;
  closing = true;
  try {
    let busy = false;
    if (rpc && !rpc.exited) {
      try {const live=await rpc.call('live');busy = live.busy||live.side_busy;} catch {busy = true;}
    }
    if (busy||terminals.list().some(t=>t.status!=='exited')) {
      browsers.hide();
      const choice = await dialog.showMessageBox(window, {type: 'question', title: '任务仍在运行', message: '退出前需要停止当前任务。已完成的修改会保留。', buttons: ['继续运行并留在窗口', '停止并退出'], defaultId: 0, cancelId: 0});
      if (choice.response === 0) return;
    }
    if (rpc && !await rpc.close()) {
      const choice = await dialog.showMessageBox(window, {type: 'warning', message: '清理尚未完成。强制结束后，下次恢复需检查未完成操作。', buttons: ['继续等待', '强制结束并退出'], defaultId: 0, cancelId: 0});
      if (choice.response === 0) return;
      await rpc.forceClose();
    }
    await terminals.closeAll();browsers.closeAll();quitting = true; app.quit();
  } finally {closing = false;}
}
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => {window?.show(); window?.focus();});
  app.whenReady().then(() => {
    const area = screen.getPrimaryDisplay().workAreaSize;
    const width = Math.min(1360, area.width - 32);
    const height = Math.min(860, area.height - 32);
    window = new BrowserWindow({width, height, minWidth: Math.min(800, width), minHeight: Math.min(560, height), center: true, title: 'ECA Desktop', backgroundColor: '#18191c', autoHideMenuBar: true, show: process.env.ECA_DESKTOP_TEST_HIDDEN !== '1',
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
    window.on('close', event => {if (!quitting) {event.preventDefault(); void closeWindow();}});
    void window.loadFile(html);
  });
  app.on('before-quit', event => {if (!quitting && window && !window.isDestroyed()) {event.preventDefault(); void closeWindow();}});
  app.on('window-all-closed', () => app.quit());
}
