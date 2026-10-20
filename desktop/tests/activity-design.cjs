// Render the production component in an owned hidden Electron window.
// Phase fixtures validate presentation; they do not claim actual tool execution.
const {_electron:electron,expect}=require('@playwright/test');
const {build}=require('esbuild'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents',temp=fs.mkdtempSync(path.join(base,'activity-design-'));
const output=path.resolve('../output/playwright/activity');fs.mkdirSync(output,{recursive:true});
const source=path.resolve('src/renderer').replaceAll('\\','/');
let app;const errors=[];
async function capture(page,name) {
  await page.locator('.activity-mark').evaluate(image=>image.decode());
  await page.evaluate(()=>document.fonts.ready);
  await page.waitForTimeout(220);
  const bounds=await page.locator('.preview-surface').boundingBox();
  const png=await app.evaluate(async({BrowserWindow},bounds)=>{
    const wc=BrowserWindow.getAllWindows()[0].webContents;
    const rect={x:Math.floor(bounds.x),y:Math.floor(bounds.y),width:Math.ceil(bounds.width),height:Math.ceil(bounds.height)};
    await wc.capturePage(rect,{stayHidden:true,stayAwake:true});await new Promise(r=>setTimeout(r,180));
    return (await wc.capturePage(rect,{stayHidden:true,stayAwake:true})).toPNG().toString('base64');
  },bounds);
  fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(png,'base64'));
}
(async()=>{
  await build({stdin:{contents:`
    import React from 'react';import {createRoot} from 'react-dom/client';
    import {RunActivity} from ${JSON.stringify(source+'/RunActivity.tsx')};
    import ${JSON.stringify(source+'/tokens.css')};import ${JSON.stringify(source+'/style.css')};
    import ${JSON.stringify(source+'/workbench.css')};import ${JSON.stringify(source+'/clay-surfaces.css')};
    const root=createRoot(document.getElementById('root'));
    window.renderActivity=(state,stopping=false)=>root.render(<div className="eca-app"><div className="preview-surface">
      <RunActivity state={state} stopping={stopping}/>
      <div className="preview-composer">继续补充任务…<div><span>deepseek-flash · 中</span><button disabled>停止</button></div></div>
    </div></div>);
  `,loader:'tsx',resolveDir:process.cwd()},outfile:path.join(temp,'fixture.js'),bundle:true,loader:{'.png':'file'},
    assetNames:'assets/[name]',define:{'process.env.NODE_ENV':'"production"'}});
  fs.writeFileSync(path.join(temp,'index.html'),`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><link rel="stylesheet" href="fixture.css">
    <style>body{margin:0}.eca-app{display:block;background:var(--canvas);height:100vh}.preview-surface{padding:32px;width:100%;box-sizing:border-box}
    .preview-composer{padding:20px;border:1px solid var(--border);border-radius:20px;background:var(--surface);color:var(--muted);font-size:13px;box-shadow:var(--material-raised)}
    .preview-composer>div{display:flex;justify-content:space-between;align-items:center;margin-top:28px;font-size:11px}.preview-composer button{font:inherit;color:var(--danger)}</style>
    <div id="root"></div><script src="fixture.js"></script></html>`);
  fs.writeFileSync(path.join(temp,'main.cjs'),`const {app,BrowserWindow}=require('electron');
    app.setPath('userData',${JSON.stringify(path.join(temp,'data'))});app.whenReady().then(()=>{
      const win=new BrowserWindow({width:760,height:400,show:false,webPreferences:{contextIsolation:true,sandbox:true,backgroundThrottling:false}});
      win.loadFile(${JSON.stringify(path.join(temp,'index.html'))});});`);
  const env={...process.env,TEMP:base,TMP:base};delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch({args:[path.join(temp,'main.cjs')],env});
  const page=await app.firstWindow();page.on('pageerror',e=>errors.push(String(e)));
  await page.waitForFunction(()=>typeof window.renderActivity==='function');
  const state=(phase,extra={})=>({started_at:Math.floor(Date.now()/1000)-14,activity:{phase,...extra}});
  const show=(state,stopping=false)=>page.evaluate(([state,stopping])=>window.renderActivity(state,stopping),[state,stopping]);
  await show({...state('executing',{tool:'grep',target:'src/components · handleSubmit'}),last_request:{tokens_per_second:42.6,throughput_source:'provider'}});
  const row=page.locator('.run-activity');
  await expect(row.getByRole('status')).toHaveText('正在搜索代码');
  await expect(row.locator('.activity-detail')).toHaveCount(0);
  await expect(row.getByRole('status').locator('time')).toHaveCount(0);
  assert(await row.evaluate(el=>el.getBoundingClientRect().height)<=70);
  await expect(row.locator('.activity-subtitle')).toHaveText('src/components · handleSubmit');
  await expect(row.locator('.activity-speed')).toContainText('42.6');
  await expect(row.locator('.activity-timing')).toContainText('上一轮');
  await capture(page,'activity-light');
  const toggle=page.getByRole('button',{name:'展开运行详情',exact:true});
  await toggle.focus();await page.keyboard.press('Enter');
  await expect(page.getByRole('button',{name:'收起运行详情'})).toHaveAttribute('aria-expanded','true');
  await expect(row.locator('code')).toHaveText('grep');
  await show(state('tool_arguments',{tool:'shell',tool_argument_chars:428,tokens_per_second:36.2,throughput_source:'estimate'}));
  await expect(row.getByRole('status')).toHaveText('正在准备工具调用');
  await expect(row.locator('.activity-detail')).toContainText('428 个参数字符，工具尚未执行');
  await expect(row.locator('.activity-speed')).toContainText('≈36.2');
  await capture(page,'activity-details');
  await show(state('thinking',{reasoning_chars:1234}));
  await expect(row.locator('.activity-detail')).toContainText('1,234 个思考字符');
  await expect(row.locator('.activity-subtitle')).toContainText('1,234');
  await show(state('waiting_model'));await expect(row).toContainText('等待模型响应');await expect(row.locator('.activity-speed strong')).toHaveText('—');
  await page.getByRole('button',{name:'收起运行详情'}).click();
  await page.emulateMedia({colorScheme:'dark'});await capture(page,'activity-dark');
  await show(state('executing',{tool:'mcp__workspace__'+ 'long_external_tool_name_'.repeat(8),target:'长路径/'.repeat(60)}));
  await page.getByRole('button',{name:'展开运行详情'}).click();
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(360,430));
  assert(!await row.evaluate(el=>el.scrollWidth>el.clientWidth+1));
  await capture(page,'activity-narrow');
  await show({...state('executing',{tool:'delegate_parallel'}),children:[{status:'running'}]});
  await expect(row.getByRole('status')).toHaveText('子任务执行中');
  await expect(row.locator('.activity-subtitle')).toContainText('1 个子任务');
  await show(state('executing',{tool:'shell'}),true);
  await expect(row.getByRole('status')).toHaveText('正在停止并清理');
  if(await page.getByRole('button',{name:'展开运行详情'}).count())await page.getByRole('button',{name:'展开运行详情'}).click();
  await expect(row.locator('.activity-detail')).toContainText('释放资源');
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await row.locator('button svg').evaluate(el=>getComputedStyle(el).transitionDuration),'0s');
  assert.deepEqual(errors,[]);
  const report={version:require('../package.json').version,mode:'production component with synthetic phase fixtures',paid_api_calls:0,
    checks:['image decode and transparent asset','two-line layout','visible tool and subject','provider and estimated speed labels','keyboard detail disclosure','visible thinking and argument counters','waiting unknown speed','timer outside live region','long tools in narrow dark layout','active child count','stopping feedback','reduced motion'],renderer_errors:errors};
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(app){await app.evaluate(({app})=>app.exit(0)).catch(()=>{});await app.close().catch(()=>{});}});
