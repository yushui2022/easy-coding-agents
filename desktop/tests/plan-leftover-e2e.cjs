// Hidden owned Electron window, local SSE fixture only. Never touches user data.
// Proves the execution checklist stops looking "still running" when a turn ends
// with unchecked steps, and reports how many are left instead of silently
// showing a half-checked list.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents';
fs.mkdirSync(base,{recursive:true});
const home=fs.mkdtempSync(path.join(base,'plan-leftover-'));
const project=path.join(home,'清单 项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/plan-leftover');fs.mkdirSync(output,{recursive:true});
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
const say=(res,text)=>{start(res);delta(res,{content:text});end(res);};
const todoCall=(res,id,items)=>{
  start(res);
  delta(res,{tool_calls:[{index:0,id,type:'function',function:{name:'todo',arguments:JSON.stringify({items})}}]},'tool_calls');
  end(res);
};
const STEPS=[
  {content:'收集材料',status:'completed'},
  {content:'写总结',status:'in_progress'},
  {content:'复核',status:'pending'},
];
// Session-title requests also reach this fixture, so pick requests by prompt
// text rather than arrival order; anything else gets a quiet one-line summary.
const answered=new Set();
async function take(marker){
  await expect.poll(()=>{
    for(const [index,exchange] of exchanges.entries()){
      if(answered.has(index))continue;
      if(JSON.stringify(exchange.body).includes(marker))return index;
      answered.add(index);say(exchange.res,'测试会话');
    }
    return -1;
  },{timeout:20000}).not.toBe(-1);
  const index=exchanges.findIndex((exchange,position)=>!answered.has(position)&&JSON.stringify(exchange.body).includes(marker));
  answered.add(index);
  return exchanges[index].res;
}
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
    BrowserWindow.getAllWindows()[0].setContentSize(1280,900);
    dialog.showOpenDialog=async()=>({canceled:false,filePaths:[folder]});
  },project);
  const invoke=(method,params={})=>page.evaluate(([method,params])=>window.eca.invoke(method,params),[method,params]);
  const config={api_format:'openai',base_url:`http://127.0.0.1:${server.address().port}/v1`,no_auth:true};
  const model=await invoke('config.save',{...config,model:'fixture',name:'本地模拟模型'});
  await invoke('config.default',{id:model.savedId});
  await page.getByRole('button',{name:'打开项目',exact:true}).click();
  await expect.poll(async()=>(await invoke('snapshot')).project).toBe(project);
  const input=page.getByLabel('任务指令');
  const checklist=page.locator('.plan-checklist');

  // Turn 1: the model writes a 3-step list, finishes one step, stops anyway.
  await input.fill('按三步做这件事');await input.press('Enter');
  todoCall(await take('按三步做这件事'),'todo-1',STEPS);
  say(await take('todo-1'),'先做到这里，剩下的还没开始。');
  await expect.poll(async()=>(await invoke('live')).busy).toBe(false);

  // Unfinished steps must be reported, not left looking in-flight.
  await expect(checklist).toContainText('执行清单');
  await expect(checklist.locator('.plan-progress')).toHaveText('1/3');
  await expect(checklist.locator('.plan-count.is-unfinished')).toHaveText('2 未完成');
  await expect(checklist.locator('.plan-hint')).toContainText('本轮已结束');
  await expect(checklist).not.toHaveClass(/is-done/);
  const second=checklist.locator('.plan-item').nth(1);
  await expect(second).toHaveClass(/is-in_progress/);
  await expect(second.locator('.plan-badge')).toHaveText('未完成');
  // Nothing is running any more, so no in-flight spinner may be left behind.
  await expect(checklist.locator('svg.ph-circle-dashed')).toHaveCount(0);
  await capture('leftover');

  // Turn 2: the list is finished properly and the checklist closes cleanly.
  await input.fill('把剩下的做完');await input.press('Enter');
  todoCall(await take('把剩下的做完'),'todo-2',STEPS.map(step=>({...step,status:'completed'})));
  say(await take('todo-2'),'三步都做完了。');
  await expect.poll(async()=>(await invoke('live')).busy).toBe(false);
  await expect(checklist.locator('.plan-progress')).toHaveText('3/3');
  await expect(checklist.locator('.plan-count.is-unfinished')).toHaveCount(0);
  await expect(checklist.locator('.plan-hint')).toHaveCount(0);
  await expect(checklist).toHaveClass(/is-done/);

  if(errors.length)throw new Error('renderer errors: '+errors.join(' | '));
  fs.writeFileSync(path.join(output,`${mode}.json`),JSON.stringify({mode,
    exe:process.env.ECA_TEST_EXE||'development',requests:exchanges.length,
    leftover:'1/3 with "2 未完成" and a closed-turn hint',closing:'3/3, no unfinished badge'},null,2));
  console.log('plan-leftover ok',mode,'requests',exchanges.length);
  server.close();for(const s of sockets)s.destroy();
  await app.close();
  process.exit(0);
})().catch(error=>{
  console.error(error);
  server.close();for(const s of sockets)s.destroy();
  if(app)app.close().then(()=>process.exit(1),()=>process.exit(1));
  else process.exit(1);
});
