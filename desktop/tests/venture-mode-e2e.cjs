// Hidden owned Electron window, local SSE fixture only. Never touches user data.
// Proves the 商业 (venture) mode end to end: the mode is selectable, its six-stage
// strip reads real state, business_stage refuses to skip the brief gate, and once
// brief.md exists on disk the stage actually moves and the artifact list grows.
// No paid API calls.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents';
fs.mkdirSync(base,{recursive:true});
const home=fs.mkdtempSync(path.join(base,'venture-'));
const project=path.join(home,'商业 项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/venture');fs.mkdirSync(output,{recursive:true});
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
const call=(res,id,name,args)=>{
  start(res);
  delta(res,{tool_calls:[{index:0,id,type:'function',function:{name,arguments:JSON.stringify(args)}}]},'tool_calls');
  end(res);
};
const answered=new Set();
async function take(marker){
  await expect.poll(()=>{
    for(const [index,exchange] of exchanges.entries()){
      if(answered.has(index))continue;
      if(JSON.stringify(exchange.body).includes(marker))return index;
      answered.add(index);say(exchange.res,'测试会话');
    }
    return -1;
  },{timeout:25000}).not.toBe(-1);
  const index=exchanges.findIndex((exchange,position)=>!answered.has(position)&&JSON.stringify(exchange.body).includes(marker));
  answered.add(index);
  return exchanges[index];
}
async function next(){
  await expect.poll(()=>exchanges.findIndex((exchange,index)=>!answered.has(index)),
    {timeout:25000}).not.toBe(-1);
  const index=exchanges.findIndex((exchange,position)=>!answered.has(position));
  answered.add(index);
  return exchanges[index];
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

  // The mode is a real choice in the menu, labelled 商业.
  await page.locator('.mode-chip').click();
  const row=page.locator('.permission-row').filter({hasText:'商业'});
  await expect(row).toBeVisible();
  await row.click();
  await expect.poll(async()=>(await invoke('snapshot')).settings.mode).toBe('venture');

  const strip=page.locator('.research-stages');
  await expect(strip).toBeVisible();
  await expect(strip.locator('.research-step')).toHaveCount(6);
  await expect(strip.locator('.research-step.is-current')).toHaveText('定题');
  await expect(strip.locator('.research-counts')).toContainText('源 0');
  await expect(strip.locator('.research-counts')).toContainText('未出');
  await capture('stage-brief');

  // Turn 1: the model tries to jump to 需求与证据 before any brief exists.
  const input=page.getByLabel('任务指令');
  await input.fill('看看这个项目值不值得做');await input.press('Enter');
  call((await take('看看这个项目值不值得做')).res,'stage-1','business_stage',{stage:'market'});
  const refused=await take('Cannot enter market');
  expect(JSON.stringify(refused.body)).toContain('brief');
  call(refused.res,'doc-1','business_doc',{name:'brief.md',
    content:'# 定题\n\n谁付费：本地服务门店老板。\n任务：每天回访未接来电。\n替代方案：手动表格。\n资源边界：两周、一台电脑。\n'});
  const afterWrite=await take('brief.md');
  call(afterWrite.res,'stage-2','business_stage',{stage:'market'});
  const accepted=await next();
  say(accepted.res,'已进入需求与证据阶段，先查搜索与评论区。');
  await expect.poll(async()=>(await invoke('live')).busy).toBe(false);

  // The strip followed the real state, and the artifact is listed with a size.
  await expect(strip.locator('.research-step.is-current')).toHaveText('需求与证据');
  await expect(strip.locator('.research-step.is-done').first()).toHaveText('定题');
  await strip.locator('.research-toggle').click();
  await expect(strip.locator('.research-artifacts')).toContainText('.eca/business/brief.md');
  await capture('stage-market');

  const business=await invoke('snapshot').then(value=>value.business);
  expect(business.stage).toBe('market');
  expect(business.counts.sources).toBe(0);
  expect(business.verdict).toBeNull();
  expect(fs.readFileSync(path.join(project,'.eca','business','brief.md'),'utf8')).toContain('谁付费');

  if(errors.length)throw new Error('renderer errors: '+errors.join(' | '));
  fs.writeFileSync(path.join(output,`${mode}.json`),JSON.stringify({mode,
    exe:process.env.ECA_TEST_EXE||'development',requests:exchanges.length,
    gate:'business_stage refused before brief.md, accepted after',stage:business.stage,
    artifacts:business.artifacts.map(item=>item.name)},null,2));
  console.log('venture ok',mode,'requests',exchanges.length,'stage',business.stage);
  server.close();for(const s of sockets)s.destroy();
  await app.close();
  process.exit(0);
})().catch(error=>{
  console.error(error);
  try{fs.writeFileSync(path.join(output,`failure-${mode}.json`),JSON.stringify(exchanges.map((exchange,index)=>{
    const messages=exchange.body.messages||[];
    return {index,answered:answered.has(index),tail:messages.slice(-2).map(message=>
      ({role:message.role,content:String(message.content||'').slice(0,600)}))};
  }),null,2));}catch{}
  server.close();for(const s of sockets)s.destroy();
  if(app)app.close().then(()=>process.exit(1),()=>process.exit(1));
  else process.exit(1);
});
