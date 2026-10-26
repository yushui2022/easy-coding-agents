// Hidden owned Electron window, local SSE fixture only. Never touches user data.
// Proves the 科研 (scholar) mode end to end: the mode is selectable, the stage
// strip reads real state, research_stage refuses to skip the proposal gate, and
// once proposal.md exists on disk the stage actually moves and the artifact list
// grows. No paid API calls.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents';
fs.mkdirSync(base,{recursive:true});
const home=fs.mkdtempSync(path.join(base,'scholar-'));
const project=path.join(home,'科研 项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/scholar');fs.mkdirSync(output,{recursive:true});
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

// The next request the app sends, whatever it contains: used where the marker
// would be a tool result whose wording we do not control.
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

  // The mode is a real choice in the menu, labelled 科研.
  await page.locator('.mode-chip').click();
  const row=page.locator('.permission-row').filter({hasText:'科研'});
  await expect(row).toBeVisible();
  await row.click();
  await expect.poll(async()=>(await invoke('snapshot')).settings.mode).toBe('scholar');

  const strip=page.locator('.research-stages');
  await expect(strip).toBeVisible();
  await expect(strip.locator('.research-step')).toHaveCount(7);
  await expect(strip.locator('.research-step.is-current')).toHaveText('选题');
  await expect(strip.locator('.research-counts')).toContainText('源 0');
  await capture('stage-proposal');

  // Turn 1: the model tries to jump to 检索 before any proposal exists.
  const input=page.getByLabel('任务指令');
  await input.fill('开始这个课题');await input.press('Enter');
  call((await take('开始这个课题')).res,'stage-1','research_stage',{stage:'search'});
  // The gate refuses, and the refusal names the missing artifact.
  // The gate refuses, and the refusal names the missing artifact.
  const refused=await take('Cannot enter search');
  expect(JSON.stringify(refused.body)).toContain('proposal');
  call(refused.res,'doc-1','research_doc',{name:'proposal.md',
    content:'# Proposal\n\nResearch question: does X improve Y under Z?\n\nHypotheses: H1 X helps, H2 no effect.\n'});
  const afterWrite=await take('proposal.md');
  call(afterWrite.res,'stage-2','research_stage',{stage:'search'});
  const accepted=await next();
  say(accepted.res,'已进入检索阶段。');
  await expect.poll(async()=>(await invoke('live')).busy).toBe(false);

  // The strip followed the real state, and the artifact is listed with a size.
  await expect(strip.locator('.research-step.is-current')).toHaveText('检索');
  await expect(strip.locator('.research-step.is-done').first()).toHaveText('选题');
  await strip.locator('.research-toggle').click();
  await expect(strip.locator('.research-artifacts')).toContainText('.eca/research/proposal.md');
  await capture('stage-search');

  const research=await invoke('snapshot').then(value=>value.research);
  expect(research.stage).toBe('search');
  expect(research.counts.sources).toBe(0);
  expect(fs.readFileSync(path.join(project,'.eca','research','proposal.md'),'utf8')).toContain('Research question');

  if(errors.length)throw new Error('renderer errors: '+errors.join(' | '));
  fs.writeFileSync(path.join(output,`${mode}.json`),JSON.stringify({mode,
    exe:process.env.ECA_TEST_EXE||'development',requests:exchanges.length,
    gate:'research_stage refused before proposal.md, accepted after',stage:research.stage,
    artifacts:research.artifacts.map(item=>item.name)},null,2));
  console.log('scholar ok',mode,'requests',exchanges.length,'stage',research.stage);
  server.close();for(const s of sockets)s.destroy();
  await app.close();
  process.exit(0);
})().catch(error=>{
  console.error(error);
  // Keep the request trail: a hung fixture is otherwise only "timeout", and the
  // interesting question is always which request the app actually sent last.
  try{fs.writeFileSync(path.join(output,`failure-${mode}.json`),JSON.stringify(exchanges.map((exchange,index)=>{
    const messages=exchange.body.messages||[];
    return {index,answered:answered.has(index),tail:messages.slice(-2).map(message=>
      ({role:message.role,content:String(message.content||'').slice(0,600)}))};
  }),null,2));}catch{}
  server.close();for(const s of sockets)s.destroy();
  if(app)app.close().then(()=>process.exit(1),()=>process.exit(1));
  else process.exit(1);
});
