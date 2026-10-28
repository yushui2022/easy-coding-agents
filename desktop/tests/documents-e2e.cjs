// Hidden owned Electron window, local SSE fixture only. Never touches user data.
// Proves a PDF becomes quotable text at the attachment boundary: the request the
// model receives carries the page text, and the raw bytes never become an image.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents',home=fs.mkdtempSync(path.join(base,'documents-'));
const project=path.join(home,'文档 项目');fs.mkdirSync(project);
fs.writeFileSync(path.join(project,'eca.toml'),'[agent]\nproject_memory=false\nauto_compact=false\nnetwork_retries=0\n');
const output=path.resolve('../output/playwright/documents');fs.mkdirSync(output,{recursive:true});
const mode=process.env.ECA_TEST_MODE||(process.env.ECA_TEST_EXE?'packaged':'development');

// A one-page PDF with a valid xref table and one text run, built here so the
// test never depends on a checked-in binary.
function pdf(text){
  const stream=Buffer.from(`BT /F1 12 Tf 20 100 Td (${text}) Tj ET`,'latin1');
  const objects=[
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    null,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ];
  const parts=[Buffer.from('%PDF-1.4\n','latin1')],offsets=[];
  objects.forEach((body,index)=>{
    offsets.push(parts.reduce((n,part)=>n+part.length,0));
    const payload=body===null
      ? Buffer.concat([Buffer.from(`<< /Length ${stream.length} >>\nstream\n`,'latin1'),stream,Buffer.from('\nendstream','latin1')])
      : Buffer.from(body,'latin1');
    parts.push(Buffer.from(`${index+1} 0 obj\n`,'latin1'),payload,Buffer.from('\nendobj\n','latin1'));
  });
  const xref=parts.reduce((n,part)=>n+part.length,0);
  parts.push(Buffer.from(`xref\n0 ${objects.length+1}\n0000000000 65535 f \n`,'latin1'));
  for(const offset of offsets)parts.push(Buffer.from(`${String(offset).padStart(10,'0')} 00000 n \n`,'latin1'));
  parts.push(Buffer.from(`trailer\n<< /Size ${objects.length+1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`,'latin1'));
  return Buffer.concat(parts);
}

const requests=[],sockets=new Set(),errors=[];
const server=http.createServer(async(req,res)=>{
  let text='';for await(const chunk of req)text+=chunk;
  requests.push(JSON.parse(text));
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  res.write('data: '+JSON.stringify({id:'local',object:'chat.completion.chunk',created:0,model:'fixture',
    choices:[{index:0,delta:{content:'已读'},finish_reason:null}]})+'\n\n');
  res.write('data: '+JSON.stringify({id:'local',object:'chat.completion.chunk',created:0,model:'fixture',
    choices:[{index:0,delta:{},finish_reason:'stop'}]})+'\n\n');
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
  // The draft read disables the picker for a moment; attaching before it finishes
  // is silently dropped, so wait for the button to be live.
  await expect(page.getByRole('button',{name:'添加文件或图片'})).toBeEnabled();
  await page.getByLabel('选择附件').setInputFiles({name:'论文.pdf',mimeType:'application/pdf',
    buffer:pdf('Evidence from page one')});
  await expect(page.locator('.attachment-chip')).toHaveCount(1);
  await expect(page.locator('.attachment-hint')).toContainText('抽出文字');
  await input.fill('这篇论文说了什么');await input.press('Enter');
  // The app also issues a title-summary request, so pick the turn by its prompt.
  await expect.poll(()=>requests.filter(r=>JSON.stringify(r.messages).includes('这篇论文说了什么')).length)
    .toBeGreaterThan(0);
  const first=JSON.stringify(requests.filter(r=>JSON.stringify(r.messages).includes('这篇论文说了什么'))[0].messages);
  assert(first.includes('Evidence from page one'),'the PDF text never reached the model');
  assert(!first.includes('image_url'),'a PDF must not be sent as an image');
  assert(first.includes('[第 1 页]'),'page markers are missing');

  // A corrupt PDF is refused with a sentence at send time, not a traceback.
  await expect(page.getByRole('button',{name:'添加文件或图片'})).toBeEnabled();
  await page.getByLabel('选择附件').setInputFiles({name:'假的.pdf',mimeType:'application/pdf',
    buffer:Buffer.from('%PDF-1.4 broken')});
  await expect(page.locator('.attachment-chip')).toHaveCount(1);
  await input.fill('这个坏文件呢');await input.press('Enter');
  await expect(page.locator('.attachment-error, .notice, [role="alert"]').first()).toContainText('PDF');

  const researchDir=path.join(project,'.eca','attachments');
  const stored=fs.existsSync(researchDir)?fs.readdirSync(researchDir):[];
  assert.equal(stored.length,0,'a document must not be snapshotted as an image blob');
  if(errors.length)throw new Error('renderer errors: '+errors.join(' | '));
  fs.writeFileSync(path.join(output,`${mode}.json`),JSON.stringify({mode,
    exe:process.env.ECA_TEST_EXE||'development',requests:requests.length,
    textReachedModel:true,imageBlocks:0,snapshotFiles:stored.length},null,2));
  console.log('documents ok',mode,'requests',requests.length);
  server.close();for(const s of sockets)s.destroy();
  await app.close();
  process.exit(0);
})().catch(error=>{
  console.error(error);
  server.close();for(const s of sockets)s.destroy();
  if(app)app.close().then(()=>process.exit(1),()=>process.exit(1));
  else process.exit(1);
});
