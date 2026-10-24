// Hidden app + local model fixture: create a schedule, let the real scheduler fire
// it, and confirm the run becomes a session in its project with a recorded result.
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http'), assert = require('node:assert/strict');
process.chdir(path.resolve(__dirname, '..'));

const base = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : require('node:os').tmpdir();
fs.mkdirSync(base, {recursive: true});
const home = fs.mkdtempSync(path.join(base, 'automations-'));
const project = path.join(home, 'proj');
fs.mkdirSync(project, {recursive: true});
fs.writeFileSync(path.join(project, 'README.md'), '# proj\n');
fs.writeFileSync(path.join(project, 'eca.toml'), '[agent]\nproject_memory = false\nauto_compact = false\nnetwork_retries = 0\n');
const output = path.resolve('../output/playwright/automations');
fs.mkdirSync(output, {recursive: true});
const python = process.env.ECA_PYTHON || path.resolve('.venv/Scripts/python.exe');

const requests = [], errors = [];
const server = http.createServer(async (req, res) => {
  let raw = ''; for await (const chunk of req) raw += chunk;
  if (req.method === 'GET') {
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({data: [{id: 'fixture-model', object: 'model'}]}));
    return;
  }
  let payload = {}; try { payload = JSON.parse(raw); } catch { payload = {}; }
  if (payload.stream) requests.push(payload);
  res.writeHead(200, {'Content-Type': 'text/event-stream'});
  res.end('data: ' + JSON.stringify({id: 'fixture', object: 'chat.completion.chunk', created: 0, model: 'fixture-model',
    choices: [{index: 0, delta: {content: '巡检完成：没有新的失败测试。下次继续观察。'}, finish_reason: 'stop'}]}) + '\n\ndata: [DONE]\n\n');
});

let app, page;
const report = {version: null, schedule_text: '', pane_rows: 0, run_status: '', scheduled_runs: 0,
  session_in_project: false, history_entries: 0, memory_written: false, paid_api_calls: 0};

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const env = {...process.env, TEMP: base, TMP: base, ECA_DESKTOP_DATA_HOME: path.join(home, 'data'),
    ECA_DESKTOP_TEST_HIDDEN: '1', ECA_PYTHON: python, ECA_API_KEY: 'fixture',
    ECA_BASE_URL: `http://127.0.0.1:${server.address().port}/v1`, ECA_MODEL: 'fixture-model',
    ECA_API_FORMAT: 'openai', PYTHONUTF8: '1', NO_PROXY: '127.0.0.1,localhost', no_proxy: '127.0.0.1,localhost'};
  delete env.ECA_AUTOMATIONS_DIR;
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.ECA_TEST_EXE;
  app = await electron.launch({args: ['.'], env});
  page = await app.firstWindow();
  page.on('pageerror', error => errors.push(String(error)));
  report.version = await app.evaluate(({app}) => app.getVersion());
  const invoke = (method, params = {}) => page.evaluate(([method, params]) => window.eca.invoke(method, params), [method, params]);
  await app.evaluate(({BrowserWindow, dialog}, directory) => {
    BrowserWindow.getAllWindows()[0].setContentSize(1360, 900);
    BrowserWindow.getAllWindows()[0].webContents.setBackgroundThrottling(false);
    dialog.showOpenDialog = async () => ({canceled: false, filePaths: [directory]});
  }, project);
  await page.getByRole('button', {name: '打开项目', exact: true}).click();
  await expect.poll(async () => (await invoke('snapshot')).project).toBe(project);
  const automationsRoot = path.join(home, 'data', 'automations');
  assert(fs.existsSync(automationsRoot) === false || fs.readdirSync(automationsRoot).length === 0,
    'a fresh profile must start with no schedules');

  // The pane lists what the backend holds; a schedule due every minute is the
  // only way to watch the real scheduler fire without waiting for a clock time.
  const start = new Date(Date.now() - 60000), pad = value => String(value).padStart(2, '0');
  const stamp = `${start.getFullYear()}${pad(start.getMonth() + 1)}${pad(start.getDate())}T${pad(start.getHours())}${pad(start.getMinutes())}00`;
  const created = await invoke('automations.save', {automation: {
    name: '每分钟巡检', prompt: '检查项目里有没有新的失败测试，用 3 行总结。',
    rrule: `DTSTART:${stamp}\nRRULE:FREQ=MINUTELY;INTERVAL=1`,
    project, permission: 'read_only', notification: 'always'}});
  report.schedule_text = created.saved.schedule;

  await page.getByRole('button', {name: '定时任务'}).click();
  await expect(page.locator('.automations-pane')).toBeVisible();
  await expect(page.locator('.automation-row')).toHaveCount(1);
  await expect(page.locator('.automation-row')).toContainText('每分钟巡检');
  report.pane_rows = await page.locator('.automation-row').count();
  await page.screenshot({path: path.join(output, 'automations-pane.png'), animations: 'disabled'}).catch(() => {});

  // Wait for the scheduler tick to fire it; the run itself is a full ECA session.
  await expect.poll(async () => {
    const state = await invoke('automations.list');
    const row = state.automations[0];
    return row?.last_status || '';
  }, {timeout: 120000, intervals: [1000]}).not.toBe('');
  const listing = await invoke('automations.list');
  report.run_status = listing.automations[0].last_status;
  report.scheduled_runs = 1;
  await expect(page.locator('.automation-row')).toContainText('成功', {timeout: 30000});
  await page.screenshot({path: path.join(output, 'automations-done.png'), animations: 'disabled'}).catch(() => {});

  const sessionId = listing.automations[0].last_session;
  assert(sessionId, 'a run must record the session it created');
  const snapshot = await invoke('snapshot');
  const sessions = (snapshot.projects || []).flatMap(group => group.sessions || []);
  report.session_in_project = sessions.some(session => session.id === sessionId);
  assert(report.session_in_project, 'the scheduled run must show up as a session in its project');

  const history = await invoke('automations.history', {id: listing.automations[0].id});
  report.history_entries = history.runs.length;
  assert(report.history_entries >= 1, 'the run must be recorded in history');
  assert.equal(history.runs[0].status, 'succeeded', 'the fixture model should make the run succeed');
  report.memory_written = fs.existsSync(path.join(automationsRoot, listing.automations[0].id, 'memory.md'));
  assert(report.memory_written, 'the harness must append the run summary to memory.md');

  // A manual run must not overlap a scheduled one and must be recorded as manual.
  await page.locator('.automation-row .automation-buttons button').first().click();
  await expect.poll(async () => {
    const runs = (await invoke('automations.history', {id: listing.automations[0].id})).runs;
    return runs.some(run => run.trigger === 'manual' && run.status !== 'running') ? 'yes' : 'no';
  }, {timeout: 120000, intervals: [1000]}).toBe('yes');

  await page.getByRole('button', {name: '删除'}).first().click().catch(() => {});
  assert.equal(errors.length, 0, `renderer errors: ${errors.join(' | ')}`);
  assert(report.paid_api_calls === 0);
  fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
  await app.close();
  server.close();
})().catch(async error => {
  console.error(String(error && error.stack || error));
  try { if (page) console.error('pane:', (await page.locator('.automations-pane').innerText()).slice(0, 1500)); } catch {}
  console.error('model stream requests:', requests.length);
  try { if (app) await app.close(); } catch {}
  server.close();
  process.exit(1);
});
