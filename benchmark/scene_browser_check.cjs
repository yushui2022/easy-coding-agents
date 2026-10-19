/* Bounded hidden browser acceptance for the existing terrarium fixture. */
const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(process.argv[2]);
const base = path.resolve(__dirname, '../output/harness-probe');
if (!root.startsWith(base + path.sep)) throw Error('Expected an isolated probe workspace');
const evidence = path.join(path.dirname(root), 'web-evidence', path.basename(root), String(Date.now()));
const cache = path.join('G:/DevCache/Temp/easy-coding-agents', 'probe-browser');
fs.mkdirSync(evidence, { recursive: true }); fs.mkdirSync(cache, { recursive: true });
app.setPath('userData', cache); app.setPath('sessionData', cache);
app.commandLine.appendSwitch('force-device-scale-factor', '1');
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
app.whenReady().then(async () => {
  const errors = [], checks = {};
  const report = { checks, errors, evidence, rendering: 'Hidden Electron WebGL; device scale 1; capturePage after two animation frames', source_sha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(root, 'index.html'))).digest('hex') };
  const start = Date.now();
  const win = new BrowserWindow({ show: false, width: 960, height: 720,
    webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false, backgroundThrottling: false } });
  const wc = win.webContents;
  async function saveFrame(name) {
    await wc.executeJavaScript('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(true))))');
    const frame=await wc.capturePage(undefined,{stayHidden:true,stayAwake:true});
    if (frame.isEmpty()) throw Error('Empty browser frame');
    fs.writeFileSync(path.join(evidence,name),frame.toPNG());
  }
  wc.on('console-message', event => { if (event.level === 'error') errors.push(event.message); });
  try {
    await wc.loadFile(path.join(root, 'index.html'));
    let state;
    for (let n = 0; n < 250; n++) {
      state = await wc.executeJavaScript(`({canvas:!!document.querySelector('canvas'),
        loaded:document.getElementById('loader')?.classList.contains('hidden'),
        error:document.getElementById('loadErr')?.textContent || ''})`);
      if (state.loaded || state.error || errors.length) break;
      await wait(100);
    }
    report.initial = state; report.loaded_ms = Date.now() - start;
    checks.loaded = !!state.loaded && !!state.canvas && !state.error;
    checks.no_console_errors = errors.length === 0;
    if (!checks.loaded || !checks.no_console_errors) throw Error('Browser initialization failed; see initial and errors');
    await wait(1000);
    const paused = await wc.executeJavaScript(`(() => {const b=document.getElementById('toggle');
      const before=b.getAttribute('aria-pressed'); b.click();
      return {before,after:b.getAttribute('aria-pressed'),text:b.textContent};})()`);
    checks.pause_changes_state = paused.before !== paused.after;
    report.pause = paused;
    await wc.executeJavaScript(`document.getElementById('time').value='500'; document.getElementById('time').dispatchEvent(new Event('input',{bubbles:true}));`);
    await wait(300);
    await saveFrame('day.png');
    const dayPhase = await wc.executeJavaScript(`document.getElementById('phase').textContent`);
    await wc.executeJavaScript(`document.getElementById('time').value='50'; document.getElementById('time').dispatchEvent(new Event('input',{bubbles:true}));`);
    await wait(300);
    await saveFrame('night.png');
    const nightPhase = await wc.executeJavaScript(`document.getElementById('phase').textContent`);
    checks.day_night_changes_phase = dayPhase !== nightPhase;
    const beforeResetErrors = errors.length;
    await wc.executeJavaScript(`document.getElementById('reset').click()`);
    await wait(200);
    checks.reset_without_error = errors.length === beforeResetErrors;
    win.setSize(800, 700);
    for (let n=0; n<30; n++) {
      await wait(100);
      report.responsive = await wc.executeJavaScript(`({width:innerWidth,scroll:document.documentElement.scrollWidth,canvasWidth:document.querySelector('canvas').clientWidth})`);
      if (Math.abs(report.responsive.canvasWidth-report.responsive.width)<2) break;
    }
    checks.no_horizontal_overflow = report.responsive.scroll <= report.responsive.width + 1;
    checks.canvas_fits = report.responsive.canvasWidth <= report.responsive.width + 1 && report.responsive.canvasWidth > 0;
    await saveFrame('narrow.png');
    checks.no_console_errors = errors.length === 0;
  } catch (error) { report.failure = String(error.message); }
  report.passed = !report.failure && Object.values(checks).every(Boolean);
  report.limitations = 'Does not establish visual quality, correct camera framing, drag/zoom, FPS, long-run or cross-browser compatibility.';
  fs.writeFileSync(path.join(evidence, 'report.json'), JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
  win.destroy(); app.exit(report.passed ? 0 : 1);
}).catch(error => { console.error(String(error.message)); app.exit(2); });
