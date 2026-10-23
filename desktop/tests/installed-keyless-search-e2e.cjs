// Network-dependent: the installed app must perform a real keyless search.
// A local fixture fakes the *model*; the web request itself is real.
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
process.chdir(path.resolve(__dirname, '..'));

const base = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : require('node:os').tmpdir();
fs.mkdirSync(base, {recursive: true});
const home = fs.mkdtempSync(path.join(base, 'eca-keyless-'));
const project = path.join(home, 'keyless-project');
fs.mkdirSync(project, {recursive: true});
fs.writeFileSync(path.join(project, 'README.md'), '# fixture\n');
const python = process.env.ECA_PYTHON || path.resolve('.venv/Scripts/python.exe');

let app;
const sockets = new Set();
let sawToolResult = false;
const server = http.createServer(async (req, res) => {
  let raw = ''; for await (const chunk of req) raw += chunk;
  let body = {}; try { body = JSON.parse(raw); } catch { body = {}; }
  if (!body.stream) {
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({id: 'f', object: 'chat.completion', created: 0, model: 'fixture',
      choices: [{index: 0, message: {role: 'assistant', content: 'ok'}, finish_reason: 'stop'}],
      usage: {prompt_tokens: 5, completion_tokens: 1, total_tokens: 6}}));
    return;
  }
  const hasToolResult = (body.messages || []).some(message => message.role === 'tool');
  if (hasToolResult) sawToolResult = true;
  const delta = hasToolResult ? {content: 'done'} : {
    tool_calls: [{index: 0, id: 'call-search', type: 'function',
      function: {name: 'web_search', arguments: JSON.stringify({query: 'duckduckgo html endpoint', count: 2})}}]};
  res.writeHead(200, {'Content-Type': 'text/event-stream'});
  res.write('data: ' + JSON.stringify({id: 'f', object: 'chat.completion.chunk', created: 0, model: 'fixture',
    choices: [{index: 0, delta, finish_reason: hasToolResult ? 'stop' : 'tool_calls'}]}) + '\n\n');
  res.end('data: [DONE]\n\n');
});
server.on('connection', socket => {sockets.add(socket);socket.on('close', () => sockets.delete(socket));});

const report = {version: null, keyless_search_ran: false, urls_found: 0, paid_api_calls: 0};

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const env = {...process.env, TEMP: base, TMP: base, ECA_DESKTOP_DATA_HOME: path.join(home, 'app'),
    ECA_DESKTOP_TEST_HIDDEN: '1', ECA_PYTHON: python,
    ECA_API_KEY: 'fixture', ECA_BASE_URL: `http://127.0.0.1:${server.address().port}/v1`,
    ECA_MODEL: 'fixture', ECA_API_FORMAT: 'openai', NO_PROXY: '127.0.0.1,localhost', no_proxy: '127.0.0.1,localhost'};
  delete env.ELECTRON_RUN_AS_NODE;
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
  await page.waitForTimeout(1200);

  await page.locator('.mode-chip').click();
  await page.getByRole('dialog', {name: '工作模式'}).getByRole('menuitemradio', {name: /网络调研/}).click();
  await expect(page.locator('.mode-chip')).toContainText('网络调研');

  await page.getByLabel('任务指令').fill('搜一下 duckduckgo html endpoint 相关资料');
  await page.getByRole('button', {name: '发送任务'}).click();

  let toolText = '';
  let diagnostics = {};
  for (let i = 0; i < 90; i++) {
    await page.waitForTimeout(1000);
    const state = await page.evaluate(async () => {
      try { return await window.eca.invoke('snapshot', {preview: false}); } catch (error) { return {error: String(error)}; }
    });
    const tools = (state.messages || []).filter(message => message.role === 'tool');
    const tool = tools.pop();
    if (tool && typeof tool.content === 'string') toolText = tool.content;
    diagnostics = {status: state.status, busy: state.busy, messages: (state.messages || []).length,
      tool_messages: tools.length, pending: (state.pending || []).length,
      last_role: ((state.messages || []).pop() || {}).role,
      tool_head: toolText.slice(0, 300)};
    if (toolText && /"provider"/.test(toolText)) break;
    if (sawToolResult && i > 30) break;
  }

  report.keyless_search_ran = /"provider":\s*"duckduckgo"/.test(toolText);
  report.search_failed_with = report.keyless_search_ran ? null
    : (/rate limited|no results|Search failed|credential/i.test(toolText) ? toolText.slice(0, 200) : null);
  report.urls_found = (toolText.match(/https:\/\/[^\s"\\]+/g) || []).length;
  report.diagnostics = diagnostics;

  const output = path.resolve('../output/playwright');
  fs.mkdirSync(output, {recursive: true});
  fs.writeFileSync(path.join(output, 'installed-keyless-search.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
  if (!report.keyless_search_ran) throw Error('the installed build did not complete a keyless search');
  if (!report.urls_found) throw Error('the search returned no URLs');
})().catch(error => {console.error(error.message || error);process.exitCode = 1;}).finally(async () => {
  if (app) {await app.evaluate(({app}) => app.exit(0)).catch(() => {});await app.close().catch(() => {});}
  for (const socket of sockets) socket.destroy();
  server.close();
});
