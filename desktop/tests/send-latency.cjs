// Where do the seconds between pressing Enter and the model request go?
// Four timestamps: click (renderer), preparing and waiting_model (backend clocks,
// read from the snapshot) and the first byte of the request (fixture server).
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http'), assert = require('node:assert/strict');
process.chdir(path.resolve(__dirname, '..'));

const base = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : require('node:os').tmpdir();
fs.mkdirSync(base, {recursive: true});
const home = fs.mkdtempSync(path.join(base, 'latency-'));
const project = path.join(home, 'proj');
fs.mkdirSync(project, {recursive: true});
fs.writeFileSync(path.join(project, 'README.md'), '# proj\n');
fs.writeFileSync(path.join(project, 'eca.toml'), '[agent]\nproject_memory = false\nauto_compact = false\nnetwork_retries = 0\n');
const python = process.env.ECA_PYTHON || path.resolve('.venv/Scripts/python.exe');

const arrivals = [];
const server = http.createServer(async (req, res) => {
  let raw = ''; for await (const chunk of req) raw += chunk;
  if (req.method === 'GET') {
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({data: [{id: 'fixture-model', object: 'model'}]}));
    return;
  }
  arrivals.push({at: Date.now(), bytes: raw.length, url: req.url});
  res.writeHead(200, {'Content-Type': 'text/event-stream'});
  res.end('data: ' + JSON.stringify({id: 'fixture', object: 'chat.completion.chunk', created: 0, model: 'fixture-model',
    choices: [{index: 0, delta: {content: '收到'}, finish_reason: 'stop'}]}) + '\n\ndata: [DONE]\n\n');
});

