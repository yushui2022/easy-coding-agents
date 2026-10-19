import {BrowserWindow, WebContentsView, session, net, dialog} from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash, randomUUID} from 'node:crypto';

export class BrowserManager {
  tabs = new Map<string,{view:WebContentsView; error:string}>();
  root = '';
  partition = '';
  constructor(private window:BrowserWindow) {}
  async bind(root:string) {
    this.closeAll(); this.root=root;
    this.partition='persist:eca-preview-'+createHash('sha256').update(root).digest('hex').slice(0,20);
    const ses=session.fromPartition(this.partition);
    ses.setPermissionRequestHandler((_w,_p,cb)=>cb(false));
    ses.setPermissionCheckHandler(()=>false);
    ses.removeAllListeners('will-download');
    ses.on('will-download',(event)=>event.preventDefault());
    if(ses.protocol.isProtocolHandled && await ses.protocol.isProtocolHandled('eca-preview')) ses.protocol.unhandle('eca-preview');
    const base=fs.realpathSync(root);
    ses.protocol.handle('eca-preview',async request=>{
      try {
        const url=new URL(request.url);
        if(url.hostname!=='project'||!['GET','HEAD'].includes(request.method))return new Response('Forbidden',{status:403});
        const relative=decodeURIComponent(url.pathname).replace(/^[/\\]+/,'');
        const file=fs.realpathSync(path.resolve(base,relative));
        const within=path.relative(base,file);
        if(!within||within.startsWith('..')||path.isAbsolute(within)||within.split(/[/\\]/).some(x=>x.startsWith('.'))||
          !/\.(html?|css|m?js|json|png|jpe?g|gif|webp|svg|ico|woff2?|ttf|wasm|mp4|webm|mp3|wav)$/i.test(file)) return new Response('Forbidden',{status:403});
        return net.fetch(pathToFileURL(file).href);
      } catch {return new Response('File not found',{status:404});}
    });
  }
  normalize(value:unknown) {
    if(typeof value!=='string'||value.length>8192)throw new Error('请输入网页地址');
    const url=new URL(value.includes('://')?value:(/^(localhost|127\.0\.0\.1|\[::1\])(?::|\/|$)/.test(value)?'http://':'https://')+value);
    if(!['https:','http:','eca-preview:'].includes(url.protocol)||url.username||url.password)throw new Error('仅支持网页或项目预览地址');
    if(url.protocol==='eca-preview:'&&url.hostname!=='project')throw new Error('无效的项目预览');
    return url.href;
  }
  get(id:string) {const tab=this.tabs.get(id); if(!tab)throw new Error('浏览器标签已关闭');return tab;}
  snapshot() {return [...this.tabs].map(([id,t])=>({id,url:t.view.webContents.getURL(),title:t.view.webContents.getTitle()||'浏览器',error:t.error,
    loading:t.view.webContents.isLoading(),back:t.view.webContents.navigationHistory.canGoBack(),forward:t.view.webContents.navigationHistory.canGoForward()}));}
  hide() {for(const t of this.tabs.values())t.view.setVisible(false);}
  close(id:string) {const t=this.get(id);this.window.contentView.removeChildView(t.view);t.view.webContents.close({waitForBeforeUnload:false});this.tabs.delete(id);}
  closeAll() {for(const id of [...this.tabs.keys()])this.close(id);}
  async action(method:string,p:any) {
    if(method==='browser.list')return this.snapshot();
    if(method==='browser.hide'){this.hide();return true;}
    if(!this.root)throw new Error('请先打开项目');
    if(method==='browser.create') {
      if(this.tabs.size>=6)throw new Error('请先关闭不用的浏览器标签（最多 6 个）');
      const view=new WebContentsView({webPreferences:{partition:this.partition,nodeIntegration:false,contextIsolation:true,sandbox:true}});
      const id=randomUUID(),tab={view,error:''};this.tabs.set(id,tab);
      this.window.contentView.addChildView(view);view.setVisible(false);
      view.webContents.setWindowOpenHandler(()=>({action:'deny'}));
      view.webContents.on('will-navigate',(event,url)=>{try{this.normalize(url);}catch{event.preventDefault();}});
      view.webContents.on('will-redirect',(event,url)=>{try{this.normalize(url);}catch{event.preventDefault();}});
      view.webContents.on('did-fail-load',(_e,code,description,_url,main)=>{if(main&&code!==-3)tab.error=description;});
      view.webContents.on('did-start-loading',()=>{tab.error='';});
      view.webContents.on('render-process-gone',()=>{tab.error='页面进程已退出，可重新加载';});
      if(p.url)void view.webContents.loadURL(this.normalize(p.url)).catch(e=>{tab.error=e.message;});
      return {id};
    }
    if(method==='browser.pick') {
      this.hide();
      const result=await dialog.showOpenDialog(this.window,{title:'预览项目 HTML',defaultPath:this.root,properties:['openFile'],filters:[{name:'HTML',extensions:['html','htm']}]});
      if(result.canceled)return null;
      const relative=path.relative(fs.realpathSync(this.root),fs.realpathSync(result.filePaths[0]));
      if(relative.startsWith('..')||path.isAbsolute(relative))throw new Error('请选择当前项目中的 HTML');
      return {url:'eca-preview://project/'+relative.split(path.sep).map(encodeURIComponent).join('/')};
    }
    const t=this.get(p.id),wc=t.view.webContents;
    if(method==='browser.bounds') {
      this.hide();
      const b=p.bounds, size=this.window.getContentSize();
      if(!b||!['x','y','width','height'].every(k=>Number.isFinite(b[k])))throw new Error('无效的浏览器区域');
      const x=Math.max(0,Math.round(b.x)),y=Math.max(0,Math.round(b.y));
      t.view.setBounds({x,y,width:Math.max(0,Math.min(Math.round(b.width),size[0]-x)),height:Math.max(0,Math.min(Math.round(b.height),size[1]-y))});
      t.view.setVisible(b.width>0&&b.height>0);return true;
    }
    if(method==='browser.navigate'){void wc.loadURL(this.normalize(p.url)).catch(e=>{t.error=e.message;});return true;}
    if(method==='browser.back'){if(wc.navigationHistory.canGoBack())wc.navigationHistory.goBack();return true;}
    if(method==='browser.forward'){if(wc.navigationHistory.canGoForward())wc.navigationHistory.goForward();return true;}
    if(method==='browser.reload'){wc.reload();return true;}
    if(method==='browser.close'){this.close(p.id);return true;}
    if(method==='browser.quote')return {url:wc.getURL(),title:wc.getTitle(),captured_at:Date.now(),text:await wc.executeJavaScript('String(window.getSelection()?.toString() || document.body?.innerText || "").slice(0,12000)',false)};
    throw new Error('不支持的浏览器操作');
  }
}
