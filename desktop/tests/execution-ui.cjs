// Isolated, hidden Electron window. This never drives an existing user window.
const {_electron:electron,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path');
const {execFileSync}=require('node:child_process');
process.chdir(path.resolve(__dirname,'..'));
const base='G:/DevCache/Temp/easy-coding-agents';
const home=fs.mkdtempSync(path.join(base,'eca-execution-'));
const project=path.join(home,'场景 工作区');
const python=process.env.ECA_PYTHON||path.resolve('.venv/Scripts/python.exe');
execFileSync(python,['-B','tests/seed-execution.py',project],{windowsHide:true,env:{...process.env,TEMP:base,TMP:base,PYTHONUTF8:'1'}});
const output=path.resolve('../output/playwright');fs.mkdirSync(output,{recursive:true});
let app;const errors=[];const report={paid_api_calls:0,fixture:'Synthetic tool sequence; real read-tool image rejection; no scene validation claimed.'};
async function capture(name,selector) {
  const bounds=selector?await (await app.firstWindow()).locator(selector).boundingBox():undefined;
  const bytes=await app.evaluate(async({BrowserWindow},bounds)=>{
    const win=BrowserWindow.getAllWindows()[0];
    await win.webContents.executeJavaScript('document.fonts.ready.then(async()=>{await Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{})));await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));})');
    const rect=bounds?{x:Math.floor(bounds.x),y:Math.floor(bounds.y),width:Math.ceil(bounds.width),height:Math.ceil(bounds.height)}:undefined;
    return (await win.webContents.capturePage(rect,{stayHidden:true,stayAwake:true})).toPNG().toString('base64');
  },bounds);
  fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(bytes,'base64'));
}
(async()=>{
  const env={...process.env,TEMP:base,TMP:base,ECA_DESKTOP_DATA_HOME:path.join(home,'app'),ECA_DESKTOP_TEST_HIDDEN:'1',ECA_PYTHON:python};
  delete env.ELECTRON_RUN_AS_NODE;
  for(const key of ['ECA_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'])delete env[key];
  app=await electron.launch(process.env.ECA_TEST_EXE?{executablePath:process.env.ECA_TEST_EXE,args:[],env}:{args:['.'],env});
  const page=await app.firstWindow();page.on('pageerror',e=>errors.push(String(e)));
  await app.evaluate(({BrowserWindow,dialog},project)=>{
    const win=BrowserWindow.getAllWindows()[0];win.webContents.setBackgroundThrottling(false);win.setContentSize(1280,880);
    dialog.showOpenDialog=async()=>({canceled:false,filePaths:[project]});
  },project);
  await page.getByRole('button',{name:'打开项目',exact:false}).first().click();
  const group=page.getByRole('region',{name:'执行记录'});
  await expect(group).toHaveCount(1);
  await expect(group).toContainText('8 项操作');
  await expect(group.locator('.tool-record')).toHaveCount(5);
  await expect(group.locator('.outcome-error')).toHaveCount(2);
  await expect(group.locator('.tool-error-hint').first()).toHaveText('文本读取工具无法查看图片内容');
  await expect(group.locator('.tool-target').first()).toContainText('glass-terrarium/shot.png');
  await expect(group.locator('pre')).toHaveCount(0);
  await expect(page.locator('.message.assistant .message-label')).toHaveCount(1);
  // Each turn carries a copy button; the text is copied by the desktop process.
  const savedClipboard=await app.evaluate(({clipboard})=>clipboard.readText());
  await expect(page.locator('.message.user .message-copy')).toHaveCount(1);
  const copy=page.locator('.message.assistant .message-copy').first();
  await expect(copy).toContainText('复制');
  await copy.click();
  await expect(copy).toContainText('已复制');
  const copied=await app.evaluate(({clipboard})=>clipboard.readText());
  expect(copied).toContain('先检查场景文件和本地运行环境，再执行页面检查。');
  await capture('message-copy');
  await app.evaluate(({clipboard},text)=>clipboard.writeText(text),savedClipboard);
  // The composer reports a local context estimate, never a billing number.
  const meter=page.locator('.context-meter').first();
  await expect(meter).toBeVisible();
  await expect(meter.locator('span')).toHaveText(/^\d{1,3}%$/);
  await expect(meter).toHaveAttribute('title',/本地估算/);
  report.context_meter=await meter.locator('span').innerText();
  // Thinking is shown as a collapsed block inside the assistant turn.
  const thinking=page.locator('.message.assistant .message-reasoning').first();
  await expect(thinking).toBeVisible();
  await expect(thinking.locator('summary')).toContainText('思考');
  await expect(thinking.locator('.message-reasoning-text')).toBeHidden();
  await thinking.locator('summary').click();
  await expect(thinking.locator('.message-reasoning-text')).toBeVisible();
  await expect(thinking.locator('.message-reasoning-text')).toContainText('先看目录结构');
  await capture('message-reasoning');
  report.thinking_block='passed';
  // The user turn is a rounded bubble, right aligned, without a role label.
  const bubble=page.locator('.message.user').first();
  const bubbleStyle=await bubble.evaluate(el=>{const s=getComputedStyle(el),r=el.getBoundingClientRect();return {bg:s.backgroundColor,radius:s.borderTopLeftRadius,width:Math.round(r.width),height:Math.round(r.height),overflow:el.scrollHeight-el.clientHeight};});
  expect(bubbleStyle.bg).not.toBe('rgba(0, 0, 0, 0)');
  expect(parseFloat(bubbleStyle.radius)).toBeGreaterThan(8);
  const bubbleBox=await bubble.boundingBox();
  const transcriptBox=await page.locator('.transcript').boundingBox();
  expect(bubbleBox.width).toBeLessThan(transcriptBox.width*0.85);
  expect(bubbleBox.x+bubbleBox.width).toBeGreaterThan(transcriptBox.x+transcriptBox.width*0.85);
  // A one-line message stays a one-line bubble: the copy action must not add height.
  expect(bubbleStyle.height).toBeLessThan(70);
  await expect(bubble.locator('.message-label')).toBeHidden();
  expect(await bubble.locator('.message-copy').evaluate(el=>getComputedStyle(el).opacity)).toBe('0');
  await bubble.hover();
  await expect.poll(()=>bubble.locator('.message-copy').evaluate(el=>getComputedStyle(el).opacity)).toBe('1');
  report.user_message=bubbleStyle;
  await meter.click();
  const menu=page.getByRole('dialog',{name:'上下文设置'});
  await expect(menu).toBeVisible();
  await expect(menu.getByRole('button',{name:/压缩上下文|任务运行中/})).toBeVisible();
  await expect(menu).toContainText('本地估算');
  await expect(menu.locator('.context-part').first()).toBeVisible();
  await expect(menu.locator('.context-part-value').first()).toHaveText(/^\d{1,3}%$/);
  report.context_parts=await menu.locator('.context-part').count();
  await page.keyboard.press('Escape');
  await expect(menu).toHaveCount(0);
  // The meter sits left of the model chip in the composer actions.
  await expect(page.locator('.composer-actions .context-meter')).toHaveCount(1);
  // The window is frameless: our own title bar replaces the native one. A native
  // title bar would subtract roughly 30 px from the content height; only the
  // invisible resize border (about 2 px) may remain here.
  const sizes=await app.evaluate(({BrowserWindow})=>{const w=BrowserWindow.getAllWindows()[0];return {bounds:w.getBounds().height,content:w.getContentSize()[1]};});
  expect(Math.abs(sizes.bounds-sizes.content)).toBeLessThan(8);
  await expect(page.locator('.titlebar')).toBeVisible();
  await expect(page.locator('.titlebar-controls button')).toHaveCount(3);
  const dragRegion=await page.locator('.titlebar-drag').evaluate(el=>getComputedStyle(el).getPropertyValue('-webkit-app-region').trim());
  expect(dragRegion==='drag'||dragRegion==='').toBe(true);
  await capture('titlebar','.titlebar');
  report.window_titlebar={frameless:Math.abs(sizes.bounds-sizes.content)<8,controls:3,difference:sizes.bounds-sizes.content};
  // The model picker is a flat list: model name, provider, check, then the slider.
  await page.locator('.model-chip').click();
  const picker=page.getByRole('dialog',{name:'选择模型'});
  await expect(picker).toBeVisible();
  await expect(picker.locator('.model-menu-heading')).toHaveCount(0);
  const pickerRows=await picker.locator('.model-menu-row').count();
  if(pickerRows){
    await expect(picker.locator('.model-menu-provider').first()).toHaveText(/\S+/);
    await expect(picker.locator('.model-effort-stops button').first()).toBeVisible();
  } else {
    await expect(picker.locator('.model-menu-empty')).toBeVisible();
  }
  report.model_picker={rows:pickerRows,effort_stops:await picker.locator('.model-effort-stops button').count(),headings:0};
  await capture('model-picker','.model-menu');
  await page.keyboard.press('Escape');
  await expect(picker).toHaveCount(0);
  // Sidebar project rows read from the left edge; the base button rule centres content.
  const rowAlign=await page.locator('.project-group-heading').first().evaluate(el=>{
    const head=el.getBoundingClientRect(),caret=el.querySelector('.project-disclosure').getBoundingClientRect();
    const title=el.querySelector('.project-title'),titleBox=title.getBoundingClientRect();
    const icon=title.querySelector('svg').getBoundingClientRect();
    return {justify:getComputedStyle(title).justifyContent,offset:Math.round(titleBox.left-head.left),iconGap:Math.round(icon.left-caret.right)};
  });
  expect(rowAlign.justify).toBe('flex-start');
  expect(rowAlign.offset).toBeLessThan(24);
  expect(rowAlign.iconGap).toBeLessThan(16);
  report.project_row_alignment=rowAlign;
  report.compact_height=await group.evaluate(el=>Math.round(el.getBoundingClientRect().height));
  await capture('execution-compact');
  const cdp=await page.context().newCDPSession(page);
  await cdp.send('DOM.enable');await cdp.send('CSS.enable');
  const doc=await cdp.send('DOM.getDocument');
  report.fonts={};
  for(const selector of ['.message.user p','.open-project','.workspace-header strong']){
    const {nodeId}=await cdp.send('DOM.querySelector',{nodeId:doc.root.nodeId,selector});
    report.fonts[selector]=await cdp.send('CSS.getPlatformFontsForNode',{nodeId});
  }
  await cdp.detach();
  console.log(JSON.stringify({fonts:report.fonts}));
  await capture('composer-footer','.composer-meta');
  await group.getByRole('button',{name:'查看全部 8 项操作'}).click();
  await expect(group.locator('.tool-record')).toHaveCount(8);
  const tool=group.locator('.tool-record').nth(1);
  await tool.locator('summary').focus();await page.keyboard.press('Enter');
  await expect(tool).toHaveAttribute('open','');
  await expect(tool.locator('pre').first()).toContainText('Get-ChildItem -LiteralPath $base');
  await tool.getByRole('button',{name:'加载完整工具记录'}).click();
  await expect(tool.getByRole('button',{name:'加载完整工具记录'})).toHaveCount(0);
  await expect(tool.locator('pre').last()).toContainText('Synthetic fixture result');
  await group.getByRole('button',{name:'收起已返回操作'}).click();
  await expect(tool).toHaveAttribute('open',''); // Opened row remains pinned while other successes fold.
  await capture('execution-expanded');
  await tool.locator('summary').click();await expect(group.locator('.tool-record')).toHaveCount(5);
  await page.emulateMedia({colorScheme:'dark'});
  await expect.poll(()=>page.evaluate(()=>matchMedia('(prefers-color-scheme: dark)').matches)).toBe(true);
  await capture('execution-dark');
  await app.evaluate(({BrowserWindow})=>{BrowserWindow.getAllWindows()[0].setContentSize(820,880);});
  if(await page.getByRole('button',{name:'收起任务详情',exact:true}).isVisible())await page.getByRole('button',{name:'收起任务详情',exact:true}).click();
  await expect(page.locator('.conversation')).toBeVisible();
  await capture('execution-narrow');
  const overflow=await group.evaluate(el=>el.scrollWidth>el.clientWidth+1);
  if(overflow)throw Error('Execution group overflows narrow layout');
  await page.reload();
  await expect(page.getByRole('region',{name:'执行记录'}).locator('.outcome-error')).toHaveCount(2);
  await page.emulateMedia({colorScheme:'light'});
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1440,900));
  await page.getByRole('button',{name:'新建会话',exact:true}).click();
  await expect(page.locator('.welcome h1')).toBeVisible();
  await page.locator('.welcome-art').evaluate(image=>image.decode());
  await expect(page.getByRole('button',{name:'切换工作项目'})).toHaveText('场景 工作区');
  await expect(page.locator('.model-chip')).toContainText('关闭');
  await page.getByRole('button',{name:'了解项目',exact:true}).click();
  await expect(page.getByLabel('任务指令')).toHaveValue('梳理项目结构、运行方式和核心模块，先不要修改代码。');
  await expect(page.getByLabel('任务指令')).toBeFocused();
  await page.getByLabel('任务指令').fill('');
  await page.mouse.move(2, 2);
  await capture('visual-welcome-focus-light');
  await page.emulateMedia({colorScheme:'dark'});
  await capture('visual-welcome-focus-dark');
  await page.emulateMedia({colorScheme:'light'});
  await page.getByRole('button',{name:'收起导航',exact:true}).click();
  await page.mouse.move(2, 2);
  await capture('visual-welcome-minimal-light');
  await page.getByRole('button',{name:'展开导航',exact:true}).click();
  await page.getByRole('button',{name:'任务详情',exact:true}).click();
  await expect(page.locator('.workspace-panel')).toBeVisible();
  await capture('visual-welcome-light');
  await page.emulateMedia({colorScheme:'dark'});
  await capture('visual-welcome-dark');
  await page.emulateMedia({colorScheme:'light'});
  await page.getByRole('button',{name:'模型与设置',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'模型与设置'})).toBeVisible();
  await capture('visual-settings-light');
  await page.emulateMedia({colorScheme:'dark'});await capture('visual-settings-dark');
  await page.getByRole('button',{name:'关闭设置'}).click();
  await page.emulateMedia({colorScheme:'light'});
  await page.getByRole('button',{name:'新建侧边聊天',exact:true}).click();
  await expect(page.getByLabel('侧边聊天输入')).toBeVisible();
  await capture('visual-sidechat-light');
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(820,680));
  await expect(page.locator('.eca-app')).toHaveClass(/workspace-full/);
  await page.keyboard.press('Escape');
  await expect(page.getByLabel('任务指令')).toBeVisible();
  await page.getByLabel('任务指令').fill('检查窄窗口输入与布局');
  await capture('visual-welcome-narrow');
  // Theme: system -> light -> dark -> system, applied through nativeTheme.
  await page.setViewportSize({width:1360,height:860});
  // Drop the media emulation used by the screenshots above, otherwise it overrides
  // the real prefers-color-scheme value that nativeTheme controls.
  await page.emulateMedia({colorScheme:null});
  const themeButton=page.locator('.theme-toggle').first();
  await expect(themeButton).toBeVisible();
  const darkNow=()=>page.evaluate(()=>matchMedia('(prefers-color-scheme: dark)').matches);
  await themeButton.click();
  await expect(themeButton).toHaveAttribute('aria-label',/浅色/);
  await expect.poll(darkNow).toBe(false);
  await themeButton.click();
  await expect(themeButton).toHaveAttribute('aria-label',/深色/);
  await expect.poll(darkNow).toBe(true);
  await themeButton.click();
  await expect(themeButton).toHaveAttribute('aria-label',/跟随系统/);
  report.theme_toggle='passed';

  report.checks=['grouping','visible failures','relative paths','lazy output','keyboard expansion','full records','opened-row pinning','dark and narrow layouts','reload','welcome and settings in both themes','side chat empty state','narrow workspace Escape and editable composer','thinking badge and quick task draft without submission','local welcome image and project context'];
  report.renderer_errors=errors;if(errors.length)throw Error(errors.join('\n'));
  report.version=await app.evaluate(({app})=>app.getVersion());
  fs.writeFileSync(path.join(output,'execution-ui-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{
  if(app){await app.evaluate(({app})=>app.exit(0)).catch(()=>{});await app.close().catch(()=>{});}
});