let app, page;
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const env = {...process.env, TEMP: base, TMP: base, ECA_DESKTOP_DATA_HOME: path.join(home, 'data'),
    ECA_DESKTOP_TEST_HIDDEN: '1', ECA_PYTHON: python, ECA_API_KEY: 'fixture',
    ECA_BASE_URL: `http://127.0.0.1:${server.address().port}/v1`, ECA_MODEL: 'fixture-model',
    ECA_API_FORMAT: 'openai', PYTHONUTF8: '1', NO_PROXY: '127.0.0.1,localhost', no_proxy: '127.0.0.1,localhost'};
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.ECA_TEST_EXE;
  app = await electron.launch({args: ['.'], env});
  page = await app.firstWindow();
  const invoke = (method, params = {}) => page.evaluate(([method, params]) => window.eca.invoke(method, params), [method, params]);
  await app.evaluate(({BrowserWindow, dialog}, directory) => {
    BrowserWindow.getAllWindows()[0].setContentSize(1360, 900);
    BrowserWindow.getAllWindows()[0].webContents.setBackgroundThrottling(false);
    dialog.showOpenDialog = async () => ({canceled: false, filePaths: [directory]});
  }, project);
  await page.getByRole('button', {name: '打开项目', exact: true}).click();
  await expect.poll(async () => (await invoke('snapshot')).project).toBe(project);

  // Baseline: one cheap RPC round trip measures renderer -> main -> backend -> back.
  const baseline = [];
  for (let index = 0; index < 5; index++) {
    const start = Date.now(); await invoke('snapshot'); baseline.push(Date.now() - start);
  }

  const composer = page.getByLabel('任务指令');
  const runs = [];
  for (let index = 0; index < 3; index++) {
    await expect.poll(async () => (await invoke('snapshot')).busy, {timeout: 30000}).toBe(false);
    await page.waitForTimeout(300);
    await composer.fill(`第 ${index + 1} 条消息`);
    const before = arrivals.length;
    const clickAt = await page.evaluate(() => {
      const stamp = Date.now();
      window.__sendAt = stamp;
      return stamp;
    });
    await composer.press('Enter');
    let preparing = null, dispatch = null;
    for (let poll = 0; poll < 600; poll++) {
      const state = await page.evaluate(() => window.eca.invoke('snapshot'));
      const activity = state.activity || {};
      if (!preparing && state.busy && activity.since) preparing = Math.round(activity.since * 1000);
      if (activity.phase === 'waiting_model' && activity.since) {dispatch = Math.round(activity.since * 1000); break;}
      await page.waitForTimeout(20);
    }
    for (let wait = 0; wait < 400 && arrivals.length === before; wait++) await page.waitForTimeout(10);
    const arrived = arrivals[before]?.at ?? null;
    runs.push({click_to_preparing: preparing ? preparing - clickAt : null,
      preparing_to_dispatch: preparing && dispatch ? dispatch - preparing : null,
      dispatch_to_server: arrived && dispatch ? arrived - dispatch : null,
      click_to_server: arrived ? arrived - clickAt : null});
  }
  const median = values => values.length ? [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)] : null;

  // Arm C: same direct send, but nothing polls the backend while the request is in
  // flight, so the measurement does not compete with the run it is measuring.
  const quiet = [];
  for (let index = 0; index < 4; index++) {
    await expect.poll(async () => (await invoke('snapshot')).busy, {timeout: 30000}).toBe(false);
    await page.waitForTimeout(400);
    const before = arrivals.length;
    const clickAt = Date.now();
    await invoke('task.start', {prompt: `安静 ${index + 1}`});
    for (let wait = 0; wait < 600 && arrivals.length === before; wait++) await page.waitForTimeout(5);
    quiet.push({click_to_server: arrivals[before] ? arrivals[before].at - clickAt : null});
  }


  // Arm B: send the same way without the composer or the renderer's own bookkeeping,
  // so a difference points at renderer/main work rather than the backend.
  const direct = [];
  for (let index = 0; index < 3; index++) {
    await expect.poll(async () => (await invoke('snapshot')).busy, {timeout: 30000}).toBe(false);
    await page.waitForTimeout(300);
    const before = arrivals.length;
    const clickAt = Date.now();
    await invoke('task.start', {prompt: `直接 ${index + 1}`});
    const acceptAt = Date.now();
    let dispatch = null;
    for (let poll = 0; poll < 600; poll++) {
      const state = await page.evaluate(() => window.eca.invoke('snapshot'));
      const activity = state.activity || {};
      if (activity.phase === 'waiting_model' && activity.since) {dispatch = Math.round(activity.since * 1000); break;}
      await page.waitForTimeout(20);
    }
    for (let wait = 0; wait < 400 && arrivals.length === before; wait++) await page.waitForTimeout(10);
    const arrived = arrivals[before]?.at ?? null;
    direct.push({invoke_ms: acceptAt - clickAt, preparing_to_dispatch: dispatch ? dispatch - acceptAt : null,
      dispatch_to_server: arrived && dispatch ? arrived - dispatch : null,
      click_to_server: arrived ? arrived - clickAt : null});
  }

  const report = {version: await app.evaluate(({app}) => app.getVersion()),
    baseline_rpc_ms: median(baseline), runs, direct, quiet,
    quiet_median: median(quiet.map(r => r.click_to_server)),
    get_requests: arrivals.filter(row => (row.url || '').includes('models')).length,
    median: {click_to_preparing: median(runs.map(r => r.click_to_preparing)),
      preparing_to_dispatch: median(runs.map(r => r.preparing_to_dispatch)),
      dispatch_to_server: median(runs.map(r => r.dispatch_to_server)),
      click_to_server: median(runs.map(r => r.click_to_server))}};
  // Budgets, not printouts: this test exists so the one-time SDK setup can never
  // quietly move back onto the first message. Measured medians here are ~60 ms
  // (composer) and ~36 ms (direct); the ceilings leave room for a slow machine.
  assert.equal(arrivals.length >= 10, true, 'every send must reach the model');
  assert.equal(report.get_requests, 0, 'sending a message must not fetch the model list');
  assert.equal(runs[0].click_to_server < 900, true,
    `first message took ${runs[0].click_to_server} ms to reach the model`);
  assert.equal(report.quiet_median < 200, true,
    `steady-state send took ${report.quiet_median} ms to reach the model`);
  console.log(JSON.stringify(report, null, 1));
  fs.writeFileSync(path.resolve('../output/playwright/send-latency.json'), JSON.stringify(report, null, 1));
  await app.close();
  server.close();
})().catch(async error => {
  console.error(String(error && error.stack || error));
  try { if (app) await app.close(); } catch {}
  server.close();
  process.exit(1);
});
