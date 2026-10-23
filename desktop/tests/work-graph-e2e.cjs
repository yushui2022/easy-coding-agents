// Hidden app + local model fixture: the todo plan is a dependency graph. A task
// whose prerequisite is unfinished shows as blocked, and the backend refuses to
// let the model mark it completed.
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http'), assert = require('node:assert/strict');
process.chdir(path.resolve(__dirname, '..'));

const base = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : require('node:os').tmpdir();
fs.mkdirSync(base, {recursive: true});
const home = fs.mkdtempSync(path.join(base, 'work-graph-'));
const project = path.join(home, 'proj');
fs.mkdirSync(project, {recursive: true});
fs.writeFileSync(path.join(project, 'README.md'), '# proj\n');
fs.writeFileSync(path.join(project, 'eca.toml'), '[agent]\nproject_memory = false\nauto_compact = false\nnetwork_retries = 0\n');
const output = path.resolve('../output/playwright/work-graph');
fs.mkdirSync(output, {recursive: true});
const python = process.env.ECA_PYTHON || path.resolve('.venv/Scripts/python.exe');

const requests = [], errors = [];
const call = (name, args, id) => ({id: 'fixture', choices: [{index: 0, delta: {tool_calls: [{index: 0, id, type: 'function',
  function: {name, arguments: JSON.stringify(args)}}]}, finish_reason: 'tool_calls'}]});
const text = value => ({id: 'fixture', choices: [{index: 0, delta: {content: value}, finish_reason: 'stop'}]});

const server = http.createServer(async (req, res) => {
  let raw = ''; for await (const chunk of req) raw += chunk;
  if (req.method === 'GET') {
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({data: [{id: 'fixture-model', object: 'model'}]}));
    return;
  }
  let payload = {};
  try { payload = JSON.parse(raw); } catch { payload = {}; }
  requests.push(payload);
  const messages = payload.messages || [];
  const afterTool = (messages.slice(-1)[0] || {}).role === 'tool';
  const users = messages.filter(m => m.role === 'user')
    .map(m => JSON.stringify(m.content || '')).filter(value => !value.includes('[Runtime guidance]'));
  const lastUser = users.slice(-1)[0] || '';
  res.writeHead(200, {'Content-Type': 'text/event-stream'});
  let body;
  if (afterTool) body = text('已收到');
  else if (lastUser.includes('依赖计划')) body = call('todo', {items: [
    {content: '迁移数据库', status: 'in_progress', id: 'db'},
    {content: '部署服务', status: 'pending', id: 'ship', depends_on: ['db']},
    {content: '写说明', status: 'pending', id: 'notes'}]}, 'call_plan');
  else if (lastUser.includes('标记完成')) body = call('todo', {items: [
    {content: '迁移数据库', status: 'failed', id: 'db'},
    {content: '部署服务', status: 'completed', id: 'ship', depends_on: ['db']},
    {content: '写说明', status: 'pending', id: 'notes'}]}, 'call_force');
  else body = text('好的');
  res.end('data: ' + JSON.stringify(body) + '\n\ndata: [DONE]\n\n');
});

const report = {version: null, blocked_items: 0, badge: '', locked: false, completed_items: 0,
  header_blocked: '', refusal: '', paid_api_calls: 0};
let app, page;
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const env = {...process.env, TEMP: base, TMP: base, ECA_DESKTOP_DATA_HOME: path.join(home, 'data'),
    ECA_DESKTOP_TEST_HIDDEN: '1', ECA_PYTHON: python, ECA_API_KEY: 'fixture',
    ECA_BASE_URL: `http://127.0.0.1:${server.address().port}/v1`, ECA_MODEL: 'fixture-model',
    ECA_API_FORMAT: 'openai', PYTHONUTF8: '1', NO_PROXY: '127.0.0.1,localhost', no_proxy: '127.0.0.1,localhost'};
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.ECA_TEST_EXE;
  app = await electron.launch(process.env.ECA_TEST_EXE
    ? {executablePath: process.env.ECA_TEST_EXE, args: [], env}
    : {args: ['.'], env});
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

  const composer = page.getByLabel('任务指令');
  await composer.fill('按依赖计划建立工作图');
  await composer.press('Enter');
  await expect(page.locator('.plan-item.is-blocked')).toHaveCount(1);
  await expect(page.locator('.plan-item.is-blocked')).toContainText('部署服务');
  report.blocked_items = await page.locator('.plan-item.is-blocked').count();
  report.badge = (await page.locator('.plan-item.is-blocked .plan-badge').textContent() || '').trim();
  report.locked = await page.locator('.plan-item.is-blocked svg').count() === 1;
  report.completed_items = await page.locator('.plan-item.is-completed').count();
  report.header_blocked = (await page.locator('.plan-count.is-blocked').textContent() || '').trim();
  await page.screenshot({path: path.join(output, 'blocked-plan.png'), animations: 'disabled'}).catch(() => {});

  // The dependency is failed here, so the dependent must not be accepted as done.
  await composer.fill('把部署标记完成');
  await composer.press('Enter');
  await expect(page.locator('.messages')).toContainText('cannot be completed', {timeout: 30000});
  report.refusal = 'shown';
  await expect(page.locator('.plan-item.is-blocked')).toHaveCount(1);
  assert.equal(await page.locator('.plan-item.is-completed').count(), 0, 'a blocked task must never render as completed');
  await page.screenshot({path: path.join(output, 'refused.png'), animations: 'disabled'}).catch(() => {});

  assert.equal(errors.length, 0, `renderer errors: ${errors.join(' | ')}`);
  fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
  await app.close();
  server.close();
})().catch(async error => {
  console.error(String(error && error.stack || error));
  try { if (page) console.error('transcript:', (await page.locator('.messages').innerText()).slice(-1500)); } catch {}
  console.error('model requests:', requests.length);
  try { if (app) await app.close(); } catch {}
  server.close();
  process.exit(1);
});
