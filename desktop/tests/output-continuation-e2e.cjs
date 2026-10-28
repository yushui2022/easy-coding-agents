// Hidden owned Electron window, local SSE fixture only. Never touches user data.
// Proves a response cut at the output token limit keeps the text the user already
// saw and continues it inside the same answer, instead of discarding the work.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents',home=fs.mkdtempSync(path.join(base,'continuation-'));
const project=path.join(home,'续写 项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\nmax_output_tokens=64\n');
const output=path.resolve('../output/playwright/output-continuation');fs.mkdirSync(output,{recursive:true});
const mode=process.env.ECA_TEST_MODE||(process.env.ECA_TEST_EXE?'packaged':'development');

const FIRST='第一段已经流出来的正文。';
const SECOND='第二段接着写完的内容。';
const requests=[],sockets=new Set(),errors=[];
const server=http.createServer(async(req,res)=>{
  let text='';for await(const chunk of req)text+=chunk;
  const body=JSON.parse(text);requests.push(body);
  const history=JSON.stringify(body.messages||[]);
  const task=history.includes('写一篇长文');
  const continued=history.includes('Continue from the exact point');
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  const send=(delta,finish)=>res.write('data: '+JSON.stringify({id:'local',object:'chat.completion.chunk',created:0,model:'fixture',
    choices:[{index:0,delta,finish_reason:finish}]})+'\n\n');
  if(!task){
    send({content:'续写验证'},'stop');
  }else if(!continued){
    // The provider cuts this response at the output limit after real prose.
    send({content:FIRST},null);
    send({},'length');
  }else{
    send({content:SECOND},null);
    send({},'stop');
  }
  res.end('data: [DONE]\n\n');
});
server.on('connection',s=>{sockets.add(s);s.on('close',()=>sockets.delete(s));});
let app;
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

  const input=page.getByLabel('任务指令');
  await input.fill('写一篇长文');await input.press('Enter');

  const taskRequests=()=>requests.filter(r=>JSON.stringify(r.messages||[]).includes('写一篇长文'));
  await expect.poll(()=>taskRequests().length,{timeout:60000}).toBeGreaterThan(1);
  assert(taskRequests()[1].messages.some(m=>String(m.content||'').includes('Continue from the exact point')),
    'the agent never asked the model to continue from the cut-off point');

  // One answer, both halves, no lost text and no second answer bubble.
  const answers=page.locator('.message.assistant');
  await expect(answers.last()).toContainText(SECOND,{timeout:60000});
  await expect(answers.last()).toContainText(FIRST);
  assert.equal(await answers.count(),1,'the continuation must extend the same answer, not add another');
  assert.equal(await page.locator('.runtime-note').count(),0,'recovery notes stay out of the transcript');

  // The saved session keeps the merged text so reopening does not lose it.
  const state=await invoke('snapshot');
  const saved=await invoke('session.history',{project_id:state.project_id,id:state.session_id,limit:50}).catch(()=>null);
  if(saved&&Array.isArray(saved.messages)){
    const assistant=saved.messages.filter(m=>m.role==='assistant');
    assert.equal(assistant.length,1,'history must hold a single assistant answer');
    assert(String(assistant[0].content).includes(FIRST)&&String(assistant[0].content).includes(SECOND),'history lost part of the answer');
  }

  if(errors.length)throw new Error('renderer errors: '+errors.join(' | '));
  fs.writeFileSync(path.join(output,`${mode}.json`),JSON.stringify({mode,
    exe:process.env.ECA_TEST_EXE||'development',requests:requests.length,
    taskRequests:taskRequests().length,mergedOneAnswer:true},null,2));
  console.log('output continuation ok',mode,'requests',requests.length);
  server.close();for(const s of sockets)s.destroy();
  await app.close();
  process.exit(0);
})().catch(error=>{
  console.error(error);
  server.close();for(const s of sockets)s.destroy();
  if(app)app.close().then(()=>process.exit(1),()=>process.exit(1));
  else process.exit(1);
});
