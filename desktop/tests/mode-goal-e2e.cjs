// Isolated hidden app + local model fixture: mode switching and the session goal.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents',home=fs.mkdtempSync(path.join(base,'mode-goal-'));
const project=path.join(home,'项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/mode-goal');fs.mkdirSync(output,{recursive:true});
const mode=process.env.ECA_TEST_MODE||'development',requests=[],errors=[];
const server=http.createServer(async(req,res)=>{
  let raw='';for await(const c of req)raw+=c;requests.push(JSON.parse(raw));
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  res.end('data: '+JSON.stringify({id:'fixture',choices:[{index:0,delta:{content:'已完成这一步'},finish_reason:'stop'}]})+'\n\ndata: [DONE]\n\n');
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
  const saved=await invoke('config.save',{name:'模式测试',api_format:'openai',model:'fixture-model',
    base_url:`http://127.0.0.1:${server.address().port}/v1`,no_auth:true});
  await invoke('config.default',{id:saved.savedId});
  await page.getByRole('button',{name:'打开项目',exact:true}).click();
  await expect.poll(async()=>(await invoke('snapshot')).project).toBe(project);

  // 1. Mode chip switches the session to plan mode and survives a reload.
  await expect(page.locator('.mode-chip')).toContainText('编码');
  await page.locator('.mode-chip').click();
  await page.getByRole('menuitemradio',{name:/计划/}).click();
  await expect(page.locator('.mode-chip')).toContainText('计划');
  await expect.poll(async()=>(await invoke('snapshot')).settings.mode).toBe('plan');

  // 2. The goal dialog stores a goal with acceptance criteria.
  await page.locator('.goal-chip').click();
  const dialog=page.locator('dialog.goal-dialog');
  await dialog.locator('textarea').nth(0).fill('交付可用的计划模式');
  await dialog.locator('textarea').nth(1).fill('给出分步计划\n标注已知风险');
  await dialog.getByRole('button',{name:'开始跟踪'}).click();
  await expect(page.locator('.goal-bar')).toContainText('交付可用的计划模式');
  await expect(page.locator('.goal-bar')).toContainText('0/2');
  await page.locator('.goal-summary').click();
  await expect(page.locator('.goal-criteria')).toContainText('标注已知风险');

  // 3. A plan-mode request only receives read-only tools plus goal_update.
  await page.getByLabel('任务指令').fill('看看这个项目');
  await page.getByRole('button',{name:'发送任务',exact:true}).click();
  // Session naming may add its own model call, so match the run by its prompt.
  const runWith=text=>requests.filter(r=>Array.isArray(r.tools)&&r.tools.length&&JSON.stringify(r.messages).includes(text));
  await expect.poll(()=>runWith('看看这个项目').length,{timeout:60000}).toBe(1);
  await expect.poll(async()=>(await invoke('snapshot')).busy).toBe(false);
  const planRun=runWith('看看这个项目')[0],planTools=planRun.tools.map(t=>t.function.name);
  for(const name of ['write','edit','shell','delete'])assert(!planTools.includes(name),`${name} leaked into plan mode`);
  for(const name of ['read','goal_update'])assert(planTools.includes(name),`${name} missing in plan mode`);
  assert(JSON.stringify(planRun.messages).includes('交付可用的计划模式'),'goal did not reach the model prompt');

  // 4. "按此计划执行" switches back to code mode and starts a new run.
  await expect(page.locator('.plan-next button')).toBeVisible();
  await page.locator('.plan-next button').click();
  await expect.poll(()=>runWith('按上面的计划开始执行').length,{timeout:60000}).toBe(1);
  await expect.poll(async()=>(await invoke('snapshot')).settings.mode).toBe('code');
  assert(runWith('按上面的计划开始执行')[0].tools.map(t=>t.function.name).includes('write'),'code mode lost write');

  // 5. Reload keeps the goal and the mode, then the goal can be cleared.
  await page.reload();
  await expect(page.locator('.goal-bar')).toContainText('交付可用的计划模式');
  await expect(page.locator('.mode-chip')).toContainText('编码');
  await page.getByLabel('清除目标').click();
  await expect(page.locator('.goal-bar')).toHaveCount(0);
  assert.equal((await invoke('snapshot')).goal,null);

  await page.screenshot({path:path.join(output,'plan-goal.png')});
  assert.deepEqual(errors,[]);
  const report={mode,exe:process.env.ECA_TEST_EXE||'development',requests:requests.length,
    planTools:planTools.length,goalPromptInjected:true,errors};
  fs.writeFileSync(path.join(output,`${mode}.json`),JSON.stringify(report,null,1));
  console.log(JSON.stringify(report));
  await app.close();server.close();
})().catch(async error=>{
  console.error(error);
  try {fs.writeFileSync(path.join(output,`${mode}-failure.json`),JSON.stringify({error:String(error),errors},null,1));} catch {}
  if(app)await app.close();
  server.close();
  process.exit(1);
});
