// Hidden owned Electron window, local SSE fixture only. Never touches user data.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents',home=fs.mkdtempSync(path.join(base,'concurrent-sessions-'));
const project=path.join(home,'并发 项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/concurrent-sessions');fs.mkdirSync(output,{recursive:true});
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
let app;
async function capture(name) {
  const png=await app.evaluate(async({BrowserWindow})=>{
    const wc=BrowserWindow.getAllWindows()[0].webContents;
    await wc.executeJavaScript('Promise.all([document.fonts.ready,...Array.from(document.images).map(i=>i.decode().catch(()=>{}))])');
    await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});
    await new Promise(r=>setTimeout(r,220));
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
    BrowserWindow.getAllWindows()[0].setContentSize(1360,900);
    BrowserWindow.getAllWindows()[0].webContents.setBackgroundThrottling(false);
    dialog.showOpenDialog=async()=>({canceled:false,filePaths:[folder]});
  },project);
  const invoke=(method,params={})=>page.evaluate(([method,params])=>window.eca.invoke(method,params),[method,params]);
  const config={api_format:'openai',base_url:`http://127.0.0.1:${server.address().port}/v1`,no_auth:true};
  const modelA=await invoke('config.save',{...config,model:'fixture-a',name:'模型 A'});
  const modelB=await invoke('config.save',{...config,model:'fixture-b',name:'模型 B'});
  await invoke('config.default',{id:modelA.savedId});
  await page.getByRole('button',{name:'打开项目',exact:true}).click();
  await expect.poll(async()=>(await invoke('snapshot')).project).toBe(project);
  const a=(await invoke('snapshot')).session_id;
  const input=page.getByLabel('任务指令');
  await input.fill('会话 A 写入文件');await input.press('Enter');
  await expect.poll(()=>exchanges.length).toBe(1);
  const first=exchanges[0].res;start(first);
  delta(first,{tool_calls:[{index:0,id:'write-a',type:'function',function:{name:'write',
    arguments:JSON.stringify({path:'A.txt',content:'approved in A'})}}]},'tool_calls');
  first.end('data: [DONE]\n\n');
  await expect(page.getByRole('button',{name:'本次允许',exact:true})).toBeVisible();
  await input.fill('A 独立草稿');
  await page.getByRole('button',{name:'新建会话',exact:true}).click();
  await expect.poll(async()=>(await invoke('snapshot')).session_id).not.toBe(a);
  const b=(await invoke('snapshot')).session_id;
  await expect(input).toHaveValue('');
  await expect(page.locator(`[data-session-id="${a}"]`)).toContainText('待确认');
  await invoke('model.use',{choice:modelB.savedId,session_id:b});
  await page.reload();
  await expect(page.getByRole('button',{name:'主对话模型'})).toContainText('fixture-b');
  await input.fill('会话 B 独立生成');await input.press('Enter');
  await expect.poll(()=>exchanges.length).toBe(2);
  const second=exchanges[1].res;start(second);delta(second,{content:'B_ONLY_STREAM'});
  await expect(page.locator('.stream-text')).toHaveText('B_ONLY_STREAM');
  await expect(page.locator('.session-concurrency')).toContainText('2 个会话运行中');
  await capture('two-sessions');
  await input.fill('B 独立草稿');
  await page.locator(`[data-session-id="${a}"]`).click();
  await expect(input).toHaveValue('A 独立草稿');
  await expect(page.getByRole('button',{name:'主对话模型'})).toContainText('fixture-a');
  await expect(page.locator('.stream-text')).toHaveCount(0);
  delta(second,{content:'_BACKGROUND'});
  await expect(page.getByRole('button',{name:'本次允许',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'本次允许',exact:true}).click();
  await expect.poll(()=>exchanges.length).toBe(3);
  assert.equal(fs.readFileSync(path.join(project,'A.txt'),'utf8'),'approved in A');
  start(exchanges[2].res);delta(exchanges[2].res,{content:'A_APPROVED_COMPLETE'});end(exchanges[2].res);
  await expect.poll(async()=>(await invoke('live')).busy).toBe(false);
  await expect(page.locator('.messages')).toContainText('A_APPROVED_COMPLETE');
  await expect(page.locator('.messages')).not.toContainText('B_ONLY_STREAM');
  await expect(page.getByRole('button',{name:'新建会话',exact:true})).toBeEnabled();
  await input.fill('A 再次运行');await input.press('Enter');
  await expect.poll(()=>exchanges.length).toBe(4);
  start(exchanges[3].res);delta(exchanges[3].res,{content:'A_SECOND_STREAM'});
  await page.locator(`[data-session-id="${b}"]`).click();
  await expect(input).toHaveValue('B 独立草稿');
  await expect(page.locator('.stream-text')).toHaveText('B_ONLY_STREAM_BACKGROUND');
  await page.reload();
  await expect(input).toHaveValue('B 独立草稿');
  await expect(page.locator('.stream-text')).toHaveText('B_ONLY_STREAM_BACKGROUND');
  assert.equal(exchanges.length,4,'Reload must not replay a task');
  await page.evaluate(()=>{
    const button=document.querySelector('.stop-button');
    button.addEventListener('click',()=>{
      window.stopTiming={click:performance.now()};
      const observer=new MutationObserver(()=>{
        if(button.disabled&&window.stopTiming.feedback===undefined)window.stopTiming.feedback=performance.now();
        if(document.querySelector('.status')?.textContent.includes('已停止')){
          window.stopTiming.finished=performance.now();observer.disconnect();
        }
      });
      observer.observe(document.body,{childList:true,subtree:true,attributes:true,characterData:true});
    },{once:true,capture:true});
  });
  await page.getByRole('button',{name:'停止',exact:true}).click();
  await expect.poll(async()=>(await invoke('live')).busy,{timeout:5000}).toBe(false);
  await expect(page.locator('.status')).toContainText('已停止');
  const timing=await page.evaluate(()=>window.stopTiming);
  const cancel_ms=Math.round(timing.finished-timing.click),feedback_ms=Math.round((timing.feedback??timing.finished)-timing.click);
  assert(feedback_ms<500);
  let snapshot=await invoke('snapshot');
  assert(snapshot.active_sessions.find(s=>s.id===a).busy,'Stopping B must not cancel A');
  assert(snapshot.any_busy);
  await page.getByRole('button',{name:'新建会话',exact:true}).click();
  await expect(page.locator('.session-concurrency')).toContainText('1 个会话运行中');
  snapshot=await invoke('snapshot');
  assert(!snapshot.busy&&snapshot.any_busy,'Idle selection must still report background work');
  const c=snapshot.session_id;
  // Closing on an idle conversation must still ask about running A.
  await app.evaluate(({BrowserWindow,dialog})=>{
    globalThis.closePrompts=[];
    dialog.showMessageBox=async(_w,options)=>{globalThis.closePrompts.push(options.message);return {response:0};};
    BrowserWindow.getAllWindows()[0].close();
  });
  await expect.poll(()=>app.evaluate(()=>globalThis.closePrompts.length)).toBe(1);
  assert((await app.evaluate(()=>globalThis.closePrompts[0])).includes('所有会话'));
  assert((await invoke('snapshot')).active_sessions.find(s=>s.id===a).busy);
  await page.locator(`[data-session-id="${a}"]`).click();
  await expect(page.locator('.stream-text')).toHaveText('A_SECOND_STREAM');
  // Repeat switches while the fixture streams to exercise session/view revision guards.
  for(let i=0;i<3;i++){
    await page.locator(`[data-session-id="${b}"]`).click();
    await expect(page.getByRole('button',{name:'主对话模型'})).toContainText('fixture-b');
    await page.locator(`[data-session-id="${a}"]`).click();
    await expect(page.locator('.stream-text')).toHaveText('A_SECOND_STREAM');
  }
  await capture('concurrent');
  await page.getByRole('button',{name:'停止',exact:true}).click();
  await expect.poll(async()=>(await invoke('live')).any_busy).toBe(false);
  assert.deepEqual(errors,[]);
  assert.equal(exchanges[0].body.model,'fixture-a');
  assert.equal(exchanges[1].body.model,'fixture-b');
  assert.equal(exchanges[2].body.model,'fixture-a');
  const report={mode,version:await app.evaluate(({app})=>app.getVersion()),sessions:[a,b,c],requests:4,paid_api_calls:0,cancel_ms,feedback_ms,
    checks:['overlapping requests','switch while awaiting approval','background status','independent model and drafts','approval routing',
      'stream isolation','reload without replay','cancel only selected session','idle view exit checks background sessions','rapid switching'],renderer_errors:errors};
  fs.writeFileSync(path.join(output,`concurrent-${mode}.json`),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(app){await app.evaluate(({dialog})=>{dialog.showMessageBox=async()=>({response:1});}).catch(()=>{});await app.close().catch(()=>{});}
  for(const socket of sockets)socket.destroy();
  server.close();
});
