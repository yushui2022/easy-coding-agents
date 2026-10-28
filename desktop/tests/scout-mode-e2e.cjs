// Hidden owned Electron window, local SSE fixture only. Never touches user data.
// Proves the 找方向 (scout) mode end to end: the mode is selectable, its four-stage
// strip reads real state, the category quota refuses a fourth variant of the same
// pool, a rejected idea lands in the rejection list, and the shortlist gate names
// what is still missing. No paid API calls.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents';
fs.mkdirSync(base,{recursive:true});
const home=fs.mkdtempSync(path.join(base,'scout-'));
const project=path.join(home,'找方向 项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/scout');fs.mkdirSync(output,{recursive:true});
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
// Answers the next request with one more candidate in one category.
async function candidate(id,name,category,what){
  const exchange=await next();
  call(exchange.res,id,'scout_candidate',{id,name,company:'某中小公司',category,what,buyer:'门店老板',
    price:'¥99/月',replicable:'一个人两周能搭',effort:'weeks',moat:'线下关系',risk:'平台改规则',
    why_not_obvious:'不是第一反应的那个',sources:['s1']});
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

  // The mode is a real choice in the menu, labelled 找方向.
  await page.locator('.mode-chip').click();
  const row=page.locator('.permission-row').filter({hasText:'找方向'});
  await expect(row).toBeVisible();
  await row.click();
  await expect.poll(async()=>(await invoke('snapshot')).settings.mode).toBe('scout');

  const strip=page.locator('.research-stages');
  await expect(strip).toBeVisible();
  await expect(strip.locator('.research-step')).toHaveCount(4);
  await expect(strip.locator('.research-step.is-current')).toHaveText('立标准');
  await expect(strip.locator('.research-counts')).toContainText('候选 0');
  await capture('stage-criteria');

  const input=page.getByLabel('任务指令');

  // Turn 1: the model tries to sweep before any criteria file exists.
  await input.fill('帮我找找能做的方向');await input.press('Enter');
  call((await take('帮我找找能做的方向')).res,'stage-1','scout_stage',{stage:'sweep'});
  const refused=await take('Cannot enter sweep');
  expect(JSON.stringify(refused.body)).toContain('criteria');
  call(refused.res,'doc-1','scout_doc',{name:'criteria.md',
    content:'# 筛选标准\n\n小团队＝2 人两个月。只考虑已经有人付月费的产品。\n不做：需要销售团队、需要牌照、平台独家。\n'});
  const afterWrite=await take('criteria.md');
  call(afterWrite.res,'stage-2','scout_stage',{stage:'sweep'});
  say((await next()).res,'已进入扫样本阶段。');
  await expect.poll(async()=>(await invoke('live')).busy).toBe(false);
  await expect(strip.locator('.research-step.is-current')).toHaveText('扫样本');

  // Turn 2: one source page, four variants of one category, one rejection.
  await input.fill('继续扫一个行业');await input.press('Enter');
  const source=await take('继续扫一个行业');
  call(source.res,'src-1','scout_source',{id:'s1',kind:'product',url:'https://example.com/a',title:'A 产品页'});
  await candidate('a1','门店回访','本地服务','自动回访未接来电');
  await candidate('a2','门店排班','本地服务','排班与调班');
  await candidate('a3','门店对账','本地服务','每日对账');
  const quota=await next();
  call(quota.res,'cand-4','scout_candidate',{id:'a4',name:'门店第四个',company:'某中小公司',category:'本地服务',
    what:'同一池子的第四个',buyer:'门店老板',price:'¥39/月',replicable:'两周能搭',effort:'weeks',
    moat:'线下关系',risk:'平台改规则',why_not_obvious:'还是在同一个池子里',sources:['s1']});
  // The quota refusal comes back as the next request's tool result.
  const crowded=await take('already has 3 candidates');
  expect(JSON.stringify(crowded.body)).toContain('leave the obvious pool');
  call(crowded.res,'excl-1','scout_exclude',{idea:'AI 套壳聊天',why:'没有付费理由',category:'ai'});
  // And the shortlist gate answers with every missing piece.
  const shortlistAsk=await next();
  call(shortlistAsk.res,'short-1','scout_shortlist',{picks:[{id:'a1',why:'有人付费',first_experiment:'问十家'}]});
  const denied=await take('Cannot shortlist yet');
  const deniedBody=JSON.stringify(denied.body);
  expect(deniedBody).toContain('candidates');
  expect(deniedBody).toContain('excluded');
  say(denied.res,'同一类已有 3 个，换行业；候选池也不够，先扫够 20 个再挑。');
  await expect.poll(async()=>(await invoke('live')).busy).toBe(false);

  // The strip counts the real pool, the spread and the rejection list.
  await expect(strip.locator('.research-counts')).toContainText('候选 3');
  await expect(strip.locator('.research-counts')).toContainText('类别 1');
  await expect(strip.locator('.research-counts')).toContainText('排除 1');
  await expect(strip.locator('.research-counts')).toContainText('未出');
  await strip.locator('.research-toggle').click();
  await expect(strip.locator('.research-artifacts')).toContainText('.eca/scout/criteria.md');
  await expect(strip.locator('.research-artifacts')).toContainText('.eca/scout/excluded.md');
  await capture('stage-sweep');

  const scan=await invoke('snapshot').then(value=>value.scout);
  expect(scan.counts.candidates).toBe(3);
  expect(scan.counts.categories).toBe(1);
  expect(scan.counts.excluded).toBe(1);
  expect(scan.counts.shortlist).toBe(false);
  expect(fs.readFileSync(path.join(project,'.eca','scout','excluded.md'),'utf8')).toContain('AI 套壳聊天');

  if(errors.length)throw new Error('renderer errors: '+errors.join(' | '));
  fs.writeFileSync(path.join(output,`${mode}.json`),JSON.stringify({mode,
    exe:process.env.ECA_TEST_EXE||'development',requests:exchanges.length,
    gate:'scout_stage refused before criteria.md, category quota refused the 4th, shortlist gate named the gap',
    counts:scan.counts,artifacts:scan.artifacts.map(item=>item.name)},null,2));
  console.log('scout ok',mode,'requests',exchanges.length,'candidates',scan.counts.candidates);
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
