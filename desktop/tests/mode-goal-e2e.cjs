// Isolated hidden app + local model fixture: mode switching, the session goal,
// and the todo-backed plan that becomes the running checklist.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents',home=fs.mkdtempSync(path.join(base,'mode-goal-'));
const project=path.join(home,'项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/mode-goal');fs.mkdirSync(output,{recursive:true});
const mode=process.env.ECA_TEST_MODE||'development',requests=[],errors=[];
const STEPS=['读入口文件确认结构','列出要改的模块','给出改动顺序'];
const todoCall=(items,id)=>({id:'fixture',choices:[{index:0,delta:{tool_calls:[{index:0,id,type:'function',
  function:{name:'todo',arguments:JSON.stringify({items})}}]},finish_reason:'tool_calls'}]});
const textCall=text=>({id:'fixture',choices:[{index:0,delta:{content:text},finish_reason:'stop'}]});
const goalCall=(updates,id)=>({id:'fixture',choices:[{index:0,delta:{tool_calls:[{index:0,id,type:'function',
  function:{name:'goal_update',arguments:JSON.stringify({updates})}}]},finish_reason:'tool_calls'}]});
const server=http.createServer(async(req,res)=>{
  let raw='';for await(const c of req)raw+=c;
  // Opening the settings dialog re-reads the model catalogue; answer that here.
  // GitHub API and the model catalogue share this fixture; branch on the path.
  if(req.method==='GET'&&String(req.url)=== '/user'){
    res.writeHead(200,{'Content-Type':'application/json'});
    res.end(JSON.stringify({login:'fixture-user'}));
    return;
  }
  if(req.method==='GET'&&String(req.url).startsWith('/user/repos')){
    res.writeHead(200,{'Content-Type':'application/json'});
    res.end(JSON.stringify([{full_name:'fixture-org/demo',private:true,description:'fixture repo',
      updated_at:'2026-01-01T00:00:00Z',default_branch:'main',clone_url:'https://github.com/fixture-org/demo.git'}]));
    return;
  }
  if(req.method==='GET'){
    res.writeHead(200,{'Content-Type':'application/json'});
    res.end(JSON.stringify({data:[{id:'fixture-model',object:'model'}]}));
    return;
  }
  let payload={};try{payload=raw?JSON.parse(raw):{};}catch{payload={};}
  requests.push(payload);
  // The runtime appends its own guidance message after the prompt, so take the
  // newest genuine user message instead of positionally the last one.
  const lastUser=((payload.messages||[]).filter(m=>m.role==='user')
    .map(m=>JSON.stringify(m.content||'')).filter(t=>!t.includes('[Runtime guidance]')).slice(-1)[0])||'';
  const lastIsTool=((payload.messages||[]).slice(-1)[0]||{}).role==='tool';
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  let body;
  const nudged=JSON.stringify(payload.messages||[]).includes('The session goal is not met');
  if(lastIsTool){
    body=textCall('已完成这一步');
  } else if(nudged){
    body=goalCall([{index:1,done:true},{index:2,done:true}],'call_goal');
  } else if(lastUser.includes('按上面的计划开始执行')){
    body=todoCall([{content:STEPS[0],status:'completed'},{content:STEPS[1],status:'in_progress'},{content:STEPS[2],status:'pending'}],'call_run');
  } else if(lastUser.includes('看看这个项目')){
    body=todoCall(STEPS.map(content=>({content,status:'pending'})),'call_plan');
  } else body=textCall('已完成这一步');
  res.end('data: '+JSON.stringify(body)+'\n\ndata: [DONE]\n\n');
});
let app;
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const env={...process.env};
  for(const k of Object.keys(env))if(k.startsWith('ECA_')||/API_KEY|API_BASE|BASE_URL|MODEL_NAME|PYTHONHOME|PYTHONPATH/.test(k))delete env[k];
  Object.assign(env,{TEMP:base,TMP:base,ECA_DESKTOP_TEST_HIDDEN:'1',ECA_DESKTOP_DATA_HOME:path.join(home,'data'),
    ECA_GITHUB_API:`http://127.0.0.1:${server.address().port}`,
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
  const saved=await invoke('config.save',{name:'模式测试',api_format:'openai',model:'fixture-model',
    base_url:`http://127.0.0.1:${server.address().port}/v1`,no_auth:true});
  await invoke('config.default',{id:saved.savedId});

  // 0. 四个设置分区各自独立：外观主题、个人信息、全局指令分页保存，且都进系统提示词。
  await page.getByRole('button',{name:'模型与设置'}).click();
  // The section rail must stay compact: the connection rows used to stretch these
  // buttons because both live in a <nav>.
  const firstNav = await page.locator('.settings-nav-item').first().boundingBox();
  assert(firstNav && firstNav.height <= 40, 'section nav items are stretched');
  await expect(page.locator('.connections-label')).toHaveCount(0);
  await page.screenshot({path:path.join(output,'settings-rail.png'), animations:'disabled', timeout:15000}).catch(()=>{});
  await page.getByRole('button',{name:'外观主题'}).click();
  await page.getByRole('radio',{name:'深色'}).click();
  await expect.poll(()=>page.evaluate(()=>window.eca.theme())).toBe('dark');
  await page.getByRole('radio',{name:'跟随系统'}).click();
  await page.getByRole('button',{name:'个人信息'}).click();
  await expect(page.locator('.profile-hero')).toBeVisible();
  await expect(page.locator('.profile-stats > div')).toHaveCount(5);
  await expect(page.locator('.profile-stats')).toContainText('累计 Token');
  await page.screenshot({path:path.join(output,'settings-profile.png'), animations:'disabled', timeout:15000}).catch(()=>{});
  await page.getByLabel('称呼').fill('小明');
  await page.getByLabel('身份').fill('后端工程师');
  await page.getByLabel('关于我').fill('在做 ECA 这个项目');
  await page.getByLabel('回答偏好').fill('先给结论');
  await page.getByRole('button',{name:'保存个人信息'}).click();
  await expect(page.locator('.personal-pane .config-status')).toContainText('已保存');
  await page.getByRole('button',{name:'全局指令'}).click();
  await page.getByLabel('每轮对话都会带上').fill('每轮回答先给结论。');
  await page.getByRole('button',{name:'保存全局指令'}).click();
  await expect(page.locator('.personal-pane .config-status')).toContainText('已保存');
  await page.getByRole('button',{name:'GitHub'}).click();
  await expect(page.getByLabel('访问令牌')).toBeVisible();
  await page.getByLabel('访问令牌').fill('ghp_fixture');
  await page.getByRole('button',{name:'连接账号'}).click();
  await expect(page.locator('.personal-pane .connection-default-badge')).toContainText('fixture-user');
  await expect(page.locator('.repo-row')).toContainText('fixture-org/demo');
  assert(fs.existsSync(path.join(home,'data','github.json')),'github.json was not written');
  const stored=fs.readFileSync(path.join(home,'data','github.json'),'utf8');
  assert(!stored.includes('ghp_fixture'),'token must not be stored in clear text');
  await page.getByRole('button',{name:'关闭设置'}).click();
  assert(fs.existsSync(path.join(home,'data','profile.json')),'profile.json was not written');
  assert(fs.existsSync(path.join(home,'data','AGENTS.md')),'global AGENTS.md was not written');
  await page.getByRole('button',{name:'打开项目',exact:true}).click();
  await expect.poll(async()=>(await invoke('snapshot')).project).toBe(project);

  // Session naming adds its own model call, so match the run by prompt and require
  // Match a turn start: the prompt is in the transcript and the last message is
  // not a tool result (history from earlier runs does contain tool messages).
  const turnStart=text=>requests.filter(r=>Array.isArray(r.tools)&&r.tools.length
    &&JSON.stringify(r.messages).includes(text)&&r.messages.slice(-1)[0]?.role!=='tool');

  // 1. The goal is set from goal mode only: entering it without an objective opens
  //    the dialog, and there is no separate goal chip in the composer any more.
  await expect(page.locator('.mode-chip')).toContainText('编码');
  await expect(page.locator('.goal-chip')).toHaveCount(0);
  await page.locator('.mode-chip').click();
  await page.getByRole('menuitemradio',{name:/目标/}).click();
  await expect(page.locator('.mode-chip')).toContainText('目标');
  const dialog=page.locator('dialog.goal-dialog');
  await expect(dialog).toBeVisible();
  await dialog.locator('textarea').nth(0).fill('交付可用的计划模式');
  await dialog.locator('textarea').nth(1).fill('给出分步计划\n标注已知风险');
  await dialog.getByRole('button',{name:'开始跟踪'}).click();
  await expect(page.locator('.goal-bar')).toContainText('交付可用的计划模式');
  await expect(page.locator('.goal-bar')).toContainText('0/2');

  // 2. Switching to plan mode keeps the goal and drops to read-only tools.
  await page.locator('.mode-chip').click();
  await page.getByRole('menuitemradio',{name:/计划/}).click();
  await expect(page.locator('.mode-chip')).toContainText('计划');
  await expect.poll(async()=>(await invoke('snapshot')).settings.mode).toBe('plan');

  // 3. A plan-mode request only receives read-only tools plus goal_update, and the
  //    model's todo call becomes the plan checklist in the conversation.
  await page.getByLabel('任务指令').fill('看看这个项目');
  await page.getByRole('button',{name:'发送任务',exact:true}).click();
  await expect.poll(()=>turnStart('看看这个项目').length,{timeout:60000}).toBeGreaterThan(0);
  await expect.poll(async()=>(await invoke('snapshot')).busy,{timeout:60000}).toBe(false);
  const planRun=turnStart('看看这个项目')[0],planTools=planRun.tools.map(t=>t.function.name);
  for(const name of ['write','edit','shell','delete'])assert(!planTools.includes(name),`${name} leaked into plan mode`);
  for(const name of ['read','todo','goal_update'])assert(planTools.includes(name),`${name} missing in plan mode`);
  assert(JSON.stringify(planRun.messages).includes('交付可用的计划模式'),'goal did not reach the model prompt');
  const checklist=page.locator('.plan-checklist');
  await expect(checklist).toContainText('计划步骤');
  await expect(checklist.locator('.plan-item')).toHaveCount(3);
  await expect(checklist).toContainText('0/3');
  await expect(checklist).toContainText(STEPS[0]);
  assert.deepEqual((await invoke('snapshot')).tasks.map(t=>t.status),['pending','pending','pending']);

  // 4. "按此计划执行" sends the approved checklist and switches back to code mode.
  await expect(page.locator('.plan-next button')).toBeVisible();
  await page.locator('.plan-next button').click();
  await expect.poll(()=>turnStart('按上面的计划开始执行').length,{timeout:60000}).toBeGreaterThan(0);
  const runRequest=turnStart('按上面的计划开始执行')[0];
  assert(runRequest.tools.map(t=>t.function.name).includes('write'),'code mode lost write');
  const handed=JSON.stringify(runRequest.messages);
  for(const step of STEPS)assert(handed.includes(step),`step missing from the approved plan message: ${step}`);
  await expect.poll(async()=>(await invoke('snapshot')).settings.mode).toBe('code');
  await expect(checklist).toContainText('执行清单');
  await expect(checklist).toContainText('1/3');
  await expect(checklist.locator('.plan-item').first()).toHaveClass(/is-completed/);

  // 5. Reload keeps the checklist and the goal, then the goal can be cleared.
  await page.reload();
  await expect(checklist).toContainText('1/3');
  await expect(page.locator('.goal-bar')).toContainText('交付可用的计划模式');
  await page.getByLabel('清除目标').click();
  await expect(page.locator('.goal-bar')).toHaveCount(0);
  assert.equal((await invoke('snapshot')).goal,null);

  // 6. Goal mode is its own mode: it asks for an objective on entry, and an unmet
  //    goal keeps the turn going instead of ending on a progress summary.
  await page.locator('.mode-chip').click();
  await page.getByRole('menuitemradio',{name:/目标/}).click();
  await expect(page.locator('.mode-chip')).toContainText('目标');
  const goalDialog=page.locator('dialog.goal-dialog');
  await expect(goalDialog).toBeVisible();
  await goalDialog.locator('textarea').nth(0).fill('自动推进到达标');
  await goalDialog.locator('textarea').nth(1).fill('第一阶段完成\n第二阶段完成');
  await goalDialog.getByRole('button',{name:'开始跟踪'}).click();
  await expect(page.locator('.goal-bar')).toContainText('0/2');
  await page.getByLabel('任务指令').fill('达成目标');
  await page.getByRole('button',{name:'发送任务',exact:true}).click();
  await expect.poll(()=>turnStart('达成目标').length,{timeout:60000}).toBeGreaterThan(1);
  await expect.poll(async()=>(await invoke('snapshot')).busy,{timeout:60000}).toBe(false);
  const pushed=requests.filter(r=>JSON.stringify(r.messages||[]).includes('The session goal is not met'));
  assert(pushed.length>0,'goal mode ended the turn without pushing for the open criteria');
  assert.equal((await invoke('snapshot')).goal.status,'done');
  await expect(page.locator('.goal-bar')).toContainText('2/2');
  assert(requests.filter(r=>Array.isArray(r.tools)&&r.tools.length)
    .every(r=>String(r.messages?.[0]?.content||'').includes('每轮回答先给结论')),'global instructions missing from the system prompt');
  assert(requests.filter(r=>Array.isArray(r.tools)&&r.tools.length)
    .every(r=>String(r.messages?.[0]?.content||'').includes('小明')),'profile name missing from the system prompt');
  assert(requests.filter(r=>Array.isArray(r.tools)&&r.tools.length)
    .every(r=>String(r.messages?.[0]?.content||'').includes('Their role: 后端工程师')),'role missing from the system prompt');
  assert(requests.filter(r=>Array.isArray(r.tools)&&r.tools.length)
    .every(r=>String(r.messages?.[0]?.content||'').includes('How they want answers: 先给结论')),'style missing from the system prompt');

  await page.screenshot({path:path.join(output,'plan-goal.png')});
  assert.deepEqual(errors,[]);
  const report={mode,exe:process.env.ECA_TEST_EXE||'development',requests:requests.length,
    planTools:planTools.length,goalPromptInjected:true,planChecklist:3,handedOver:true,errors};
  fs.writeFileSync(path.join(output,`${mode}.json`),JSON.stringify(report,null,1));
  console.log(JSON.stringify(report));
  await app.close();server.close();
})().catch(async error=>{
  console.error(error);
  const shapes=requests.map(r=>({tools:Array.isArray(r.tools)?r.tools.length:'none',
    lastRole:(r.messages||[]).slice(-1)[0]?.role,
    lastUser:JSON.stringify((r.messages||[]).slice().reverse().find(m=>m.role==='user')?.content||'').slice(0,200),
    head:JSON.stringify(r.messages||[]).slice(0,160)}));
  try {const body=await app.firstWindow().then(w=>w.locator('body').innerText());console.error('BODY:',body.slice(-800));} catch {}
  try {fs.writeFileSync(path.join(output,`${mode}-failure.json`),JSON.stringify({error:String(error),errors,shapes},null,1));} catch {}
  if(app)await app.close();
  server.close();
  process.exit(1);
});
