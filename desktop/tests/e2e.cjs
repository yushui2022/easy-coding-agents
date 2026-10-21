// Real Electron + local HTTP model fixture. No paid API and no renderer mocks.
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const os = require('node:os');
const {execFileSync} = require('node:child_process');
process.chdir(path.resolve(__dirname,'..'));
const artifact = path.resolve('../output/playwright');
fs.mkdirSync(artifact,{recursive:true});
const tempBase = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : (process.env.TEMP || os.tmpdir());
fs.mkdirSync(tempBase,{recursive:true});
process.env.ELECTRON_CACHE ||= fs.existsSync('G:/') ? 'G:/DevCache/electron' : path.join(tempBase,'electron');
const temp = fs.mkdtempSync(path.join(tempBase,'eca-desktop-e2e-'));
const project = path.join(temp,'中文 项目');
fs.mkdirSync(project);
const requests=[];
let catalogueRequests=0;
let catalogueMode='normal';
let releaseCatalogue;
let delay=false;
let modelError=false;
let targetFile='hello.txt';
let shellIssued=false;
let sockets=new Set();
const server=http.createServer(async(req,res)=>{
  if(req.headers.authorization!=='Bearer desktop-fixture-credential'){res.writeHead(401);res.end('Missing fixture credential');return;}
  if(req.method==='GET'&&req.url==='/v1/models') {
    catalogueRequests++;
    if(catalogueMode==='unavailable'){res.writeHead(404);res.end();return;}
    const respond=ids=>{res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({data:ids.map(id=>({id}))}));};
    if(catalogueMode==='hold'){releaseCatalogue=()=>respond(['stale-model']);return;}
    respond(['fixture','fixture-secondary']);return;
  }
  let raw=''; for await(const chunk of req)raw+=chunk;
  const body=JSON.parse(raw);requests.push({stream:!!body.stream});
  console.log('Fixture request', requests.length, body.messages?.map(m=>m.role).join(','), Date.now());
  if(!body.stream){res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({choices:[{message:{role:'assistant',content:'OK'}}]}));return;}
  if(modelError){res.writeHead(401,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'Fixture rejected the model request',type:'authentication_error'}}));return;}
  if(delay)return;
  const hasResult=body.messages.some(message=>message.role==='tool');
  // One follow-up shell call keeps the approval-mode coverage that the removed
  // verification panel used to provide: a command still needs its own approval.
  const savedHello=body.messages.some(message=>message.role==='tool'&&String(message.content).includes('Saved hello.txt'));
  let delta={content:'已完成修改，等待检查。'};
  if(!hasResult)delta={tool_calls:[{index:0,id:'fixture-write-'+requests.length,type:'function',function:{name:'write',arguments:JSON.stringify({path:targetFile,content:'hello'})}}]};
  else if(savedHello&&!shellIssued){shellIssued=true;delta={tool_calls:[{index:0,id:'fixture-shell-'+requests.length,type:'function',function:{name:'shell',arguments:JSON.stringify({command:"Write-Output 'shell ok'"})}}]};}
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  for(const [piece,reason] of [[delta,null],[{},delta.tool_calls?'tool_calls':'stop']])res.write('data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',created:0,model:'fixture',choices:[{index:0,delta:piece,finish_reason:reason}]})+'\n\n');
  res.end('data: [DONE]\n\n');
});
server.on('connection',socket=>{sockets.add(socket);socket.on('close',()=>sockets.delete(socket));});
let application;
const env={...process.env,ECA_DESKTOP_DATA_HOME:path.join(temp,'app-data'),ECA_DESKTOP_TEST_HIDDEN:'1',NO_PROXY:'127.0.0.1,localhost',no_proxy:'127.0.0.1,localhost'};
delete env.ELECTRON_RUN_AS_NODE;
if(process.env.ECA_TEST_EXE) {
  env.PATH = `${process.env.SystemRoot}\\System32;${process.env.SystemRoot}\\System32\\WindowsPowerShell\\v1.0;${process.env.SystemRoot}`;
  delete env.Path;
  delete env.PYTHONPATH;
  delete env.PYTHONHOME;
}
for(const name of Object.keys(env))if((name.startsWith('ECA_')&&!['ECA_DESKTOP_DATA_HOME','ECA_DESKTOP_TEST_HIDDEN','ECA_PYTHON'].includes(name))||['OPENAI_API_KEY','OPENAI_BASE_URL','ANTHROPIC_API_KEY','ANTHROPIC_BASE_URL','MODELSCOPE_API_KEY','MODEL_NAME'].includes(name))delete env[name];
const errors=[];
const report={mode:process.env.ECA_TEST_EXE?'packaged':'development',executable_path:process.env.ECA_TEST_EXE || null,project,paid_api_calls:0};
async function capture(name){
  // Hidden windows need Electron's capture API to avoid compositor/occlusion stalls.
  // stayHidden keeps the isolated test window off the user's desktop.
  const encoded=await application.evaluate(async({BrowserWindow})=>{
    const contents=BrowserWindow.getAllWindows()[0].webContents;
    await contents.executeJavaScript('document.fonts.ready.then(async()=>{await Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{})));await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));})');
    const image=await contents.capturePage(undefined,{stayHidden:true,stayAwake:true});
    return image.toPNG().toString('base64');
  });
  fs.writeFileSync(path.join(artifact,name),Buffer.from(encoded,'base64'));
}
async function checkContrast(page,theme){
  await page.evaluate(()=>Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{}))));
  const ratios=await page.evaluate(()=>{
    const luminance=color=>{
      const channels=color.match(/[\d.]+/g).slice(0,3).map(Number).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;});
      return channels[0]*.2126+channels[1]*.7152+channels[2]*.0722;
    };
    return ['.open-project','.session-list .selected','.status','.model-chip','.verification>span','.composer-meta'].map(selector=>{
      const element=document.querySelector(selector);
      let parent=element,bg;
      do{bg=getComputedStyle(parent).backgroundColor;parent=parent.parentElement;}while(parent&&(bg==='transparent'||bg==='rgba(0, 0, 0, 0)'));
      const a=luminance(getComputedStyle(element).color),b=luminance(bg);
      return {selector,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
    });
  });
  for(const {selector,ratio} of ratios)assert(ratio>=4.5,theme+' '+selector+' contrast '+ratio);
  report[theme+'_text_contrast']=ratios;
}
async function backendProcess(){
  const parent=await application.evaluate(()=>process.pid);
  const command=`Get-CimInstance Win32_Process -Filter "ParentProcessId = ${parent}" | Where-Object { $_.Name -in @('python.exe','eca-backend.exe') } | Select-Object ProcessId,WorkingSetSize | ConvertTo-Json -Compress`;
  const raw=execFileSync('powershell.exe',['-NoProfile','-Command',command],{encoding:'utf8',windowsHide:true});
  if(!raw.trim())throw new Error('No owned backend found for Electron main PID '+parent);
  const result=JSON.parse(raw);
  const rows=Array.isArray(result)?result:[result];
  assert.equal(rows.length,1,'Exactly one backend must belong to this test application');
  return rows[0];
}
async function launch(){
  const start=Date.now();
  application=await electron.launch(process.env.ECA_TEST_EXE?{executablePath:process.env.ECA_TEST_EXE,args:[],env}:{args:['.'],env});
  const page=await application.firstWindow();
  await application.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].webContents.setBackgroundThrottling(false));
  application.process().on('exit', code=>console.log('Electron exit',code));
  application.process().stderr.on('data', data=>console.log('Electron:',String(data).slice(0,1000)));
  page.on('framenavigated',frame=>console.log('Navigation',frame.url()));
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')console.log('Renderer error:',message.text());});
  await expect(page.getByRole('button',{name:'模型与设置'})).toBeVisible();
  const elapsed=Date.now()-start;
  if(report.first_window_ms===undefined)report.first_window_ms=elapsed;else report.reopen_window_ms=elapsed;
  await application.evaluate(({dialog},folder)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[folder]});},project);
  return page;
}
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let page=await launch();
  const draft='创建 hello.txt，内容为 hello。';
  await expect(page.getByLabel('任务指令')).toBeEnabled();
  await page.getByLabel('任务指令').fill(draft);
  await page.reload();
  await expect(page.getByLabel('任务指令')).toHaveValue(draft);
  await expect(page.locator('.inspector')).toHaveCount(0);
  // A cancelled native directory picker must keep the draft and must not run a task.
  await application.evaluate(({dialog})=>{dialog.showOpenDialog=async()=>({canceled:true,filePaths:[]});});
  await page.getByRole('button',{name:'发送任务'}).click();
  await expect(page.getByRole('button',{name:'发送任务'})).toBeEnabled();
  await expect(page.getByLabel('任务指令')).toHaveValue(draft);
  assert.equal(requests.length,0);
  report.pre_project_draft_and_reload='passed';
  report.cancel_picker_preserves_draft='passed';
  await capture('desktop-welcome.png');
  await page.getByRole('button',{name:'模型与设置'}).click();
  await page.getByLabel('API 地址').fill('http://127.0.0.1:'+server.address().port+'/v1');
  await expect(page.getByRole('button',{name:'保存配置',exact:true})).toBeDisabled();
  await page.getByLabel('API 密钥').fill('invalid-fixture-credential');
  await expect(page.locator('.catalogue-status')).toContainText('密钥无效',{timeout:10000});
  await page.getByLabel('API 密钥').fill('desktop-fixture-credential');
  await expect(page.getByLabel('服务返回的模型')).toBeEnabled({timeout:10000});
  assert.equal(requests.length,0,'Model discovery must not generate a paid completion');
  catalogueMode='unavailable';
  await page.getByRole('button',{name:'刷新模型列表'}).click();
  await expect(page.locator('.catalogue-status')).toContainText('手动填写');
  await page.locator('.manual-model summary').click();
  await page.getByLabel('模型名称').fill('fixture');
  await expect(page.getByRole('button',{name:'保存配置',exact:true})).toBeEnabled();
  catalogueMode='normal';
  await page.getByRole('button',{name:'刷新模型列表'}).click();
  await expect(page.getByLabel('服务返回的模型')).toBeEnabled();
  await page.locator('.manual-model summary').click();
  report.automatic_model_discovery_and_manual_fallback='passed';
  await page.getByLabel('服务返回的模型',{exact:false}).selectOption('fixture');
  await page.getByRole('button',{name:'保存配置',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('配置已保存');
  const stored=fs.readFileSync(path.join(env.ECA_DESKTOP_DATA_HOME,'preferences.json'),'utf8');
  assert(!stored.includes('desktop-fixture-credential'));
  await page.getByRole('button',{name:'测试连接',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('[role=status]')?.textContent.includes('连接成功'),null,{timeout:30000});
  console.log('Connection passed');
  await page.getByRole('button',{name:'关闭设置'}).click();
  await expect(page.locator('.model-chip')).toContainText('fixture');
  // Escape closes the native dialog and restores focus to its opener.
  await page.locator('.model-chip').click();
  await expect(page.getByRole('dialog',{name:'选择模型',exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('.model-chip')).toBeFocused();
  report.modal_keyboard_focus='passed';
  const projectEnv='ECA_MODEL=Qwen/old-project-model\nECA_BASE_URL=https://project.invalid/v1\nECA_API_KEY=project-only-fixture-key\n';
  fs.writeFileSync(path.join(project,'.env'),projectEnv);
  await application.evaluate(({dialog},folder)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[folder]});},project);
  const beforeSelection=requests.length;
  // Synthetic composition events exercise the Chinese IME guard, not a model or UI mock.
  await page.getByLabel('任务指令').dispatchEvent('keydown',{key:'Enter',isComposing:true});
  await expect(page.locator('.inspector')).toHaveCount(0);
  await page.getByRole('button',{name:'发送任务'}).click();
  await expect(page.locator('.workspace-title')).toContainText('中文 项目');
  await expect(page.locator('.model-chip')).toContainText('fixture');
  await expect(page.getByLabel('任务指令')).toHaveValue(draft);
  assert.equal(requests.length,beforeSelection,'Selecting a project must not submit the draft');
  report.select_project_requires_explicit_send='passed';
  // Add a second encrypted connection and explicitly pin it to this project.
  await page.getByRole('button',{name:'模型与设置'}).click();
  await page.getByRole('button',{name:'添加连接',exact:true}).click();
  await page.getByLabel('连接名称',{exact:true}).fill('第二个连接');
  await page.getByLabel('API 地址').fill('http://127.0.0.1:'+server.address().port+'/v1');
  catalogueMode='hold';
  await page.getByLabel('API 密钥').fill('desktop-fixture-credential');
  await expect.poll(()=>!!releaseCatalogue).toBe(true);
  // Switch connection while a catalogue request is in flight. Its response is obsolete.
  catalogueMode='normal';
  await page.getByRole('navigation',{name:'已保存的模型连接'}).getByRole('button').first().click();
  await expect(page.getByLabel('服务返回的模型')).toBeEnabled({timeout:10000});
  releaseCatalogue();releaseCatalogue=undefined;
  await expect(page.getByLabel('服务返回的模型').locator('option')).toHaveText(['当前模型：fixture','fixture','fixture-secondary']);
  await page.getByRole('button',{name:'添加连接',exact:true}).click();
  await expect(page.getByLabel('服务返回的模型')).toBeEnabled({timeout:10000});
  await page.getByLabel('服务返回的模型').selectOption('fixture-secondary');
  report.stale_catalogue_response_ignored='passed';
  await page.getByRole('button',{name:'保存配置',exact:true}).click();
  await expect(page.locator('.config-status')).toContainText('配置已保存');
  await capture('desktop-model-connections.png');
  await page.getByRole('button',{name:'用于当前项目',exact:true}).click();
  await expect(page.locator('.model-chip')).toContainText('fixture-secondary');
  await page.getByRole('button',{name:'新建会话',exact:true}).click();
  await expect(page.locator('.model-chip')).toContainText('fixture-secondary');
  await page.reload();
  await expect(page.locator('.model-chip')).toContainText('fixture-secondary');
  await page.getByRole('button',{name:'打开项目',exact:true}).click();
  await expect(page.locator('.model-chip')).toContainText('fixture-secondary');
  // The model picker no longer carries an explicit 「跟随桌面默认 / 沿用项目配置」 row
  // (simplified on request); pinning is exercised above through 用于当前项目.
  await page.keyboard.press('Escape');
  await page.locator('.model-chip').click();
  await capture('desktop-model-picker.png');
  await page.keyboard.press('Escape');
  assert.equal(fs.readFileSync(path.join(project,'.env'),'utf8'),projectEnv);
  report.desktop_default_over_project_env='passed';
  report.multiple_connections_and_project_pin='passed';
  report.explicit_project_configuration='passed';
  report.model_catalogue_requests=catalogueRequests;
  await page.getByRole('button',{name:'任务详情',exact:true}).click();
  await page.getByRole('button',{name:'审查',exact:true}).click();
  // The narrow workspace replaces the main pane; Escape returns to the chat.
  await application.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(900,680));
  await expect(page.locator('.workspace-panel')).toBeVisible();
  await expect(page.locator('.conversation')).toBeHidden();
  await page.locator('.review-extra summary').filter({hasText:'用量'}).click();
  await expect(page.locator('.metric').last()).toContainText('未知');
  await page.getByRole('tab',{name:'文件修改',exact:true}).click();
  await capture('desktop-narrow-details.png');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'任务详情',exact:true})).toBeFocused();
  const dimensions=await page.evaluate(()=>({width:innerWidth,height:innerHeight,scroll:document.documentElement.scrollWidth,
    input:document.querySelector('#prompt').getBoundingClientRect().toJSON(),send:document.querySelector('.send-button').getBoundingClientRect().toJSON()}));
  assert(dimensions.scroll<=dimensions.width);
  assert(dimensions.input.bottom<dimensions.height&&dimensions.send.bottom<dimensions.height);
  await capture('desktop-narrow.png');
  await application.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(1360,860));
  await page.getByRole('button',{name:'任务详情',exact:true}).click();
  await expect(page.locator('.workspace-review')).toBeVisible();
  await page.getByRole('button',{name:'收起任务详情'}).click();
  await expect(page.locator('.workspace-review')).toBeHidden();
  await page.getByRole('button',{name:'任务详情',exact:true}).click();
  await expect(page.locator('.workspace-review')).toBeVisible();
  report.responsive_details_and_controls='passed';
  await expect(page.getByLabel('任务指令')).toBeEnabled();
  const taskInput=page.getByLabel('任务指令');
  const beforeKeyboard=requests.length;
  await taskInput.fill('第一行');
  await taskInput.press('Shift+Enter');
  await taskInput.press('x');
  await expect(taskInput).toHaveValue('第一行\nx');
  await taskInput.dispatchEvent('compositionstart');
  await taskInput.dispatchEvent('keydown',{key:'Enter'});
  await taskInput.dispatchEvent('compositionend');
  await taskInput.dispatchEvent('keydown',{key:'Enter',keyCode:229});
  await taskInput.dispatchEvent('keydown',{key:'Enter',repeat:true});
  assert.equal(requests.length,beforeKeyboard,'IME confirmation, newline and key repeat must not send');
  await taskInput.fill('创建 hello.txt，内容为 hello。');
  // The next intentional Enter is after the 50 ms IME commit guard.
  await page.waitForTimeout(60);
  await taskInput.press('Enter');
  report.enter_send_shift_enter_and_ime='passed';
  await expect(page.getByRole('button',{name:'本次允许'})).toBeVisible();
  await page.locator('.messages').evaluate(el=>{el.scrollTop=0;});
  const approvalPlacement=await page.getByRole('button',{name:'本次允许'}).boundingBox();
  const viewport=page.viewportSize()||await page.evaluate(()=>({width:innerWidth,height:innerHeight}));
  assert(approvalPlacement.y>=0&&approvalPlacement.y+approvalPlacement.height<viewport.height,'Approval remains visible above composer while transcript is scrolled');
  report.approval_docked_outside_scrollback='passed';
  await capture('desktop-approval.png');
  // Reload during an approval must retain it without resubmitting the model request.
  const before=requests.length;
  await page.reload();
  await expect(page.getByRole('button',{name:'本次允许'})).toBeVisible();
  assert.equal(requests.length,before);
  await application.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(900,680));
  await expect(page.locator('.workspace-panel')).toBeHidden();
  await expect(page.locator('.conversation')).toBeVisible();
  await page.waitForFunction(()=>innerWidth<=900&&!document.querySelector('.eca-app').classList.contains('workspace-full'));
  const narrowApproval=await page.evaluate(()=>({height:innerHeight,width:innerWidth,scroll:document.documentElement.scrollWidth,
    approval:document.querySelector('.approval .primary').getBoundingClientRect().toJSON(),stop:document.querySelector('.stop-button').getBoundingClientRect().toJSON()}));
  assert(narrowApproval.scroll<=narrowApproval.width&&narrowApproval.approval.y>=0&&narrowApproval.approval.bottom<narrowApproval.height&&narrowApproval.stop.bottom<narrowApproval.height);
  await capture('desktop-narrow-approval.png');
  await application.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(1360,860));
  await page.waitForFunction(()=>innerWidth>1179);
  await page.getByRole('button',{name:'任务详情',exact:true}).click();
  await expect(page.locator('.workspace-review')).toBeVisible();
  report.narrow_approval_and_stop_remain_visible='passed';
  await page.getByLabel('审批模式').selectOption('accept-edits');
  await page.waitForFunction(()=>document.querySelector('.approval')?.textContent.includes('Run shell'),null,{timeout:30000});
  console.log('Shell approval reached');
  await expect(page.getByRole('button',{name:'本次允许'})).toBeVisible();
  await page.getByLabel('审批模式').selectOption('full-access');
  await expect(page.getByRole('dialog',{name:'开启完全访问',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'开启完全访问',exact:true}).click();
  await expect(page.locator('.tool-record')).toHaveCount(2);
  await expect(page.locator('.tool-record pre')).toHaveCount(0);
  await page.locator('.tool-record summary').first().click();
  await expect(page.locator('.tool-record').first()).toContainText('Saved hello.txt');
  await page.locator('.tool-record summary').first().click();
  await expect(page.locator('.tool-record pre')).toHaveCount(0);
  report.paired_tool_log_is_lazy='passed';
  assert.equal(fs.readFileSync(path.join(project,'hello.txt'),'utf8'),'hello');
  await page.getByRole('button',{name:'hello.txt',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'文件差异'})).toContainText('+hello');
  await page.getByRole('button',{name:'关闭差异'}).click();
  await checkContrast(page,'light');
  await capture('desktop-workspace.png');
  await page.emulateMedia({colorScheme:'dark'});
  await checkContrast(page,'dark');
  await capture('desktop-workspace-dark.png');
  await page.emulateMedia({colorScheme:'light'});
  report.memory=await application.evaluate(({app})=>app.getAppMetrics().map(p=>({type:p.type,workingSetKB:p.memory.workingSetSize})));
  if(process.platform==='win32')report.backend_working_set_bytes=Number((await backendProcess()).WorkingSetSize);
  report.round_trip='passed';report.reload_approval='passed';
  report.approval_modes_release_pending_and_preserve_shell_confirmation='passed';
  await page.reload();
  await expect(page.getByLabel('审批模式')).toHaveValue('full-access');
  // Verify that externally changed files cannot be overwritten by undo.
  fs.writeFileSync(path.join(project,'hello.txt'),'external');
  await page.getByRole('button',{name:'撤销 hello.txt'}).click();
  await expect(page.getByRole('alert')).toContainText('refusing to overwrite');
  assert.equal(fs.readFileSync(path.join(project,'hello.txt'),'utf8'),'external');
  await page.getByRole('button',{name:'关闭错误'}).click();
  fs.writeFileSync(path.join(project,'hello.txt'),'hello');
  await page.getByRole('button',{name:'审查 hello.txt'}).click();
  await expect(page.locator('.change-bottom')).toContainText('已审查');
  await application.close();application=undefined;
  page=await launch();
  await page.getByRole('button',{name:'打开项目',exact:false}).first().click();
  await expect(page.locator('.messages')).toContainText('创建 hello.txt');
  await page.getByRole('button',{name:'任务详情',exact:true}).click();
  await page.getByRole('button',{name:'审查',exact:true}).click();
  await expect(page.locator('.change-bottom')).toContainText('已审查');
  report.resume='passed';
  await expect(page.getByLabel('审批模式')).toHaveValue('ask');
  report.full_access_resets_on_reopen='passed';
  await page.getByLabel('审批模式').selectOption('ask');
  // Cancel an HTTP request which never returns. This must not wait for network timeout.
  delay=true;
  const priorRequests=requests.length;
  await page.getByLabel('任务指令').fill('等待模型');
  await page.getByRole('button',{name:'发送任务'}).click();
  await expect(page.getByRole('button',{name:'停止',exact:true})).toBeVisible();
  const deadline=Date.now()+10000;
  while(requests.length===priorRequests && Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,20));
  assert(requests.length>priorRequests,'The request must reach the server before testing cancellation');
  await expect(page.locator('.run-activity')).toContainText('等待模型响应');
  await page.locator('.activity-mark').evaluate(image=>image.decode());
  await capture('desktop-activity-waiting.png');
  report.waiting_model_feedback='passed';
  const cancelStart=Date.now();
  await page.getByRole('button',{name:'停止',exact:true}).click();
  await expect(page.locator('.status')).toContainText('已停止',{timeout:5000});
  report.cancel_ms=Date.now()-cancelStart;
  delay=false;modelError=true;
  await page.getByLabel('任务指令').fill('模拟模型错误');
  await page.getByRole('button',{name:'发送任务'}).click();
  await expect(page.locator('.status')).toContainText('遇到问题',{timeout:10000});
  await expect(page.getByRole('alert')).toContainText('401');
  report.model_error='passed';
  modelError=false;targetFile='denied.txt';
  await page.getByRole('button',{name:'新建会话',exact:true}).click();
  await page.getByLabel('任务指令').fill('创建 denied.txt，内容为 hello。');
  await page.getByRole('button',{name:'发送任务'}).click();
  await expect(page.getByRole('button',{name:'本次允许'})).toBeVisible();
  // The native close prompt must keep the original window/task when asked to continue.
  await application.evaluate(({dialog,BrowserWindow})=>{
    globalThis.closePromptShown=false;
    dialog.showMessageBox=async()=>{globalThis.closePromptShown=true;return {response:0,checkboxChecked:false};};
    BrowserWindow.getAllWindows()[0].close();
  });
  await expect.poll(()=>application.evaluate(()=>globalThis.closePromptShown)).toBe(true);
  await expect(page.getByRole('button',{name:'本次允许'})).toBeVisible();
  report.close_keeps_active_window='passed';
  await page.getByRole('button',{name:'拒绝',exact:true}).click();
  await expect(page.locator('.status')).toContainText('等待指令',{timeout:10000});
  report.denial_continues_task='passed';
  assert(!fs.existsSync(path.join(project,'denied.txt')));
  if(process.platform==='win32'){
    // Kill only the Python child belonging to this test app. No task may replay on restart.
    delay=true;
    const prior=requests.length;
    await page.getByLabel('任务指令').fill('模拟后端中断');
    await page.getByRole('button',{name:'发送任务'}).click();
    await expect.poll(()=>requests.length).toBeGreaterThan(prior);
    process.kill(Number((await backendProcess()).ProcessId));
    await expect(page.getByRole('alert')).toContainText('后端已退出',{timeout:10000});
    const count=requests.length;
    await page.getByRole('button',{name:'打开项目',exact:false}).first().click();
    await expect(page.locator('.status')).toContainText('已停止',{timeout:15000});
    assert.equal(requests.length,count);
    await expect(page.getByRole('button',{name:'发送任务'})).toBeVisible();
    report.backend_crash_recovery_without_replay='passed';
    delay=false;modelError=true;
    await page.getByLabel('任务指令').fill('重启后再次模拟模型错误');
    await page.getByRole('button',{name:'发送任务'}).click();
    await expect(page.getByRole('alert')).toContainText('401',{timeout:10000});
    await expect(page.locator('.status')).toContainText('遇到问题');
    modelError=false;
    report.errors_after_backend_restart='passed';
  }
  delay=true;
  const beforeClose=requests.length;
  await page.getByLabel('任务指令').fill('测试停止并退出');
  await page.getByRole('button',{name:'发送任务'}).click();
  await expect.poll(()=>requests.length).toBeGreaterThan(beforeClose);
  await Promise.all([
    application.waitForEvent('close',{timeout:15000}),
    application.evaluate(({dialog,BrowserWindow})=>{
      dialog.showMessageBox=async()=>({response:1,checkboxChecked:false});
      BrowserWindow.getAllWindows()[0].close();
    })
  ]);
  application=undefined;
  const countAfterClose=requests.length;
  page=await launch();
  await page.getByRole('button',{name:'打开项目',exact:false}).first().click();
  await expect(page.locator('.status')).toContainText('已停止');
  assert.equal(requests.length,countAfterClose);
  report.close_stops_and_recovers='passed';
  assert.deepEqual(errors,[]);
  report.renderer_errors=errors;report.requests=requests.length;
  await application.close();application=undefined;
  fs.writeFileSync(path.join(artifact,process.env.ECA_TEST_EXE?'desktop-packaged-report.json':'desktop-e2e-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
})().catch(async error=>{
  console.error(error);
  if(application){try{const page=await application.firstWindow();console.error((await page.locator('body').innerText()).slice(-5000));await capture('desktop-failure.png');}catch{}}
  process.exitCode=1;
}).finally(async()=>{if(application){await application.evaluate(({app})=>app.exit(0)).catch(()=>{});await application.close().catch(()=>{});}for(const socket of sockets)socket.destroy();server.close();});
