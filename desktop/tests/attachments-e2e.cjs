// Isolated hidden app, local model fixture; no user credentials or projects.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents',home=fs.mkdtempSync(path.join(base,'attachments-'));
const project=path.join(home,'中文 项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/attachments');fs.mkdirSync(output,{recursive:true});
const mode=process.env.ECA_TEST_MODE||'development',requests=[],errors=[];
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j1ioAAAAASUVORK5CYII=','base64');
const server=http.createServer(async(req,res)=>{
  let raw='';for await(const c of req)raw+=c;requests.push(JSON.parse(raw));
  if(requests.length===3){res.writeHead(400,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'image not supported',type:'invalid_request_error'}}));return;}
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  res.end('data: '+JSON.stringify({id:'fixture',choices:[{index:0,delta:{content:'附件已收到'},finish_reason:'stop'}]})+'\n\ndata: [DONE]\n\n');
});
let app;
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const env={...process.env};
  for(const k of Object.keys(env))if(k.startsWith('ECA_')||/API_KEY|API_BASE|BASE_URL|MODEL_NAME|PYTHONHOME|PYTHONPATH/.test(k))delete env[k];
  Object.assign(env,{TEMP:base,TMP:base,ECA_DESKTOP_TEST_HIDDEN:'1',ECA_DESKTOP_DATA_HOME:path.join(home,'data'),
    ECA_PYTHON:path.resolve('.venv/Scripts/python.exe'),PYTHONUTF8:'1',NO_PROXY:'localhost,127.0.0.1'});
  delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch(process.env.ECA_TEST_EXE?{executablePath:process.env.ECA_TEST_EXE,args:[],env}:{args:['.'],env});
  const page=await app.firstWindow();page.on('pageerror',e=>errors.push(String(e)));
  const invoke=(m,p={})=>page.evaluate(([m,p])=>window.eca.invoke(m,p),[m,p]);
  await app.evaluate(({BrowserWindow,dialog},project)=>{
    BrowserWindow.getAllWindows()[0].setContentSize(1360,900);
    BrowserWindow.getAllWindows()[0].webContents.setBackgroundThrottling(false);
    dialog.showOpenDialog=async()=>({canceled:false,filePaths:[project]});
  },project);
  const saved=await invoke('config.save',{name:'视觉测试',api_format:'openai',model:'fixture-vision',base_url:`http://127.0.0.1:${server.address().port}/v1`,no_auth:true});
  await invoke('config.default',{id:saved.savedId});
  await page.getByRole('button',{name:'打开项目',exact:true}).click();
  await expect.poll(async()=>(await invoke('snapshot')).project).toBe(project);
  const a=await invoke('snapshot');
  const main=page.locator('.composer');
  await expect(main.getByRole('button',{name:'添加文件或图片'})).toBeEnabled();
  await main.getByLabel('选择附件').setInputFiles([{name:'参考.png',mimeType:'image/png',buffer:png},{name:'需求.md',mimeType:'text/plain',buffer:Buffer.from('真实附件内容：陶土工作区')}]);
  await expect(main.locator('.attachment-chip')).toHaveCount(2);
  await page.reload();
  await expect(main.locator('.attachment-chip')).toHaveCount(2);
  await invoke('session.switch',{});await page.reload();
  await expect(main.locator('.attachment-chip')).toHaveCount(0);
  await invoke('session.switch',{id:a.session_id});await page.reload();
  await expect(main.locator('.attachment-chip')).toHaveCount(2);
  await page.getByLabel('任务指令').fill('参考附件设计');
  await page.getByRole('button',{name:'发送任务',exact:true}).click();
  await expect.poll(()=>requests.length).toBe(1);
  await expect.poll(async()=>(await invoke('snapshot')).busy).toBe(false);
  const message=requests[0].messages.find(m=>m.role==='user'&&Array.isArray(m.content));
  assert(message.content[0].text.includes('真实附件内容：陶土工作区'));
  assert.equal(message.content[1].image_url.url,'data:image/png;base64,'+png.toString('base64'));
  await expect(main.locator('.attachment-chip')).toHaveCount(0);
  await expect(page.locator('.sent-attachments')).toContainText('参考.png');
  await page.getByRole('button',{name:'打开侧边聊天',exact:true}).click();
  const side=page.locator('.side-chat');
  await expect(side.getByRole('button',{name:'添加文件或图片'})).toBeEnabled();
  // Paste a real clipboard File through the same DOM event consumed by the composer.
  await side.locator('textarea').evaluate((el,b64)=>{
    const dt=new DataTransfer();dt.items.add(new File([Uint8Array.from(atob(b64),c=>c.charCodeAt(0))],'截图.png',{type:'image/png'}));
    el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
  },png.toString('base64'));
  await expect(side.locator('.attachment-chip')).toHaveCount(1);
  await side.getByRole('button',{name:'发送',exact:true}).click();
  await expect.poll(()=>requests.length).toBe(2);
  await expect(side.locator('.sent-attachments')).toContainText('截图.png');
  assert(requests[1].messages.some(m=>Array.isArray(m.content)&&m.content.some(b=>b.type==='image_url')));
  await expect(side.getByRole('button',{name:'添加文件或图片'})).toBeEnabled();
  await side.getByLabel('选择附件').setInputFiles({name:'文档.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF')});
  await expect(side.getByRole('alert')).toContainText('暂不支持');
  await expect(side.locator('.attachment-chip')).toHaveCount(0);
  // Drop and remove, then send to a service explicitly rejecting vision.
  await main.evaluate((el,b64)=>{
    const dt=new DataTransfer();dt.items.add(new File([Uint8Array.from(atob(b64),c=>c.charCodeAt(0))],'拖入.png',{type:'image/png'}));
    el.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}));
  },png.toString('base64'));
  await expect(main.locator('.attachment-chip')).toHaveCount(1);
  await main.getByRole('button',{name:'移除 拖入.png'}).click();
  await expect(main.locator('.attachment-chip')).toHaveCount(0);
  await main.getByLabel('选择附件').setInputFiles({name:'不支持.png',mimeType:'image/png',buffer:png});
  await expect(main.locator('.attachment-chip')).toHaveCount(1);
  await page.getByRole('button',{name:'发送任务',exact:true}).click();
  await expect.poll(()=>requests.length).toBe(3);
  await expect.poll(async()=>(await invoke('snapshot')).busy).toBe(false);
  await expect(page.getByText(/模型服务拒绝了含图片的请求/).first()).toBeVisible();
  // Review is opened on demand; it no longer crowds the initial workspace.
  await page.getByRole('button',{name:'审查',exact:true}).click();
  await expect(page.getByRole('tab',{name:'检查结果'})).toBeVisible();
  await expect(page.getByRole('tab',{name:'进度',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'关闭错误'}).click();
  await main.getByLabel('选择附件').setInputFiles({name:'设计参考.png',mimeType:'image/png',buffer:png});
  await page.locator('.workspace-tabs').getByRole('button',{name:'侧边聊天',exact:true}).click();
  await side.getByLabel('选择附件').setInputFiles({name:'代码.py',mimeType:'text/plain',buffer:Buffer.from('print(42)')});
  await expect(side.locator('.attachment-chip')).toHaveCount(1);
  for(const theme of ['light','dark']){
    await page.emulateMedia({colorScheme:theme});
    await page.waitForFunction(t=>matchMedia('(prefers-color-scheme: dark)').matches===(t==='dark'),theme);
    await app.evaluate(({nativeTheme},theme)=>{nativeTheme.themeSource=theme;},theme);
    const image=await app.evaluate(async({BrowserWindow})=>{
      const wc=BrowserWindow.getAllWindows()[0].webContents;
      await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});await new Promise(r=>setTimeout(r,220));
      return (await wc.capturePage(undefined,{stayHidden:true,stayAwake:true})).toPNG().toString('base64');
    });
    fs.writeFileSync(path.join(output,`${mode}-${theme}.png`),Buffer.from(image,'base64'));
  }
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(960,720));
  await page.waitForFunction(()=>innerWidth<1180);
  await expect(side.getByRole('button',{name:'发送',exact:true})).toBeVisible();
  let box=await side.getByRole('button',{name:'发送',exact:true}).boundingBox();
  assert(box.y+box.height<=await page.evaluate(()=>innerHeight));
  await page.getByRole('button',{name:'收起任务详情',exact:true}).click();
  await expect(page.getByRole('button',{name:'发送任务',exact:true})).toBeVisible();
  box=await page.getByRole('button',{name:'发送任务',exact:true}).boundingBox();
  assert(box.y+box.height<=await page.evaluate(()=>innerHeight));
  assert.deepEqual(errors,[]);
  const report={mode,version:await app.evaluate(({app})=>app.getVersion()),requests:requests.length,paid_api_calls:0,
    checks:['main text and image payload','side chat image payload','draft reload','session isolation','image-only send','paste','drop','remove','unsupported format','vision service rejection','on-demand review','light/dark','narrow composer controls'],renderer_errors:errors};
  fs.writeFileSync(path.join(output,`${mode}.json`),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{
  if(app){await app.evaluate(({dialog})=>{dialog.showMessageBox=async()=>({response:1});}).catch(()=>{});await app.close().catch(()=>{});}
  server.closeAllConnections();server.close();
});
