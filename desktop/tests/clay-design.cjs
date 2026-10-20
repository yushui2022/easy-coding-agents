// Owned hidden Electron + real persisted local sessions. No user windows or API keys.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents',home=fs.mkdtempSync(path.join(base,'eca-clay-design-'));
const output=path.resolve('../output/playwright/clay-design');fs.mkdirSync(output,{recursive:true});
const python=process.env.ECA_PYTHON||path.resolve('.venv/Scripts/python.exe');
const project=path.join(home,'陶土工作台'),other=path.join(home,'组件 素材库');
fs.mkdirSync(other);fs.mkdirSync(path.join(home,'app'));
execFileSync(python,['-B','-c',`import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path.cwd().parent))\nfrom eca.store import Store\nroot=Path(sys.argv[1]);root.mkdir()\n(root/'eca.toml').write_text('[agent]\\nproject_memory=false\\n',encoding='utf-8')\nstore=Store(root)\nfor title in ['归档任务 '+str(i) for i in range(12)]+['重构模型连接表单','修复输入框换行问题','给组件添加深色主题','三维微缩生态场景','New session']:\n state=store.create();state['title']=title;store.save(state)\nstore.close()`,project],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1',TEMP:base,TMP:base}});
fs.writeFileSync(path.join(home,'app','preferences.json'),JSON.stringify({schema:2,connections:[],projects:{},recent:[other]}));
let app;const errors=[],sockets=new Set(),materials=new Set();const report={paid_api_calls:0,checks:[]};
const server=http.createServer((req,res)=>{res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({data:[{id:'deepseek-flash'},{id:'local-coder'}]}));});
server.on('connection',socket=>{sockets.add(socket);socket.on('close',()=>sockets.delete(socket));});
async function capture(name,sidebar=false){
  const bytes=await app.evaluate(async({BrowserWindow},sidebar)=>{
    const win=BrowserWindow.getAllWindows()[0];
    const rect=await win.webContents.executeJavaScript(`(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode()));await Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{})));await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));const r=document.querySelector('.sidebar').getBoundingClientRect();return {x:Math.round(r.x),y:Math.round(r.y),width:Math.round(r.width),height:Math.round(r.height)}})()`);
    return (await win.webContents.capturePage(sidebar?rect:undefined,{stayHidden:true,stayAwake:true})).toPNG().toString('base64');
  },sidebar);fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(bytes,'base64'));
}
async function sidebarFits(page){
  const dimensions=await page.locator('.sidebar').evaluate(el=>{
    const box=e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}};
    return {width:innerWidth,height:innerHeight,sidebar:box(el),footer:box(el.querySelector('.sidebar-bottom')),overflow:el.scrollWidth>el.clientWidth};
  });
  assert(!dimensions.overflow);assert(dimensions.footer.bottom<=dimensions.height+1);assert(dimensions.footer.top>0);return dimensions;
}
async function checkMaterials(page){
  const loaded=await page.evaluate(async()=>{
    const urls=new Set();
    for(const selector of ['.clay-sidebar','.composer','.session-list .selected','.connection-sidebar .selected']){
      const el=document.querySelector(selector);if(!el)continue;
      for(const match of getComputedStyle(el).backgroundImage.matchAll(/url\(["']?([^"')]+)["']?\)/g))urls.add(new URL(match[1],location.href).href);
    }
    for(const url of urls){const image=new Image();image.src=url;await image.decode();if(image.naturalWidth!==1254)throw Error('Unexpected texture size');}
    return [...urls];
  });
  loaded.forEach(url=>materials.add(url.split('/').pop()));
}
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const env={...process.env,TEMP:base,TMP:base,ECA_DESKTOP_DATA_HOME:path.join(home,'app'),ECA_DESKTOP_TEST_HIDDEN:'1',ECA_PYTHON:python,ECA_API_KEY:'clay-fixture-only',ECA_MODEL:'deepseek-flash',ECA_BASE_URL:`http://127.0.0.1:${server.address().port}/v1`,ECA_API_FORMAT:'openai',NO_PROXY:'127.0.0.1,localhost',no_proxy:'127.0.0.1,localhost'};delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch({args:['.'],env});const page=await app.firstWindow();page.on('pageerror',e=>errors.push(String(e)));
  await app.evaluate(({BrowserWindow,dialog},project)=>{const win=BrowserWindow.getAllWindows()[0];win.webContents.setBackgroundThrottling(false);win.setContentSize(1360,900);dialog.showOpenDialog=async()=>({canceled:false,filePaths:[project]});},project);
  await page.getByRole('button',{name:'打开项目',exact:true}).click();
  await expect(page.locator('.project-current')).toContainText('陶土工作台');
  await expect(page.locator('.session-list button')).toHaveCount(17);
  if(await page.getByRole('button',{name:'任务详情',exact:true}).getAttribute('aria-expanded')==='true')await page.getByRole('button',{name:'任务详情',exact:true}).click();
  await page.getByLabel('任务指令').fill('把想法写下来，我们从这里开始。');
  for(const theme of ['light','dark']){
    await page.emulateMedia({colorScheme:theme});report['layout_'+theme]=await sidebarFits(page);await checkMaterials(page);
    await capture('workspace-'+theme);await capture('sidebar-'+theme,true);
  }
  await page.emulateMedia({colorScheme:'light'});
  await page.getByLabel('搜索会话').fill('模型连接');await expect(page.locator('.session-list button')).toHaveCount(1);
  await page.locator('.session-list button').click();await expect(page.locator('.session-list .selected')).toContainText('模型连接');
  await page.getByRole('button',{name:'清除会话搜索'}).click();await expect(page.locator('.session-list button')).toHaveCount(17);
  await page.getByLabel('搜索会话').fill('不存在');await expect(page.locator('.session-list')).toContainText('没有匹配的会话');
  await page.getByRole('button',{name:'清除会话搜索'}).click();
  await page.getByRole('button',{name:'新建会话',exact:true}).click();await expect(page.locator('.session-list button')).toHaveCount(18);
  report.checks.push('persisted sessions, search, empty result, selection and new session');
  await page.getByLabel('搜索会话').fill('过滤');await page.locator('.recent').click();
  await expect(page.getByLabel('搜索会话')).toHaveValue('');await expect(page.locator('.project-current')).toContainText('组件 素材库');
  await page.getByRole('button',{name:'打开项目',exact:true}).click();await expect(page.locator('.project-current')).toContainText('陶土工作台');
  report.checks.push('recent project switches and resets session search');
  await page.getByRole('button',{name:'收起导航'}).click();await expect(page.locator('.sidebar-sessions')).toBeHidden();
  await expect(page.locator('.settings-glyph')).toBeVisible();await sidebarFits(page);await capture('collapsed');
  await page.getByRole('button',{name:'模型与设置',exact:true}).click();await expect(page.getByRole('dialog')).toBeVisible();await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'展开导航'}).click();
  await page.getByRole('button',{name:'任务详情',exact:true}).click();await page.getByRole('button',{name:'展开工作区',exact:true}).click();
  await expect(page.locator('.sidebar-sessions')).toBeHidden();await expect(page.locator('.settings-glyph')).toBeVisible();await sidebarFits(page);await capture('workspace-full');
  await page.getByRole('button',{name:'收起任务详情',exact:true}).click();
  report.checks.push('collapsed navigation and full workspace keep settings reachable');
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(820,580));
  await expect(page.locator('.project-current')).toBeVisible();report.compact=await sidebarFits(page);await capture('compact');
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1360,900));
  await page.evaluate(async endpoint=>{await window.eca.invoke('config.save',{name:'日常编码',model:'deepseek-flash',base_url:endpoint,api_format:'openai',api_key:'clay-fixture-only',persist:false,make_default:true});},`http://127.0.0.1:${server.address().port}/v1`);
  await page.reload();await page.getByRole('button',{name:'模型与设置',exact:true}).click();
  await expect(page.getByLabel('服务返回的模型')).toBeEnabled();
  for(const theme of ['light','dark']){await page.emulateMedia({colorScheme:theme});await capture('form-'+theme);}
  await page.getByLabel('连接名称',{exact:true}).fill('陶土主题演示');await page.getByRole('button',{name:'保存配置',exact:true}).click();
  await expect(page.locator('.config-status')).toContainText('配置已保存');
  report.checks.push('light/dark textured fields accept input and save');
  const assets=[...materials];
  assert(assets.some(name=>name.startsWith('clay-chalk')));assert(assets.some(name=>name.startsWith('clay-charcoal')));assert(assets.some(name=>name.startsWith('clay-rose')));
  report.loaded_materials=assets;report.renderer_errors=errors;assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
})().catch(async e=>{console.error(e);if(app)await capture('failure').catch(()=>{});process.exitCode=1;}).finally(async()=>{if(app){await app.evaluate(({app})=>app.exit(0)).catch(()=>{});await app.close().catch(()=>{});}for(const socket of sockets)socket.destroy();server.close();});
