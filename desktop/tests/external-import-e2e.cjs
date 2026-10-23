// Import a synthetic Codex session into a real hidden ECA window and continue there.
// Uses a throwaway ECA_CODEX_HOME so the machine's real history is never touched.
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), http = require('node:http');
process.chdir(path.resolve(__dirname, '..'));

const base = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : require('node:os').tmpdir();
fs.mkdirSync(base, {recursive: true});
const home = fs.mkdtempSync(path.join(base, 'eca-import-'));
const codexHome = path.join(home, 'codex');
const rollout = path.join(codexHome, 'sessions', '2026', '10', '22', 'rollout-2026-10-22T09-00-00-abc.jsonl');
fs.mkdirSync(path.dirname(rollout), {recursive: true});
const records = [
  {type: 'session_meta', payload: {id: 'abc'}},
  {type: 'response_item', timestamp: '2026-10-22T09:00:01Z',
   payload: {type: 'message', role: 'user', content: [{type: 'input_text', text: '第一句问题：帮我看看这个仓库'}]}},
  {type: 'response_item', timestamp: '2026-10-22T09:00:02Z',
   payload: {type: 'message', role: 'assistant', content: [{type: 'output_text', text: '第一句回答：看过了，结构正常。'}]}},
];
fs.writeFileSync(rollout, records.map(record => JSON.stringify(record)).join('\n') + '\n');
const before = crypto.createHash('sha256').update(fs.readFileSync(rollout)).digest('hex');
const project = path.join(home, 'proj');
fs.mkdirSync(project, {recursive: true});
fs.writeFileSync(path.join(project, 'README.md'), '# proj\n');
const python = process.env.ECA_PYTHON || path.resolve('.venv/Scripts/python.exe');

let app;
const sockets = new Set();
const bodies = [];
const server = http.createServer(async (req, res) => {
  let raw = ''; for await (const chunk of req) raw += chunk;
  let body = {}; try { body = JSON.parse(raw); } catch { body = {}; }
  if (body.stream) bodies.push(body);
  if (!body.stream) {
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({id: 'f', object: 'chat.completion', created: 0, model: 'fixture',
      choices: [{index: 0, message: {role: 'assistant', content: 'ok'}, finish_reason: 'stop'}],
      usage: {prompt_tokens: 5, completion_tokens: 1, total_tokens: 6}}));
    return;
  }
  res.writeHead(200, {'Content-Type': 'text/event-stream'});
  res.write('data: ' + JSON.stringify({id: 'f', object: 'chat.completion.chunk', created: 0, model: 'fixture',
    choices: [{index: 0, delta: {content: '继续的话题已收到。'}, finish_reason: 'stop'}]}) + '\n\n');
  res.end('data: [DONE]\n\n');
});
server.on('connection', socket => {sockets.add(socket);socket.on('close', () => sockets.delete(socket));});

const report = {version: null, imported: false, session_title: '', messages: 0, note_present: false,
  source_untouched: false, continued: false, paid_api_calls: 0};

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const env = {...process.env, TEMP: base, TMP: base, ECA_DESKTOP_DATA_HOME: path.join(home, 'app'),
    ECA_DESKTOP_TEST_HIDDEN: '1', ECA_PYTHON: python, ECA_CODEX_HOME: codexHome,
    ECA_API_KEY: 'fixture', ECA_BASE_URL: `http://127.0.0.1:${server.address().port}/v1`,
    ECA_MODEL: 'fixture', ECA_API_FORMAT: 'openai', NO_PROXY: '127.0.0.1,localhost', no_proxy: '127.0.0.1,localhost',
    ECA_CLAUDE_HOME: path.join(home, 'none-claude'), ECA_WORKBUDDY_HOME: path.join(home, 'none-buddy')};
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.ECA_TEST_EXE;
  app = await electron.launch(process.env.ECA_TEST_EXE
    ? {executablePath: process.env.ECA_TEST_EXE, args: [], env}
    : {args: ['.'], env});
  const page = await app.firstWindow();
  report.version = await app.evaluate(({app}) => app.getVersion());
  await app.evaluate(({BrowserWindow, dialog}, proj) => {
    BrowserWindow.getAllWindows()[0].webContents.setBackgroundThrottling(false);
    dialog.showOpenDialog = async () => ({canceled: false, filePaths: [proj]});
  }, project);
  await expect(page.getByRole('button', {name: '打开项目', exact: false}).first()).toBeVisible();
  await page.getByRole('button', {name: '打开项目', exact: false}).first().click();
  await page.waitForTimeout(1500);

  await page.getByRole('button', {name: '其他工具的历史'}).click();
  const dialog = page.getByRole('dialog', {name: '其他工具的历史会话'});
  await expect(dialog.locator('.external-row').first()).toBeVisible({timeout: 30000});
  await dialog.locator('.external-row').first().click();
  await expect(dialog.locator('.external-import')).toBeEnabled();
  await dialog.locator('.external-import').click();

  await page.waitForTimeout(1500);
  // The visible conversation must switch to the imported session, not just the
  // backend state: this is what the person actually sees.
  try {
    await expect(page.locator('.transcript')).toContainText('第一句问题', {timeout: 15000});
    report.dom_shows_import = true;
  } catch { report.dom_shows_import = false; }
  report.dialog_closed = await page.getByRole('dialog', {name: '其他工具的历史会话'}).count() === 0;
  const state = await page.evaluate(async () => {
    const snapshot = await window.eca.invoke('snapshot', {preview: false});
    return {session_id: snapshot.session_id, title: snapshot.title, sessions: snapshot.sessions,
      messages: (snapshot.messages || []).slice(0, 3).map(message => ({role: message.role, content: String(message.content || '').slice(0, 120)}))};
  });
  report.session_title = state.title || '';
  report.messages = (state.messages || []).length;
  report.note_present = (state.messages || []).some(message => /不可信|没有在本应用里发生|不是在本应用里发生的/.test(message.content));
  report.sessions_named = (state.sessions || []).some(session => String(session.title).startsWith('[导入 codex]'));
  report.imported = report.note_present && report.sessions_named;
  report.source_untouched = crypto.createHash('sha256').update(fs.readFileSync(rollout)).digest('hex') === before;

  // Continue the imported session: the next request must carry the foreign history.
  await page.getByLabel('任务指令').fill('接着刚才的话题继续');
  await page.getByRole('button', {name: '发送任务'}).click();
  for (let i = 0; i < 40 && !bodies.length; i++) await page.waitForTimeout(250);
  const payload = bodies.length ? JSON.stringify(bodies[0]) : '';
  report.continued = payload.includes('第一句问题') && payload.includes('接着刚才的话题继续');
  report.imported_history_in_context = payload.includes('第一句回答');

  const output = path.resolve('../output/playwright');
  fs.mkdirSync(output, {recursive: true});
  fs.writeFileSync(path.join(output, 'external-import.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
  if (!report.imported) throw Error('the imported session was not created as expected');
  if (!report.dom_shows_import) throw Error('the conversation area did not switch to the imported session');
  if (!report.dialog_closed) throw Error('the dialog stayed open after importing');
  if (!report.source_untouched) throw Error('the source transcript was modified');
  if (!report.continued) throw Error('the follow-up request did not carry the imported history');
})().catch(error => {console.error(error.message || error);process.exitCode = 1;}).finally(async () => {
  if (app) {await app.evaluate(({app}) => app.exit(0)).catch(() => {});await app.close().catch(() => {});}
  for (const socket of sockets) socket.destroy();
  server.close();
});
