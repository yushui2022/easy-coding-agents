// Real hidden Electron, isolated settings and a local model catalogue. No user windows or keys.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents';
const home=fs.mkdtempSync(path.join(base,'eca-settings-design-'));
const output=path.resolve('../output/playwright/settings-design');fs.mkdirSync(output,{recursive:true});
let app;const errors=[];const sockets=new Set();
const report={paid_api_calls:0,mode:process.env.ECA_TEST_EXE?'packaged':'source',checks:[]};
const server=http.createServer((req,res)=>{
  res.writeHead(200,{'Content-Type':'application/json'});
  res.end(JSON.stringify({object:'list',data:['deepseek-flash','deepseek-pro','local-coder'].map(id=>({id}))}));
});
server.on('connection',socket=>{sockets.add(socket);socket.on('close',()=>sockets.delete(socket));});
async function capture(name) {
  const bytes=await app.evaluate(async({BrowserWindow})=>{
    const win=BrowserWindow.getAllWindows()[0];
    await win.webContents.executeJavaScript('document.fonts.ready.then(async()=>{await Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{})));await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));})');
    return (await win.webContents.capturePage(undefined,{stayHidden:true,stayAwake:true})).toPNG().toString('base64');
  });
  fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(bytes,'base64'));
}
async function layout(page) {
  return page.evaluate(()=>{
    const rect=selector=>document.querySelector(selector).getBoundingClientRect().toJSON();
    return {viewport:{width:innerWidth,height:innerHeight},dialog:rect('.model-settings'),footer:rect('.connection-editor-footer'),save:rect('.config-actions .primary'),scroll:rect('.connection-scroll'),overflow:document.querySelector('.model-settings').scrollWidth>document.querySelector('.model-settings').clientWidth+1};
  });
}
async function contrast(page,theme) {
  await page.evaluate(()=>Promise.all(document.getAnimations().map(animation=>animation.finished.catch(()=>{}))));
  const ratios=await page.evaluate(()=>{
    const rgb=value=>(value.match(/[\d.]+/g)||[]).slice(0,3).map(Number);
    const luminance=color=>rgb(color).map(value=>{value/=255;return value<=.04045?value/12.92:((value+.055)/1.055)**2.4;}).reduce((sum,value,index)=>sum+value*[.2126,.7152,.0722][index],0);
    return ['.connection-heading h3','.connection-heading p','.connection-item-copy small','.connections-note p','.field label','.catalogue-status','.connection-test-note','.config-actions .primary'].map(selector=>{
      const el=document.querySelector('.model-settings '+selector);let parent=el;
      while(parent&&getComputedStyle(parent).backgroundColor==='rgba(0, 0, 0, 0)')parent=parent.parentElement;
      const a=luminance(getComputedStyle(el).color),b=luminance(getComputedStyle(parent).backgroundColor);
      return {selector,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
    });
  });
  for(const sample of ratios)assert(sample.ratio>=4.5,`${theme} ${sample.selector}: ${sample.ratio}`);
  report['contrast_'+theme]=ratios;
}
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const env={...process.env,TEMP:base,TMP:base,ECA_DESKTOP_DATA_HOME:path.join(home,'app'),ECA_DESKTOP_TEST_HIDDEN:'1',ECA_PYTHON:process.env.ECA_PYTHON||path.resolve('.venv/Scripts/python.exe'),NO_PROXY:'127.0.0.1,localhost',no_proxy:'127.0.0.1,localhost'};
  delete env.ELECTRON_RUN_AS_NODE;
  for(const key of ['ECA_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'])delete env[key];
  app=await electron.launch(process.env.ECA_TEST_EXE?{executablePath:process.env.ECA_TEST_EXE,args:[],env}:{args:['.'],env});
  const page=await app.firstWindow();page.on('pageerror',error=>errors.push(String(error)));
  await app.evaluate(({BrowserWindow})=>{const win=BrowserWindow.getAllWindows()[0];win.webContents.setBackgroundThrottling(false);win.setContentSize(1360,920);});
  await page.getByRole('button',{name:'模型与设置',exact:false}).click();
  const defaultToggle=page.getByRole('checkbox',{name:'设为桌面默认模型'});
  await expect(defaultToggle).toBeEnabled();await expect(defaultToggle).not.toBeChecked();
  await capture('new-connection-light');
  await page.keyboard.press('Escape');
  report.checks.push('empty connection has an editable unchecked default option');
  const endpoint=`http://127.0.0.1:${server.address().port}/v1`;
  await page.evaluate(async endpoint=>{
    for(const [name,model,no_auth,make_default] of [['DeepSeek 工作模型','deepseek-flash',false,true],['本地轻量模型','local-coder',true,false],['备用兼容服务','deepseek-pro',false,false]])
      await window.eca.invoke('config.save',{name,model,no_auth,make_default,base_url:endpoint,api_format:'openai',api_key:'settings-fixture-only',persist:true,thinking_mode:'fast'});
  },endpoint);
  await page.reload();
  await page.getByRole('button',{name:'模型与设置',exact:false}).click();
  await expect(page.getByRole('navigation',{name:'已保存的模型连接'}).getByRole('button')).toHaveCount(3);
  await expect(page.getByLabel('连接名称',{exact:true})).toHaveValue('DeepSeek 工作模型');
  await expect(page.getByLabel('API 密钥')).toHaveValue('');
  await expect(page.getByLabel('服务返回的模型')).toBeEnabled({timeout:15000});
  await expect(defaultToggle).toBeChecked();await expect(defaultToggle).toBeDisabled();
  await contrast(page,'light');await capture('connections-light');
  await page.emulateMedia({colorScheme:'dark'});await contrast(page,'dark');await capture('connections-dark');
  await page.emulateMedia({colorScheme:'light'});
  const before=await layout(page);
  await page.locator('.connection-scroll').evaluate(el=>{el.scrollTop=el.scrollHeight;});
  const after=await layout(page);
  assert.equal(before.save.y,after.save.y,'Save stays in place when the form scrolls');
  assert(!after.overflow&&after.save.bottom<after.viewport.height);
  await expect(page.getByRole('button',{name:'移除连接',exact:true})).toBeVisible();
  await capture('connection-usage');
  report.checks.push('independent editor scroll keeps save visible','three connections and saved credential masking');
  await page.getByLabel('连接名称',{exact:true}).fill('临时草稿名称');
  await page.getByRole('navigation',{name:'已保存的模型连接'}).getByRole('button',{name:/本地轻量模型/}).click();
  await page.getByRole('navigation',{name:'已保存的模型连接'}).getByRole('button',{name:/DeepSeek 工作模型/}).click();
  await expect(page.getByLabel('连接名称',{exact:true})).toHaveValue('临时草稿名称');
  await page.getByLabel('连接名称',{exact:true}).fill('DeepSeek 工作模型');
  await page.getByRole('button',{name:'移除连接',exact:true}).click();
  await expect(page.locator('.connection-remove-confirm')).toBeVisible();
  await page.getByRole('button',{name:'取消',exact:true}).click();
  await expect(page.getByRole('navigation',{name:'已保存的模型连接'}).getByRole('button')).toHaveCount(3);
  report.checks.push('draft survives connection changes','remove is explicit and cancel preserves connection');
  // Only this owned test window can shrink below the application's production minimum.
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setMinimumSize(480,480));
  for(const width of [820,560]) {
    await app.evaluate(({BrowserWindow},width)=>BrowserWindow.getAllWindows()[0].setContentSize(width,680),width);
    await page.locator('.connection-scroll').evaluate(el=>{el.scrollTop=0;});
    const dimensions=await layout(page);
    assert(Math.abs(dimensions.viewport.width-width)<5,'Requested responsive viewport is actually applied');
    assert(!dimensions.overflow&&dimensions.save.bottom<dimensions.viewport.height&&dimensions.save.x>=0&&dimensions.save.right<=dimensions.viewport.width);
    report['layout_'+width]=dimensions;
    await capture('connections-'+width);
  }
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'模型与设置',exact:false})).toBeFocused();
  report.checks.push('compact layout and save remain usable','Escape restores opener focus');
  assert.deepEqual(errors,[]);report.renderer_errors=errors;
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
})().catch(async error=>{console.error(error);console.error('Renderer errors:',errors);if(app)await capture('failure').catch(()=>{});process.exitCode=1;}).finally(async()=>{
  if(app){await app.evaluate(({app})=>app.exit(0)).catch(()=>{});await app.close().catch(()=>{});}
  for(const socket of sockets)socket.destroy();server.close();
});

