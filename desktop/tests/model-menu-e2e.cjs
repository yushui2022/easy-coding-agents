// Owned hidden Electron with real Python/HTTP; never operates a user window or API.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents',home=fs.mkdtempSync(path.join(base,'model-menu-'));
const project=path.join(home,'模型选择 项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/model-menu');fs.mkdirSync(output,{recursive:true});
let app;const requests=[],sockets=new Set(),errors=[];
const server=http.createServer(async(req,res)=>{
  let raw='';for await(const part of req)raw+=part;
  const payload=JSON.parse(raw);requests.push(payload);
  const prompt=payload.messages.filter(m=>!String(m.content||'').startsWith('[Runtime guidance]')).findLast(m=>m.role==='user')?.content;
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  const chunk={id:'local',object:'chat.completion.chunk',created:0,model:payload.model,choices:[{index:0,delta:{content:'本地模型已收到这次请求。'},finish_reason:prompt==='等待取消'?null:'stop'}]};
  res.write('data: '+JSON.stringify(chunk)+'\n\n');
  if(prompt!=='等待取消')res.end('data: [DONE]\n\n');
});
server.on('connection',s=>{sockets.add(s);s.on('close',()=>sockets.delete(s));});
async function capture(name){
  const data=await app.evaluate(async({BrowserWindow})=>{
    const wc=BrowserWindow.getAllWindows()[0].webContents;
    await wc.executeJavaScript('document.fonts.ready.then(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))');
    await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});await new Promise(r=>setTimeout(r,220));
    return (await wc.capturePage(undefined,{stayHidden:true,stayAwake:true})).toPNG().toString('base64');
  });fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(data,'base64'));
}
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const env={...process.env};
  for(const k of Object.keys(env))if(k.startsWith('ECA_')||/API_KEY|API_BASE|BASE_URL|MODEL_NAME|PYTHONHOME|PYTHONPATH/.test(k))delete env[k];
  Object.assign(env,{TEMP:base,TMP:base,ECA_DESKTOP_TEST_HIDDEN:'1',ECA_DESKTOP_DATA_HOME:path.join(home,'app'),ECA_PYTHON:path.resolve('.venv/Scripts/python.exe'),NO_PROXY:'127.0.0.1,localhost',no_proxy:'127.0.0.1,localhost'});
  delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch(process.env.ECA_TEST_EXE?{executablePath:process.env.ECA_TEST_EXE,args:[],env}:{args:['.'],env});
  const page=await app.firstWindow();page.on('pageerror',e=>errors.push(String(e)));
  await app.evaluate(({BrowserWindow,dialog},folder)=>{const w=BrowserWindow.getAllWindows()[0];w.setContentSize(1440,960);w.webContents.setBackgroundThrottling(false);dialog.showOpenDialog=async()=>({canceled:false,filePaths:[folder]});},project);
  const call=(method,params={})=>page.evaluate(({method,params})=>window.eca.invoke(method,params),{method,params});
  const base_url=`http://127.0.0.1:${server.address().port}/v1`;
  const saved=[];
  for(const [model,name] of [['deepseek-flash','快速模型'],['deepseek-v4-pro','推理模型'],['deepseek-flash','备用连接'],['unknown-model','自定义模型']]){
    const v=await call('config.save',{model,name,base_url,api_format:'openai',no_auth:true});saved.push(v.savedId);
  }
  const [flash,pro,duplicate,unknown]=saved;
  await call('config.default',{id:flash});await page.reload();
  const main=page.getByRole('button',{name:'主对话模型',exact:true});
  await main.click();let menu=page.getByRole('dialog',{name:'选择模型',exact:true});
  await menu.getByRole('button',{name:'推理强度：高',exact:true}).click();
  await expect.poll(async()=>(await call('config.get')).model.reasoning.value).toBe('high');
  await page.keyboard.press('Escape');await expect(main).toBeFocused();
  await page.getByRole('button',{name:'打开项目',exact:true}).click();
  await expect.poll(async()=>(await call('snapshot')).settings.reasoning.value).toBe('high');
  await main.click();await menu.getByLabel('搜索模型').fill('deepseek-v4-pro');
  await expect(menu.getByRole('option')).toHaveCount(1);await menu.getByRole('option').click();
  await expect.poll(async()=>(await call('snapshot')).settings.model).toBe('deepseek-v4-pro');
  await menu.getByLabel('搜索模型').fill('');
  await expect(menu.getByRole('option',{selected:true})).toHaveCount(1);
  const slider=menu.getByRole('slider',{name:'推理强度',exact:true});
  await slider.focus();await slider.press('End');
  await expect.poll(async()=>(await call('snapshot')).settings.reasoning.value).toBe('max');
  for(const theme of ['light','dark']){
    await app.evaluate(({nativeTheme},t)=>{nativeTheme.themeSource=t;},theme);await page.emulateMedia({colorScheme:theme});await page.waitForTimeout(350);await capture('main-'+theme);
  }
  await app.evaluate(({nativeTheme})=>{nativeTheme.themeSource='light';});await page.emulateMedia({colorScheme:'light'});
  await page.keyboard.press('Escape');await page.getByLabel('任务指令').fill('主任务测试');await page.getByLabel('任务指令').press('Enter');
  await expect.poll(async()=>(await call('live')).busy).toBe(false);
  await expect.poll(()=>requests.length).toBe(1);
  assert.equal(requests[0].model,'deepseek-v4-pro');assert.equal(requests[0].reasoning_effort,'max');assert(!('thinking' in requests[0]));
  await page.getByRole('button',{name:'新建侧边聊天',exact:true}).click();
  const side=page.getByRole('button',{name:'侧聊模型',exact:true}),sideInput=page.getByLabel('侧边聊天输入');
  await expect(side).toBeEnabled();await side.click();menu=page.getByRole('dialog',{name:'侧聊模型选择',exact:true});
  await menu.getByLabel('搜索模型').fill('快速模型');await menu.getByRole('option').click();
  await menu.getByLabel('搜索模型').fill('');
  await menu.getByRole('button',{name:'推理强度：低',exact:true}).click();
  await expect(side).toContainText('低');await capture('side-light');
  await page.keyboard.press('Escape');
  await sideInput.fill('侧聊测试');await sideInput.press('Enter');
  await expect(side).toBeEnabled();await expect.poll(()=>requests.length).toBe(2);
  assert.equal(requests[1].model,'deepseek-flash');assert.equal(requests[1].reasoning_effort,'low');
  assert.equal((await call('snapshot')).settings.reasoning.value,'max');
  for(const [label,value] of [['默认',undefined],['关闭','none'],['中','medium']]){
    await side.click();await menu.getByRole('button',{name:'推理强度：'+label,exact:true}).click();await expect(side).toContainText(label);
    await page.keyboard.press('Escape');await sideInput.fill('侧聊 '+label);await sideInput.press('Enter');
    await expect(side).toBeEnabled();await expect.poll(()=>requests.at(-1).reasoning_effort).toBe(value);
    assert(!('thinking' in requests.at(-1)));
  }
  await side.click();await menu.getByLabel('搜索模型').fill('备用连接');await menu.getByRole('option').click();
  await menu.getByLabel('搜索模型').fill('');await expect(menu.getByRole('option',{selected:true})).toHaveCount(1);
  await expect(menu.getByRole('option',{selected:true})).toContainText('备用连接');
  await menu.getByRole('button',{name:'推理强度：高',exact:true}).click();await expect(side).toContainText('高');
  await page.keyboard.press('Escape');await sideInput.fill('高强度测试');await sideInput.press('Enter');await expect(side).toBeEnabled();await expect.poll(()=>requests.at(-1).reasoning_effort).toBe('high');
  const before=requests.length;await page.reload();await expect(side).toContainText('高');assert.equal(requests.length,before);
  assert.equal((await call('config.get')).recentModels[0],duplicate);
  await side.click();menu=page.getByRole('dialog',{name:'侧聊模型选择',exact:true});
  await menu.getByLabel('搜索模型').fill('not-a-real-model');await expect(menu.getByText('没有匹配的模型')).toBeVisible();
  await menu.getByLabel('搜索模型').fill('自定义模型');await menu.getByRole('option').click();
  await expect(menu.getByRole('slider')).toHaveCount(0);
  const owner=(await call('snapshot')).session_id;
  const sideState=await call('sidechat.open',{session_id:owner});
  await assert.rejects(call('sidechat.reasoning',{session_id:owner,id:sideState.id,effort:'high'}));
  await menu.getByLabel('搜索模型').fill('快速模型');await menu.getByRole('option').click();
  await menu.getByLabel('搜索模型').fill('');await menu.getByRole('button',{name:'推理强度：低',exact:true}).click();
  await expect(side).toContainText('低');await page.keyboard.press('Escape');
  await sideInput.fill('等待取消');await sideInput.press('Enter');await expect(side).toBeDisabled();
  await assert.rejects(call('sidechat.reasoning',{session_id:owner,id:sideState.id,effort:'high'}));
  await page.getByRole('button',{name:'停止侧聊',exact:true}).click();await expect(side).toBeEnabled();
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(900,720));
  await side.click();menu=page.getByRole('dialog',{name:'侧聊模型选择',exact:true});
  const bounds=await menu.evaluate(el=>{const r=el.getBoundingClientRect();return{x:r.x,right:r.right,y:r.y,bottom:r.bottom,w:innerWidth,h:innerHeight,overflow:el.scrollWidth>el.clientWidth+1};});
  assert(bounds.x>=0&&bounds.y>=0&&bounds.right<=bounds.w&&bounds.bottom<=bounds.h&&!bounds.overflow,JSON.stringify(bounds));
  await capture('side-narrow');await page.keyboard.press('Escape');await expect(menu).not.toBeVisible();await expect(page.locator('.workspace-panel')).toBeVisible();
  assert.deepEqual(errors,[]);
  const mode=process.env.ECA_TEST_MODE||(process.env.ECA_TEST_EXE?'packaged':'development');
  const report={version:await app.evaluate(({app})=>app.getVersion()),mode,paid_api_calls:0,local_requests:requests.length,renderer_errors:errors,checks:['main and side share search/recent/checkmark menu','default before opening project','six DeepSeek effort values reach HTTP payload','side changes do not change main','same-model connections have unique selection','keyboard slider/search/Escape','reload retains live selection and recent order','unknown models and busy calls reject unsupported effort','light/dark/narrow popover fits']};
  fs.writeFileSync(path.join(output,`report-${mode}.json`),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
})().catch(async e=>{console.error(e);if(app)await capture('failure').catch(()=>{});process.exitCode=1;}).finally(async()=>{if(app){await app.evaluate(({app})=>app.exit(0)).catch(()=>{});await app.close().catch(()=>{});}for(const s of sockets)s.destroy();server.close();});
