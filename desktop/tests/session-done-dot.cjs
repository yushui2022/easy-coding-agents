// Hidden owned Electron window, local SSE fixture only. Never touches user data.
// Proves the sidebar shows a green "finished" dot after a run ends, that the dot
// is absent while running and on sessions that never ran, and that opening the
// session clears it.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents';
fs.mkdirSync(base,{recursive:true});
const home=fs.mkdtempSync(path.join(base,'done-dot-'));
const project=path.join(home,'完成点 项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/done-dot');fs.mkdirSync(output,{recursive:true});
const mode=process.env.ECA_TEST_MODE||(process.env.ECA_TEST_EXE?'packaged':'development');
const exchanges=[],sockets=new Set(),errors=[];
const server=http.createServer(async(req,res)=>{
  let text='';for await(const chunk of req)text+=chunk;
  exchanges.push({res,body:JSON.parse(text)});
});
server.on('connection',s=>{sockets.add(s);s.on('close',()=>sockets.delete(s));});
const start=res=>res.writeHead(200,{'Content-Type':'text/event-stream'});
const delta=(res,value,finish=null)=>res.write('data: '+JSON.stringify({id:'local',object:'chat.completion.chunk',created:0,
  model:'fixture',choices:[{index:0,delta:value,finish_reason:finish}]})+'\n\n');
const end=res=>{delta(res,{},'stop');res.end('data: [DONE]\n\n');};
let app;
async function capture(name) {
  const png=await app.evaluate(async({BrowserWindow})=>{
    const wc=BrowserWindow.getAllWindows()[0].webContents;
    await wc.executeJavaScript('Promise.all([document.fonts.ready,...Array.from(document.images).map(i=>i.decode().catch(()=>{}))])');
    await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});
    await new Promise(r=>setTimeout(r,200));
    return (await wc.capturePage(undefined,{stayHidden:true,stayAwake:true})).toPNG().toString('base64');
  });
  fs.writeFileSync(path.join(output,`${name}-${mode}.png`),Buffer.from(png,'base64'));
}
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const env={...process.env};
  for(const name of Object.keys(env))if(name.startsWith('ECA_')||/API_KEY|API_BASE|BASE_URL|MODEL_NAME|PYTHONHOME|PYTHONPATH/.test(name))delete env[name];
  Object.assign(env,{TEMP:base,TMP:base,ECA_DESKTOP_TEST_HIDDEN:'1',ECA_DESKTOP_DATA_HOME:path.join(home,'app'),
    ECA_PYTHON:path.resolve('.venv/Scripts/python.exe'),NO_PROXY:'127.0.0.1,localhost',no_proxy:'127.0.0.1,localhost'});
  delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch(process.env.ECA_TEST_EXE?{executablePath:process.env.ECA_TEST_EXE,args:[],env}:{args:['.'],env});
  const page=await app.firstWindow();page.on('pageerror',e=>errors.push(String(e)));
  await app.evaluate(({BrowserWindow,dialog},folder)=>{
    BrowserWindow.getAllWindows()[0].setContentSize(1280,860);
    dialog.showOpenDialog=async()=>({canceled:false,filePaths:[folder]});
  },project);
  const invoke=(method,params={})=>page.evaluate(([method,params])=>window.eca.invoke(method,params),[method,params]);
  const config={api_format:'openai',base_url:`http://127.0.0.1:${server.address().port}/v1`,no_auth:true};
  const model=await invoke('config.save',{...config,model:'fixture',name:'本地模拟模型'});
  await invoke('config.default',{id:model.savedId});
  await page.getByRole('button',{name:'打开项目',exact:true}).click();
  await expect.poll(async()=>(await invoke('snapshot')).project).toBe(project);
  const first=(await invoke('snapshot')).session_id;
  const input=page.getByLabel('任务指令');

  // A session that never ran must stay plain: no state marker at all.
  await expect(page.locator(`[data-session-id="${first}"] .session-state`)).toHaveCount(0);

  // Second session runs the fixture turn.
  await page.getByRole('button',{name:'新建会话',exact:true}).click();
  await expect.poll(async()=>(await invoke('snapshot')).session_id).not.toBe(first);
  const second=(await invoke('snapshot')).session_id;
  await input.fill('第一轮任务');await input.press('Enter');
  await expect.poll(()=>exchanges.length).toBe(1);
  start(exchanges[0].res);delta(exchanges[0].res,{content:'FIRST_ANSWER'});
  // While running the row shows the orange "运行中" marker, never the green dot.
  await expect(page.locator(`[data-session-id="${second}"] .session-state`)).toContainText('运行中');
  await expect(page.locator(`[data-session-id="${second}"] .session-state.done`)).toHaveCount(0);
  await capture('running');
  end(exchanges[0].res);
  await expect.poll(async()=>(await invoke('live')).busy).toBe(false);
  await expect(page.locator('.messages')).toContainText('FIRST_ANSWER');

  // Finished: the same row now carries the green dot instead of looking idle.
  const dot=page.locator(`[data-session-id="${second}"] .session-state.done`);
  await expect(dot).toBeVisible();
  await expect(dot).toHaveAttribute('aria-label','本轮已完成');
  await expect(page.locator(`[data-session-id="${second}"] .session-state`)).not.toContainText('运行中');
  await expect(page.locator(`[data-session-id="${first}"] .session-state`)).toHaveCount(0);
  const green=await dot.locator('i').evaluate(node=>getComputedStyle(node).backgroundColor);
  await capture('finished');

  // Opening the row clears the marker.
  await page.locator(`[data-session-id="${second}"]`).click();
  await expect(dot).toHaveCount(0);

  if(errors.length)throw new Error('renderer errors: '+errors.join(' | '));
  await expect(dot).toHaveCount(0);

  // A run that ends in error must not claim "finished": same slot, red marker.
  await page.getByRole('button',{name:'新建会话',exact:true}).click();
  await expect.poll(async()=>(await invoke('snapshot')).session_id).not.toBe(second);
  const third=(await invoke('snapshot')).session_id;
  await input.fill('会失败的任务');await input.press('Enter');
  await expect.poll(()=>exchanges.length).toBeGreaterThan(2);
  for(const exchange of exchanges){
    if(exchange.res.writableEnded||exchange.handled)continue;
    exchange.handled=true;
    exchange.res.writeHead(500,{'Content-Type':'application/json'});
    exchange.res.end('{"error":{"message":"fixture refusal"}}');
  }
  await expect(page.locator(`[data-session-id="${third}"] .session-state.failed`)).toBeVisible();
  await expect(page.locator(`[data-session-id="${third}"] .session-state.done`)).toHaveCount(0);
  fs.writeFileSync(path.join(output,`${mode}.json`),JSON.stringify({mode,
    exe:process.env.ECA_TEST_EXE||'development',requests:exchanges.length,green,
    dot:'green after a completed run, cleared when the row is opened, red after a failed run'},null,2));
  console.log('done-dot ok',mode,'requests',exchanges.length,'green',green);
  server.close();for(const s of sockets)s.destroy();
  await app.close();
  process.exit(0);
})().catch(error=>{
  console.error(error);
  server.close();for(const s of sockets)s.destroy();
  // A hidden test window occasionally refuses a graceful close; do not hang the run.
  setTimeout(()=>process.exit(1),4000).unref();
  if(app)app.close().catch(()=>process.exit(1));
});
