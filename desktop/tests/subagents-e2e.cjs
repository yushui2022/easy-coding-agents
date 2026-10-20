// Owned hidden Electron, actual Python runtime and local streaming model.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents';
const home=fs.mkdtempSync(path.join(base,'child-view-')),project=path.join(home,'子任务 项目');
fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/subagents');fs.mkdirSync(output,{recursive:true});
let stage='parallel',requests=0,app;
const held=new Set(),sockets=new Set(),errors=[];
function piece(res,delta,finish=null){res.write('data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',created:0,model:'fixture',choices:[{index:0,delta,finish_reason:finish}]})+'\n\n');}
function finish(res){if(!res.destroyed){piece(res,{},'stop');res.end('data: [DONE]\n\n');}held.delete(res);}
const server=http.createServer(async(req,res)=>{
  let raw='';for await(const part of req)raw+=part;
  const body=JSON.parse(raw);requests++;
  const child=!body.tools.some(t=>t.function.name==='delegate');
  const history=body.messages.filter(m=>!String(m.content||'').startsWith('[Runtime guidance]'));
  const lastUser=history.findLast(m=>m.role==='user')?.content||'';
  const last=history.at(-1);
  if(child&&stage==='error'){res.writeHead(500,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'Fixture child error'}}));return;}
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  if(child&&last.role==='tool'){
    piece(res,{content:last.content.startsWith('Denied')?'写入已被拒绝，未修改文件。':'已完成文件修改，正在整理子任务结果。\n\n## 检查结论\n\n| 检查项 | 结果 | 后续建议 |\n| --- | --- | --- |\n| 模型配置 | 已检查 | 保持环境变量优先级 |\n| 任务取消 | 已检查 | 确认排队任务一同停止 |\n| 会话恢复 | 待验证 | 补充关闭后重新打开的用例 |\n\n文件修改保存在子任务目录中，等待主 Agent 汇总。'});
    if(stage==='parallel'||stage==='cancel'){held.add(res);res.on('close',()=>held.delete(res));return;}
    finish(res);return;
  }
  if(!child&&last.role==='tool'){piece(res,{content:'主 Agent 已收到所有子任务报告。'});finish(res);return;}
  let name,args;
  if(child){name='write';args={path:'child.txt',content:lastUser};}
  else if(stage==='serial'||stage==='error'){name='delegate';args={task:stage==='serial'?'整理入口文件的验证建议':'检查失败场景',mode:'code'};}
  else{piece(res,{content:'我会安排三个子任务，分别检查模型配置、取消清理和会话恢复。'});name='delegate_parallel';args={tasks:[{task:'梳理模型连接与配置入口',mode:'code'},{task:'检查任务取消与资源清理',mode:'code'},{task:'补充会话恢复的测试建议',mode:'code'}]};}
  piece(res,{tool_calls:[{index:0,id:'call-'+requests,type:'function',function:{name,arguments:JSON.stringify(args)}}]});
  piece(res,{},'tool_calls');res.end('data: [DONE]\n\n');
});
server.on('connection',s=>{sockets.add(s);s.on('close',()=>sockets.delete(s));});
async function capture(name){
  const png=await app.evaluate(async({BrowserWindow})=>{
    const wc=BrowserWindow.getAllWindows()[0].webContents;
    await wc.executeJavaScript('document.fonts.ready.then(async()=>{await Promise.all([...document.images].map(i=>i.decode()));await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));})');
    // A hidden window can retain the previous compositor frame until captured.
    await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});
    await new Promise(resolve=>setTimeout(resolve,180));
    return (await wc.capturePage(undefined,{stayHidden:true,stayAwake:true})).toPNG().toString('base64');
  });fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(png,'base64'));
}
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const env={...process.env};
  for(const name of Object.keys(env))if(name.startsWith('ECA_')||['OPENAI_API_KEY','ANTHROPIC_API_KEY','MODELSCOPE_API_KEY','OPENAI_BASE_URL','ANTHROPIC_BASE_URL','MODEL_NAME'].includes(name))delete env[name];
  Object.assign(env,{TEMP:base,TMP:base,ECA_DESKTOP_TEST_HIDDEN:'1',ECA_DESKTOP_DATA_HOME:path.join(home,'app'),ECA_PYTHON:path.resolve('.venv/Scripts/python.exe'),ECA_API_KEY:'child-fixture',ECA_MODEL:'fixture',ECA_BASE_URL:`http://127.0.0.1:${server.address().port}/v1`,ECA_API_FORMAT:'openai',NO_PROXY:'127.0.0.1,localhost',no_proxy:'127.0.0.1,localhost'});
  delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch(process.env.ECA_TEST_EXE?{executablePath:process.env.ECA_TEST_EXE,args:[],env}:{args:['.'],env});
  const page=await app.firstWindow();page.on('pageerror',e=>errors.push(String(e)));
  await app.evaluate(({BrowserWindow,dialog},project)=>{const win=BrowserWindow.getAllWindows()[0];win.webContents.setBackgroundThrottling(false);win.setContentSize(1440,960);dialog.showOpenDialog=async()=>({canceled:false,filePaths:[project]});},project);
  const invoke=(method,params={})=>page.evaluate(({method,params})=>window.eca.invoke(method,params),{method,params});
  await page.getByRole('button',{name:'打开项目',exact:true}).click();
  const opened=await invoke('snapshot'),owner=opened.session_id,workspaceOwner=opened.workspace_owner;
  await invoke('permissions.set',{mode:'accept-edits'});
  await page.getByLabel('任务指令').fill('把检查分给三个子 Agent，并行执行。');
  await page.getByLabel('任务指令').press('Enter');
  await expect(page.locator('.agent-card')).toHaveCount(3,{timeout:20000});
  await expect.poll(()=>held.size).toBe(2);
  await expect(page.locator('.agent-card').nth(2)).toContainText('排队中');
  await expect(page.locator('.run-activity')).toContainText('子任务执行中');
  await expect(page.locator('.conversation .message.live')).toHaveCount(0);
  assert(await page.locator('.agent-card').first().evaluate(el=>el.getBoundingClientRect().height<=40));
  await expect(page.locator('.conversation .execution-heading')).toHaveCount(0);
  await page.locator('.agent-card').first().click();
  await expect(page.locator('.agent-stream')).toContainText('正在整理');
  const firstId=(await invoke('snapshot')).children[0].id;
  await expect(page.locator('.agent-detail')).toContainText('梳理模型连接与配置入口');
  await expect(page.locator('.agent-stream table')).toBeVisible();
  await expect(page.locator('.agent-stream table tbody tr')).toHaveCount(3);
  assert.equal((await invoke('live')).session_id,owner);
  for(const theme of ['light','dark']){
    await app.evaluate(({nativeTheme},theme)=>{nativeTheme.themeSource=theme;},theme);
    await page.emulateMedia({colorScheme:theme});
    await expect.poll(()=>page.evaluate(()=>matchMedia('(prefers-color-scheme: dark)').matches)).toBe(theme==='dark');
    await capture('running-'+theme);
    assert(await page.locator('.agent-detail').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
  }
  await page.emulateMedia({colorScheme:'light'});
  await app.evaluate(({nativeTheme})=>{nativeTheme.themeSource='light';});
  await page.getByRole('button',{name:'返回主对话',exact:true}).click();
  await expect(page.locator('.workspace-panel')).not.toBeVisible();
  assert((await invoke('subagent.snapshot',{owner:workspaceOwner,id:firstId})).busy);
  await page.locator('.agent-card').first().click();
  await expect(page.locator('.agent-detail')).toBeVisible();
  await page.getByRole('button',{name:'关闭子智能体 01',exact:true}).click();
  assert((await invoke('subagent.snapshot',{owner:workspaceOwner,id:firstId})).busy);
  await page.locator('.agent-card').first().click();
  await expect(page.locator('.agent-stream')).toContainText('正在整理');
  const count=requests;await page.reload();
  await expect(page.locator('.agent-detail')).toBeVisible();
  await expect(page.locator('.agent-stream')).toContainText('正在整理');
  assert.equal(requests,count,'reload must not replay model calls');
  // Only the two running children finish; the queued third then begins.
  [...held].forEach(finish);await expect.poll(()=>held.size).toBe(1);
  [...held].forEach(finish);await expect.poll(async()=>(await invoke('live')).busy).toBe(false);
  await expect(page.locator('.agent-card .status-idle')).toHaveCount(3);
  await expect(page.locator('.agent-detail')).toContainText('已完成文件修改');
  assert(!fs.existsSync(path.join(project,'child.txt')),'isolated modifications must not merge automatically');
  await page.locator('.agent-card').nth(1).click();await expect(page.locator('.workspace-content:not(.inactive) .agent-detail')).toContainText('检查任务取消与资源清理');
  await expect(page.locator('.workspace-content:not(.inactive) .agent-detail table')).toBeVisible();
  await capture('returned-light');
  // Serial child and rejected authorization remain visible without becoming a new main session.
  stage='serial';await invoke('permissions.set',{mode:'ask'});
  await page.getByLabel('任务指令').fill('再委派一个单独的子任务。');await page.getByLabel('任务指令').press('Enter');
  await expect(page.getByRole('region',{name:'等待确认'})).toBeVisible({timeout:20000});
  await expect(page.locator('.agent-card')).toHaveCount(4);
  await page.locator('.agent-card').last().click();
  await page.getByRole('button',{name:'拒绝',exact:true}).click();
  await expect.poll(async()=>(await invoke('live')).busy).toBe(false);
  await expect(page.locator('.workspace-content:not(.inactive) .agent-detail')).toContainText('写入已被拒绝');
  assert(!fs.existsSync(path.join(project,'child.txt')));
  stage='error';
  await page.getByLabel('任务指令').fill('委派失败场景。');await page.getByLabel('任务指令').press('Enter');
  await expect(page.locator('.agent-card')).toHaveCount(5);
  await expect.poll(async()=>(await invoke('live')).busy).toBe(false);
  await expect(page.locator('.agent-card').last()).toContainText('出错');
  stage='cancel';await invoke('permissions.set',{mode:'accept-edits'});
  await page.getByLabel('任务指令').fill('开始第二组并行检查。');await page.getByLabel('任务指令').press('Enter');
  await expect(page.locator('.agent-card')).toHaveCount(8);
  await expect.poll(()=>held.size).toBe(2);
  await page.locator('.agent-card').nth(5).click();
  await expect(page.locator('.workspace-content:not(.inactive) .agent-stream')).toBeVisible();
  await page.getByRole('button',{name:'停止',exact:true}).click();
  await expect.poll(async()=>(await invoke('live')).busy).toBe(false);
  await expect(page.locator('.agent-card .status-interrupted')).toHaveCount(3);
  const all=await page.locator('.agent-card img').evaluateAll(imgs=>imgs.map(i=>({src:i.src,loaded:i.complete&&i.naturalWidth>0})));
  assert(all.every(i=>i.loaded));assert.equal(new Set(all.map(i=>i.src)).size,6);
  // Narrow layout uses the existing full workspace; Escape returns to the conversation.
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(900,720));
  await expect(page.locator('.eca-app')).toHaveClass(/workspace-full/);
  await page.keyboard.press('Escape');
  await expect(page.getByLabel('任务指令')).toBeVisible();
  await page.locator('.agent-card').first().click();
  await expect(page.locator('.workspace-panel')).toBeVisible();await capture('compact');
  await page.keyboard.press('Escape');await expect(page.getByLabel('任务指令')).toBeVisible();
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1440,960));
  const beforeReopen=requests;
  await invoke('project.close');await page.getByRole('button',{name:'打开项目',exact:true}).click();
  await expect(page.locator('.agent-card')).toHaveCount(8);
  assert.equal((await invoke('snapshot')).session_id,owner);
  assert.equal(requests,beforeReopen);
  assert.deepEqual(errors,[]);
  const report={version:await app.evaluate(({app})=>app.getVersion()),mode:process.env.ECA_TEST_EXE?'packaged':'development',paid_api_calls:0,local_model_requests:requests,renderer_errors:errors,marks:6,
    checks:['compact inline entries, queued and live text','Markdown tables during streaming and after completion','click child without switching main session','closing view does not stop child','reload without replay','isolated edits retained','serial child and denied authorization','child error','parent stop cancels children','six local marks decode','light/dark/narrow layout','reopen restores main and children']};
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
})().catch(async e=>{console.error(e);if(app)await capture('failure').catch(()=>{});process.exitCode=1;}).finally(async()=>{if(app){await app.evaluate(({app})=>app.exit(0)).catch(()=>{});await app.close().catch(()=>{});}for(const s of sockets)s.destroy();server.close();});
