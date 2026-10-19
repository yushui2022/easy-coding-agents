// Real hidden Electron, isolated data and a streaming local provider. Never drives user windows.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {execFileSync}=require('node:child_process');
process.chdir(path.resolve(__dirname,'..'));
const label=process.argv[2]||'current';
if(!/^[a-z0-9-]+$/.test(label))throw Error('Invalid artifact label');
const base='G:/DevCache/Temp/easy-coding-agents';
const home=fs.mkdtempSync(path.join(base,'eca-performance-'));
const project=path.join(home,'订单 服务');
const python=process.env.ECA_PYTHON||path.resolve('.venv/Scripts/python.exe');
execFileSync(python,['-B','tests/seed-workspace.py',project],{windowsHide:true,env:{...process.env,TEMP:base,TMP:base,PYTHONUTF8:'1'}});
let app;
const sockets=new Set();
const server=http.createServer(async(req,res)=>{
  for await(const _ of req){};
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  let n=0;
  const timer=setInterval(()=>{
    res.write('data: '+JSON.stringify({choices:[{index:0,delta:{content:'已定位订单写入路径，继续核对异常恢复和事务边界。 '},finish_reason:null}]})+'\n\n');
    if(++n>=1000){clearInterval(timer);res.end('data: [DONE]\n\n');}
  },8);
  res.on('close',()=>clearInterval(timer));
});
server.on('connection',s=>{sockets.add(s);s.on('close',()=>sockets.delete(s));});
const report={label,project,paid_api_calls:0,fixture_messages:240,method:'Hidden real Electron; capture-phase input event through React discrete-event microtask. No throttled timers/rAF in input measurement; not physical display latency.'};
const percentile=(a,p)=>[...a].sort((x,y)=>x-y)[Math.min(a.length-1,Math.floor(a.length*p))]||0;
async function measureTyping(page,name){
  await page.evaluate(()=>{
    window.inputSamples=[];
    window.inputSignal?.abort();window.inputSignal=new AbortController();
    const times=new WeakMap();
    document.addEventListener('input',e=>{if(e.target.getAttribute('aria-label')==='任务指令')times.set(e,performance.now());},{capture:true,signal:window.inputSignal.signal});
    // Document bubble follows React's root handler; its discrete commit runs
    // before this microtask. Hidden windows throttle timers even in some test modes.
    document.addEventListener('input',e=>{if(times.has(e))queueMicrotask(()=>window.inputSamples.push(performance.now()-times.get(e)));},{signal:window.inputSignal.signal});
  });
  await page.getByLabel('任务指令').fill('');
  await page.getByLabel('任务指令').pressSequentially('inspect rollback and add regression tests',{delay:12});
  await page.waitForTimeout(120);
  const samples=await page.evaluate(()=>window.inputSamples);
  report[name]={samples:samples.length,p50_ms:percentile(samples,.5),p95_ms:percentile(samples,.95),max_ms:Math.max(0,...samples)};
}
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const env={...process.env,TEMP:base,TMP:base,ECA_DESKTOP_DATA_HOME:path.join(home,'app'),ECA_DESKTOP_TEST_HIDDEN:'1',ECA_PYTHON:python,
    ECA_API_KEY:'performance-fixture-only',ECA_BASE_URL:`http://127.0.0.1:${server.address().port}/v1`,ECA_MODEL:'fixture',ECA_API_FORMAT:'openai',NO_PROXY:'127.0.0.1,localhost',no_proxy:'127.0.0.1,localhost'};
  delete env.ELECTRON_RUN_AS_NODE;
  const started=Date.now();
  app=await electron.launch(process.env.ECA_TEST_EXE?{executablePath:process.env.ECA_TEST_EXE,args:[],env}:{args:['.'],env});
  const page=await app.firstWindow();
  report.version=await app.evaluate(({app})=>app.getVersion());
  await app.evaluate(({BrowserWindow,dialog},project)=>{
    BrowserWindow.getAllWindows()[0].webContents.setBackgroundThrottling(false);
    dialog.showOpenDialog=async()=>({canceled:false,filePaths:[project]});
  },project);
  await expect(page.getByRole('button',{name:'打开项目',exact:false}).first()).toBeVisible();
  report.launch_ms=Date.now()-started;
  await page.getByRole('button',{name:'打开项目',exact:false}).first().click();
  await expect(page.locator('.session-list .selected')).toContainText('订单服务');
  await page.evaluate(()=>{window.longTasks=[];new PerformanceObserver(list=>window.longTasks.push(...list.getEntries().map(e=>e.duration))).observe({type:'longtask',buffered:false});});
  report.initial_dom_nodes=await page.locator('*').count();
  report.snapshots=await page.evaluate(async()=>{
    const timings=[];let bytes=0;
    for(let i=0;i<8;i++){const t=performance.now();const state=await window.eca.invoke('snapshot',{preview:true});timings.push(performance.now()-t);bytes=JSON.stringify(state).length;}
    return {timings,characters:bytes};
  });
  await measureTyping(page,'idle_typing');
  await page.getByRole('button',{name:'发送任务'}).click();
  await expect(page.getByRole('button',{name:'停止',exact:true})).toBeVisible();
  await page.waitForTimeout(700);
  await measureTyping(page,'streaming_typing');
  report.cancellation=await page.evaluate(()=>new Promise((resolve,reject)=>{
    const status=document.querySelector('.status'),button=document.querySelector('.stop-button');
    const started=performance.now();let feedback;
    const timeout=setTimeout(()=>{observer.disconnect();reject(Error('Cancellation did not complete'));},10000);
    const observer=new MutationObserver(()=>{
      if(status.textContent.includes('已停止')){clearTimeout(timeout);observer.disconnect();resolve({feedback_ms:feedback,complete_ms:performance.now()-started});}
    });
    observer.observe(status,{subtree:true,childList:true,characterData:true});
    button.click();
    queueMicrotask(()=>{if(!button.textContent.includes('正在停止')){clearTimeout(timeout);observer.disconnect();reject(Error('Stop had no immediate feedback'));}feedback=performance.now()-started;});
  }));
  report.long_tasks=await page.evaluate(()=>({count:window.longTasks.length,max_ms:Math.max(0,...window.longTasks)}));
  report.final_dom_nodes=await page.locator('*').count();
  if(process.env.ECA_TEST_WORKBENCH==='1') {
    await expect(page.locator('.tool-record pre')).toHaveCount(0);
    const tool=page.locator('.tool-record').last();
    await tool.locator('summary').click();
    await expect(tool.getByRole('button',{name:'加载完整工具记录'})).toBeVisible();
    await tool.getByRole('button',{name:'加载完整工具记录'}).click();
    await expect(tool.getByRole('button',{name:'加载完整工具记录'})).toHaveCount(0);
    await expect(tool.getByRole('button',{name:/继续展开/})).toBeVisible();
    await tool.locator('summary').click();
    await expect(tool.locator('pre')).toHaveCount(0);
    await page.getByLabel('搜索会话').fill('不存在的会话');
    await expect(page.locator('.session-list')).toContainText('没有匹配的会话');
    await page.getByRole('button',{name:'清除会话搜索'}).click();
    await expect(page.locator('.session-list .selected')).toContainText('订单服务');
    await page.getByRole('button',{name:'收起导航'}).click();
    await expect(page.locator('.workspace')).toHaveClass(/nav-collapsed/);
    await page.getByRole('button',{name:'展开导航'}).click();
    for(let i=0;i<4;i++) {
      await page.getByRole('button',{name:'加载更早的消息'}).click();
      await expect(page.getByRole('button',{name:'正在加载…',exact:true})).toHaveCount(0);
    }
    await expect(page.locator('.history-gap')).toContainText(/中间 \d+ 条记录已收起/);
    await page.getByRole('button',{name:'返回最近记录'}).click();
    await expect(page.locator('.history-gap')).toHaveCount(0);
    report.bounded_history_search_navigation_and_full_logs='passed';
    await page.locator('.transcript').evaluate(el=>{el.scrollTop=0;});
    await expect(page.getByRole('button',{name:'回到最新'})).toBeVisible();
    await page.getByRole('button',{name:'回到最新'}).click();
    report.scroll_navigation='passed';
  }
  const output=path.resolve('../output/performance');fs.mkdirSync(output,{recursive:true});
  fs.writeFileSync(path.join(output,label+'.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(app){await app.evaluate(({app})=>app.exit(0)).catch(()=>{});await app.close().catch(()=>{});}
  for(const socket of sockets)socket.destroy();server.close();
});
