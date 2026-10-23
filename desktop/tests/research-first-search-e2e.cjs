// Real installed/packaged app: prove the research-mode instruction actually
// reaches the model. Captures the outgoing request body with a local fixture.
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
process.chdir(path.resolve(__dirname, '..'));

const base = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : require('node:os').tmpdir();
fs.mkdirSync(base, {recursive: true});
const home = fs.mkdtempSync(path.join(base, 'eca-first-search-'));
const project = path.join(home, 'first-search');
fs.mkdirSync(project, {recursive: true});
fs.writeFileSync(path.join(project, 'README.md'), '# fixture\n');
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
    choices: [{index: 0, delta: {content: 'ok'}, finish_reason: 'stop'}]}) + '\n\n');
  res.end('data: [DONE]\n\n');
});
server.on('connection', socket => {sockets.add(socket);socket.on('close', () => sockets.delete(socket));});

const report = {mode: process.env.ECA_TEST_EXE ? 'installed-or-packaged' : 'development', paid_api_calls: 0};

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

  // Switch to research mode, then ask about something the model cannot know.
  await page.locator('.mode-chip').click();
  await page.getByRole('dialog', {name: '工作模式'}).getByRole('menuitemradio', {name: /网络调研/}).click();
  await expect(page.locator('.mode-chip')).toContainText('网络调研');

  await page.getByLabel('任务指令').fill('zeptoflux 这个库现在还维护吗');
  await page.getByRole('button', {name: '发送任务'}).click();

  for (let i = 0; i < 40 && !bodies.length; i++) await page.waitForTimeout(250);
  if (!bodies.length) throw Error('the model request never arrived');

  const payload = JSON.stringify(bodies[0]);
  report.system_prompt_has_orientation = payload.includes('start with one web search that answers what the thing is');
  report.runtime_guidance_has_orientation = payload.includes('make your first action one web search');
  report.model_received_question = payload.includes('zeptoflux');

  if (!report.model_received_question) throw Error('the question never reached the model');
  if (!report.system_prompt_has_orientation) throw Error('system prompt lacks the orientation step');
  if (!report.runtime_guidance_has_orientation) throw Error('runtime guidance lacks the orientation step');

  const output = path.resolve('../output/playwright');
  fs.mkdirSync(output, {recursive: true});
  fs.writeFileSync(path.join(output, 'research-first-search.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
})().catch(error => {console.error(error.message || error);process.exitCode = 1;}).finally(async () => {
  if (app) {await app.evaluate(({app}) => app.exit(0)).catch(() => {});await app.close().catch(() => {});}
  for (const socket of sockets) socket.destroy();
  server.close();
});
