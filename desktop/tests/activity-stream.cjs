// Real renderer -> RPC -> provider SSE -> approved shell. Only local fixture API.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents',home=fs.mkdtempSync(path.join(base,'activity-stream-'));
const project=path.join(home,'实时状态 项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
fs.writeFileSync(path.join(project,'activity-input.txt'),'activity-stream-ready');
const output=path.resolve('../output/playwright/activity');fs.mkdirSync(output,{recursive:true});
let app;const exchanges=[],sockets=new Set(),errors=[];
const server=http.createServer(async(req,res)=>{
  let text='';for await(const chunk of req)text+=chunk;
  exchanges.push({res,body:JSON.parse(text)});
});
server.on('connection',s=>{sockets.add(s);s.on('close',()=>sockets.delete(s));});
const start=res=>res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache'});
const delta=(res,value,finish=null)=>res.write('data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',created:0,model:'deepseek-flash',choices:[{index:0,delta:value,finish_reason:finish}]})+'\n\n');
const end=(res,tokens)=>{
  res.write('data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',created:0,model:'deepseek-flash',choices:[],usage:{prompt_tokens:100,completion_tokens:tokens,total_tokens:100+tokens}})+'\n\n');
  res.end('data: [DONE]\n\n');
};
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const env={...process.env};
  for(const name of Object.keys(env))if(name.startsWith('ECA_')||/API_KEY|API_BASE|BASE_URL|MODEL_NAME|PYTHONHOME|PYTHONPATH/.test(name))delete env[name];
  Object.assign(env,{TEMP:base,TMP:base,ECA_DESKTOP_TEST_HIDDEN:'1',ECA_DESKTOP_DATA_HOME:path.join(home,'app'),ECA_PYTHON:path.resolve('.venv/Scripts/python.exe'),NO_PROXY:'127.0.0.1,localhost',no_proxy:'127.0.0.1,localhost'});
  delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch(process.env.ECA_TEST_EXE?{executablePath:process.env.ECA_TEST_EXE,args:[],env}:{args:['.'],env});
  const page=await app.firstWindow();page.on('pageerror',e=>errors.push(String(e)));
  await app.evaluate(({BrowserWindow,dialog},folder)=>{
    const w=BrowserWindow.getAllWindows()[0];w.setContentSize(1280,880);w.webContents.setBackgroundThrottling(false);
    dialog.showOpenDialog=async()=>({canceled:false,filePaths:[folder]});
  },project);
  const invoke=(method,params={})=>page.evaluate(([method,params])=>window.eca.invoke(method,params),[method,params]);
  const saved=await invoke('config.save',{model:'deepseek-flash',name:'本地流式测试',api_format:'openai',base_url:`http://127.0.0.1:${server.address().port}/v1`,no_auth:true});
  await invoke('config.default',{id:saved.savedId});await page.getByRole('button',{name:'打开项目',exact:true}).click();
  await expect.poll(async()=>(await invoke('snapshot')).project).toBe(project);
  await page.getByLabel('任务指令').fill('读取 activity-input.txt 并报告结果');
  await expect(page.getByRole('button',{name:'发送任务',exact:true})).toBeEnabled();
  await page.getByLabel('任务指令').press('Enter');
  await expect.poll(()=>exchanges.length).toBe(1);
  const row=page.locator('.run-activity');
  await expect(row.locator('.activity-title')).toHaveText('等待模型响应');
  await expect(row.locator('.activity-speed strong')).toHaveText('—');
  const first=exchanges[0].res;start(first);
  delta(first,{reasoning_content:'private fixture reasoning'});
  await expect(row.locator('.activity-subtitle')).toContainText('25 个思考字符');
  await new Promise(r=>setTimeout(r,350));
  delta(first,{reasoning_content:' more private fixture reasoning'});
  await expect(row.locator('.activity-speed strong')).toContainText('≈');
  await expect(page.locator('body')).not.toContainText('private fixture reasoning');
  const command="Get-Content 'activity-input.txt'; Start-Sleep -Seconds 3";
  delta(first,{tool_calls:[{index:0,id:'fixture-shell',type:'function',function:{name:'shell',arguments:'{"command":'}}]});
  await expect(row.locator('.activity-title')).toHaveText('正在准备工具调用');
  await expect(row.locator('.activity-tool-name')).toHaveText('shell');
  await expect(row.locator('.activity-subtitle')).toContainText('尚未执行');
  delta(first,{tool_calls:[{index:0,function:{arguments:JSON.stringify(command)+'}'}}]});
  delta(first,{},'tool_calls');end(first,80);
  await expect(page.getByRole('button',{name:'本次允许',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'本次允许',exact:true}).click();
  await expect(row.locator('.activity-title')).toHaveText('正在运行命令');
  await expect(row.locator('.activity-subtitle')).toHaveText(command);
  await expect(row.locator('.activity-speed strong')).not.toContainText('≈');
  await expect(row.locator('.activity-speed strong')).not.toHaveText('—');
  await expect(row.locator('.activity-timing')).toContainText('上一轮');
  const generation=await invoke('live');
  assert.equal(generation.last_request.output_tokens,80);
  assert.equal(generation.last_request.throughput_source,'provider');
  assert.equal(generation.activity.tool,'shell');
  const mode=process.env.ECA_TEST_MODE||(process.env.ECA_TEST_EXE?'packaged':'development');
  const png=await app.evaluate(async({BrowserWindow})=>{
    const wc=BrowserWindow.getAllWindows()[0].webContents;
    await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});await new Promise(r=>setTimeout(r,180));
    return (await wc.capturePage(undefined,{stayHidden:true,stayAwake:true})).toPNG().toString('base64');
  });
  fs.writeFileSync(path.join(output,`stream-${mode}.png`),Buffer.from(png,'base64'));
  await expect.poll(()=>exchanges.length,{timeout:15000}).toBe(2);
  assert(exchanges[1].body.messages.some(m=>m.role==='tool'&&m.content.includes('activity-stream-ready')));
  await expect(row.locator('.activity-title')).toHaveText('等待模型响应');
  await expect(row.locator('.activity-speed strong')).toHaveText('—'); // no stale previous rate
  const second=exchanges[1].res;start(second);
  delta(second,{content:'文件已读取。'});
  await new Promise(r=>setTimeout(r,350));delta(second,{content:'正在整理结果。'});
  await expect(row.locator('.activity-title')).toHaveText('正在生成回答');
  await expect(row.locator('.activity-speed strong')).toContainText('≈');
  await page.reload();
  await expect(page.locator('.activity-title')).toHaveText('正在生成回答');
  await expect(page.locator('.activity-speed strong')).toContainText('≈');
  assert.equal(exchanges.length,2);
  await page.evaluate(()=>{
    const button=document.querySelector('.stop-button');
    button.addEventListener('click',()=>{
      window.cancelTiming={click:performance.now()};
      const observer=new MutationObserver(()=>{
        if(button.disabled&&window.cancelTiming.feedback===undefined)window.cancelTiming.feedback=performance.now();
        if(document.querySelector('.status')?.textContent.includes('已停止')){
          window.cancelTiming.finished=performance.now();observer.disconnect();
        }
      });
      observer.observe(document.body,{childList:true,subtree:true,attributes:true,characterData:true});
    },{once:true,capture:true});
  });
  await page.getByRole('button',{name:'停止',exact:true}).click();
  await expect(page.locator('.status')).toContainText('已停止',{timeout:5000});
  const timing=await page.evaluate(()=>window.cancelTiming);
  const cancel_ms=Math.round(timing.finished-timing.click),feedback_ms=Math.round((timing.feedback??timing.finished)-timing.click);
  assert(feedback_ms<500,'Stop click must give immediate feedback independently of model response');
  await expect(page.locator('.run-activity')).toHaveCount(0);
  assert.deepEqual(errors,[]);
  const report={version:await app.evaluate(({app})=>app.getVersion()),mode,paid_api_calls:0,requests:exchanges.length,cancel_ms,feedback_ms,renderer_errors:errors,
    checks:['real SSE reasoning counters without private text','estimated stream speed','tool argument progress before execution','actual approved shell with visible subject','provider usage replaces estimate','new request clears old rate','live reply counters','reload restores telemetry without replay','stalled stream cancellation']};
  fs.writeFileSync(path.join(output,`stream-${mode}.json`),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{
  if(app){await app.evaluate(({app})=>app.exit(0)).catch(()=>{});await app.close().catch(()=>{});}
  for(const s of sockets)s.destroy();server.close();
});
