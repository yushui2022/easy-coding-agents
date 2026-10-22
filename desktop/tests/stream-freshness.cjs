// Regression test: live output must keep advancing while the model is talking.
// Real hidden Electron + streaming local fixture on a FRESH project (no history,
// so no context compaction sits in front of the turn). Never drives user windows.
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
process.chdir(path.resolve(__dirname, '..'));

const base = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : require('node:os').tmpdir();
fs.mkdirSync(base, {recursive: true});
const home = fs.mkdtempSync(path.join(base, 'eca-freshness-'));
const project = path.join(home, 'freshness-project');
fs.mkdirSync(project, {recursive: true});
fs.writeFileSync(path.join(project, 'README.md'), '# fixture\n');
const python = process.env.ECA_PYTHON || path.resolve('.venv/Scripts/python.exe');

const CHUNKS = 600;
let app;
const sockets = new Set();
const report = {mode: process.env.ECA_TEST_EXE ? 'packaged' : 'development', paid_api_calls: 0, chunks: CHUNKS};
const fixtureRequests = [];
const server = http.createServer(async (req, res) => {
  let raw = ''; for await (const _ of req) raw += _;
  let body = {}; try { body = JSON.parse(raw); } catch { body = {}; }
  fixtureRequests.push({t: Date.now(), url: req.url, stream: !!body.stream, bytes: raw.length});
  // Summarisation and title calls must answer with JSON: an SSE body there would
  // stall the turn before any live text exists.
  if (!body.stream) {
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({id: 'fixture', object: 'chat.completion', created: 0, model: 'fixture',
      choices: [{index: 0, message: {role: 'assistant', content: 'ok'}, finish_reason: 'stop'}],
      usage: {prompt_tokens: 10, completion_tokens: 5, total_tokens: 15}}));
    return;
  }
  res.writeHead(200, {'Content-Type': 'text/event-stream'});
  let n = 0;
  const timer = setInterval(() => {
    res.write('data: ' + JSON.stringify({id: 'fixture', object: 'chat.completion.chunk', created: 0, model: 'fixture',
      choices: [{index: 0, delta: {content: '流'}, finish_reason: null}]}) + '\n\n');
    if (++n >= CHUNKS) { clearInterval(timer); res.end('data: [DONE]\n\n'); }
  }, 8);
  res.on('close', () => clearInterval(timer));
});
server.on('connection', socket => {sockets.add(socket);socket.on('close', () => sockets.delete(socket));});

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const env = {...process.env, TEMP: base, TMP: base,
    ECA_DESKTOP_DATA_HOME: path.join(home, 'app'), ECA_DESKTOP_TEST_HIDDEN: '1', ECA_PYTHON: python,
    ECA_API_KEY: 'freshness-fixture-only', ECA_BASE_URL: `http://127.0.0.1:${server.address().port}/v1`,
    ECA_MODEL: 'fixture', ECA_API_FORMAT: 'openai', NO_PROXY: '127.0.0.1,localhost', no_proxy: '127.0.0.1,localhost'};
  delete env.ELECTRON_RUN_AS_NODE;
  app = await electron.launch(process.env.ECA_TEST_EXE ? {executablePath: process.env.ECA_TEST_EXE, args: [], env} : {args: ['.'], env});
  const page = await app.firstWindow();
  report.version = await app.evaluate(({app}) => app.getVersion());
  await app.evaluate(({BrowserWindow, dialog}, proj) => {
    BrowserWindow.getAllWindows()[0].webContents.setBackgroundThrottling(false);
    dialog.showOpenDialog = async () => ({canceled: false, filePaths: [proj]});
  }, project);
  await expect(page.getByRole('button', {name: '打开项目', exact: false}).first()).toBeVisible();
  await page.getByRole('button', {name: '打开项目', exact: false}).first().click();
  await page.waitForTimeout(1500);

  await page.evaluate(() => {
    window.streamSamples = [];
    const read = () => {const el = document.querySelector('.stream-text'); return el ? el.textContent.length : -1;};
    let last = read();
    const target = document.querySelector('.transcript') || document.body;
    new MutationObserver(() => {
      const length = read();
      if (length !== last) {last = length; window.streamSamples.push({t: performance.now(), length});}
    }).observe(target, {subtree: true, childList: true, characterData: true});
    window.streamStart = performance.now();
  });

  await page.getByLabel('任务指令').fill('stream the whole answer');
  const sentAt = Date.now();
  await page.getByRole('button', {name: '发送任务'}).click();
  const timeline = [];
  for (let i = 0; i < 34; i++) {
    await page.waitForTimeout(250);
    timeline.push(await page.evaluate(async () => {
      const dom = document.querySelector('.stream-text');
      let snap = {};
      try { snap = await window.eca.invoke('snapshot', {preview: true}); } catch { snap = {}; }
      return {busy: snap.busy, phase: snap.activity && snap.activity.phase,
        stream_len: (snap.stream || '').length, dom_len: dom ? dom.textContent.length : null};
    }));
  }

  const metrics = await page.evaluate(() => {
    const samples = window.streamSamples, gaps = [];
    for (let i = 1; i < samples.length; i++) gaps.push(samples[i].t - samples[i - 1].t);
    const sorted = [...gaps].sort((a, b) => a - b);
    return {updates: samples.length, last_chars: samples.length ? samples[samples.length - 1].length : 0,
      first_change_ms: samples.length ? Math.round(samples[0].t - window.streamStart) : null,
      p50_gap_ms: Math.round(sorted[Math.floor(sorted.length * .5)] || 0),
      p95_gap_ms: Math.round(sorted[Math.floor(sorted.length * .95)] || 0),
      max_gap_ms: Math.round(Math.max(0, ...gaps)),
      gaps_over_500ms: gaps.filter(g => g > 500).length};
  });
  report.stream = metrics;
  report.requests = fixtureRequests.map(r => ({...r, ms_after_send: r.t - sentAt}));
  // A second turn separates one-time start-up cost from per-request cost.
  await page.waitForTimeout(2500);
  await page.getByLabel('任务指令').fill('stream again');
  const secondAt = Date.now();
  await page.getByRole('button', {name: '发送任务'}).click();
  await page.waitForTimeout(3000);
  report.second_turn = fixtureRequests.filter(r => r.t >= secondAt).map(r => ({...r, ms_after_send: r.t - secondAt}));
  report.timeline = timeline.map((s, i) => ({ms: (i + 1) * 250, ...s}));
  // Live output must appear, keep appearing, and never stall for half a second.
  if (!metrics.last_chars) throw Error('No live text reached the DOM at all: ' + JSON.stringify(metrics));
  if (metrics.updates < 20) throw Error('Live text barely refreshed: ' + JSON.stringify(metrics));
  if (metrics.max_gap_ms > 500) throw Error('Live text stalled for ' + metrics.max_gap_ms + ' ms: ' + JSON.stringify(metrics));

  const output = path.resolve('../output/performance');
  fs.mkdirSync(output, {recursive: true});
  fs.writeFileSync(path.join(output, 'stream-freshness.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
})().catch(error => {console.error(error.message || error);process.exitCode = 1;}).finally(async () => {
  if (app) {await app.evaluate(({app}) => app.exit(0)).catch(() => {});await app.close().catch(() => {});}
  for (const socket of sockets) socket.destroy();
  server.close();
});
