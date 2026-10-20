// Owned hidden Electron + real runtime + local HTTP fixture; no user desktop control.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents',home=fs.mkdtempSync(path.join(base,'side-clay-'));
const project=path.join(home,'陶土侧聊 项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/sidechat-clay');fs.mkdirSync(output,{recursive:true});
const requests=[],sockets=new Set(),errors=[];let app,hold;
const server=http.createServer(async(req,res)=>{
  let raw='';for await(const c of req)raw+=c;const body=JSON.parse(raw);requests.push(body);
  const history=body.messages.filter(m=>!String(m.content||'').startsWith('[Runtime guidance]'));
  const prompt=history.findLast(m=>m.role==='user')?.content||'';
  if(prompt==='失败场景'){res.writeHead(500,{'Content-Type':'application/json'});res.end('{"error":{"message":"Local test connection failed"}}');return;}
  const chunk=text=>res.write('data: '+JSON.stringify({choices:[{index:0,delta:{content:text},finish_reason:null}]})+'\n\n');
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  if(prompt==='持续输出'){chunk('我正在梳理当前任务的背景与约束。');hold=res;return;}
  chunk('可以先把问题拆开，再决定下一步。\n\n| 检查项 | 建议 |\n| --- | --- |\n| 模型连接 | 确认服务端点与模型名称 |\n| 会话恢复 | 查看上次保存的任务记录 |\n\n讨论结论可以放进主对话草稿，确认后再执行。');
  res.end('data: '+JSON.stringify({choices:[{index:0,delta:{},finish_reason:'stop'}]})+'\n\ndata: [DONE]\n\n');
});
server.on('connection',s=>{sockets.add(s);s.on('close',()=>sockets.delete(s));});
async function capture(name,panel=false){
  const png=await app.evaluate(async({BrowserWindow},panel)=>{
    const wc=BrowserWindow.getAllWindows()[0].webContents;
    await wc.executeJavaScript('document.fonts.ready.then(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))');
    const rect=panel?await wc.executeJavaScript("(()=>{const r=document.querySelector('.workspace-panel').getBoundingClientRect();return{x:Math.round(r.x),y:Math.round(r.y),width:Math.floor(r.width),height:Math.floor(r.height)}})()"):undefined;
    await wc.capturePage(rect,{stayHidden:true,stayAwake:true});
    await new Promise(r=>setTimeout(r,180));
    return (await wc.capturePage(rect,{stayHidden:true,stayAwake:true})).toPNG().toString('base64');
  },panel);fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(png,'base64'));
}
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const env={...process.env};
  for(const key of Object.keys(env))if(key.startsWith('ECA_')||/API_KEY|API_BASE|BASE_URL|MODEL_NAME|PYTHONHOME|PYTHONPATH/.test(key))delete env[key];
  Object.assign(env,{TEMP:base,TMP:base,ECA_DESKTOP_DATA_HOME:path.join(home,'app'),ECA_DESKTOP_TEST_HIDDEN:'1',ECA_PYTHON:path.resolve('.venv/Scripts/python.exe'),NO_PROXY:'127.0.0.1,localhost',no_proxy:'127.0.0.1,localhost'});
  delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch(process.env.ECA_TEST_EXE?{executablePath:process.env.ECA_TEST_EXE,args:[],env}:{args:['.'],env});
  const page=await app.firstWindow();page.on('pageerror',e=>errors.push(String(e)));
  await app.evaluate(({BrowserWindow,dialog},project)=>{const win=BrowserWindow.getAllWindows()[0];win.setContentSize(1440,960);win.webContents.setBackgroundThrottling(false);dialog.showOpenDialog=async()=>({canceled:false,filePaths:[project]});},project);
  const invoke=(method,params={})=>page.evaluate(({method,params})=>window.eca.invoke(method,params),{method,params});
  const url=`http://127.0.0.1:${server.address().port}/v1`;
  let config=await invoke('config.save',{name:'快速讨论',model:'clay-chat-local',api_format:'openai',base_url:url,no_auth:true});
  const first=config.connections[0].id;await invoke('config.default',{id:first});
  config=await invoke('config.save',{name:'长名称布局检查',model:'a-long-provider-name/long-model-name-for-layout-check',api_format:'openai',base_url:url,no_auth:true});
  await page.getByRole('button',{name:'打开项目',exact:true}).click();
  await page.reload();await page.getByRole('button',{name:'新建侧边聊天',exact:true}).click();
  const input=page.getByLabel('侧边聊天输入'),model=page.getByRole('button',{name:'侧聊模型',exact:true});
  await expect(model).toBeEnabled();
  const noOverflow=async()=>{
    const values=await page.locator('.side-chat,.side-context,.side-composer,.side-compose-area').evaluateAll(nodes=>nodes.map(el=>({name:el.className,ok:el.scrollWidth<=el.clientWidth+1})));
    assert(values.every(v=>v.ok),JSON.stringify(values));
  };
  for(const theme of ['light','dark']){
    await app.evaluate(({nativeTheme},theme)=>{nativeTheme.themeSource=theme;},theme);await page.emulateMedia({colorScheme:theme});
    await page.waitForTimeout(350);
    const channel=await page.locator('.side-starters>button').first().evaluate(el=>Number(getComputedStyle(el).backgroundColor.match(/\d+/)[0]));
    assert(theme==='dark'?channel<100:channel>200,'starter buttons follow theme');
    await noOverflow();await capture('empty-'+theme);
    await capture('panel-'+theme,true);
  }
  await app.evaluate(({nativeTheme})=>{nativeTheme.themeSource='light';});await page.emulateMedia({colorScheme:'light'});
  await page.getByRole('button',{name:'梳理进展',exact:true}).click();
  await expect(input).toHaveValue(/已完成的工作/);assert.equal(requests.length,0,'starter only fills the draft');
  await expect(input).toBeFocused();
  await page.getByRole('button',{name:'更新上下文',exact:true}).click();
  await expect(input).toHaveValue(/已完成的工作/);
  await model.click();await expect(page.getByRole('dialog',{name:'侧聊模型选择'})).toBeVisible();await capture('model-menu');
  await page.keyboard.press('Escape');await expect(model).toBeFocused();await expect(page.locator('.workspace-panel')).toBeVisible();
  await model.click();await page.keyboard.press('ArrowDown');await page.keyboard.press('End');await page.keyboard.press('Enter');
  await expect(model).toContainText('long-model-name');await noOverflow();await page.keyboard.press('Escape');
  await model.click();await page.getByRole('option',{name:/快速讨论/}).click();await expect(model).toContainText('clay-chat-local');await page.keyboard.press('Escape');
  await input.fill('多行');await input.press('Shift+Enter');await input.pressSequentially('讨论');assert.equal(requests.length,0);
  await input.dispatchEvent('compositionstart');await input.dispatchEvent('keydown',{key:'Enter',code:'Enter',isComposing:true});assert.equal(requests.length,0);
  await input.dispatchEvent('compositionend');await page.waitForTimeout(110);
  await input.press('Enter');
  await expect(page.locator('.side-message.assistant table')).toBeVisible({timeout:20000});
  await expect(page.locator('.side-send')).toBeDisabled();await noOverflow();await capture('conversation-light');
  await page.getByRole('button',{name:'放入主对话草稿',exact:true}).click();await expect(page.getByLabel('任务指令')).toHaveValue(/来自侧边聊天/);
  await input.fill('失败场景');await input.press('Enter');await expect(page.locator('.side-error')).toBeVisible({timeout:20000});await capture('error-light');
  await input.fill('持续输出');await input.press('Enter');await expect(page.getByRole('button',{name:'停止侧聊',exact:true})).toBeVisible();await expect(model).toBeDisabled();
  await page.getByRole('button',{name:'停止侧聊',exact:true}).click();await expect(model).toBeEnabled();
  const before=requests.length;await page.reload();await expect(page.locator('.side-chat')).toBeVisible();assert.equal(requests.length,before);
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1200,780));
  await noOverflow();await capture('narrow-panel');
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(900,720));
  await noOverflow();await capture('expanded-panel');await page.keyboard.press('Escape');await expect(page.getByLabel('任务指令')).toBeVisible();
  assert.deepEqual(errors,[]);
  const mode=process.env.ECA_TEST_MODE||(process.env.ECA_TEST_EXE?'packaged':'development');
  const report={version:await app.evaluate(({app})=>app.getVersion()),mode,paid_api_calls:0,requests:requests.length,renderer_errors:errors,checks:['light/dark/360px panel/expanded workspace','starter drafts without sending','context refresh retains draft','keyboard model menu, Escape and long model names','Enter/Shift+Enter/IME','Markdown tables and attach to main draft','errors and cancellation','reload without replay']};
  fs.writeFileSync(path.join(output,`report-${mode}.json`),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
})().catch(async e=>{console.error(e);if(app)await capture('failure').catch(()=>{});process.exitCode=1;}).finally(async()=>{hold?.destroy();if(app){await app.evaluate(({app})=>app.exit(0)).catch(()=>{});await app.close().catch(()=>{});}for(const s of sockets)s.destroy();server.close();});
