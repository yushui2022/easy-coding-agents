// macOS smoke test: real Electron window, real Python backend, local HTTP model
// fixture. No renderer mocks and no paid API calls. It answers one question the
// Windows e2e suite cannot: does the packaged/started app work on darwin?
//
//   ECA_PYTHON=../.venv/bin/python node tests/mac-smoke.cjs
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');

process.chdir(path.resolve(__dirname, '..'));
const temp = fs.mkdtempSync(path.join(process.env.TMP || os.tmpdir(), 'eca-mac-smoke-'));
const project = path.join(temp, 'mac 项目');
fs.mkdirSync(project);
const requests = [];

const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/v1/models') {
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({data: [{id: 'fixture'}, {id: 'fixture-secondary'}]}));
    return;
  }
  let raw = '';
  for await (const chunk of req) raw += chunk;
  const body = JSON.parse(raw || '{}');
  requests.push(body);
  if (!body.stream) {
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({choices: [{message: {role: 'assistant', content: 'OK'}}]}));
    return;
  }
  const hasResult = body.messages.some(message => message.role === 'tool');
  const delta = hasResult
    ? {content: '已完成修改，等待检查。'}
    : {tool_calls: [{index: 0, id: 'fixture-write-' + requests.length, type: 'function',
        function: {name: 'write', arguments: JSON.stringify({path: 'hello.txt', content: 'hello'})}}]};
  res.writeHead(200, {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache'});
  for (const [piece, reason] of [[delta, null], [{}, delta.tool_calls ? 'tool_calls' : 'stop']]) {
    res.write('data: ' + JSON.stringify({id: 'fixture', object: 'chat.completion.chunk', created: 0, model: 'fixture',
      choices: [{index: 0, delta: piece, finish_reason: reason}]}) + '\n\n');
  }
  res.end('data: [DONE]\n\n');
});

(async () => {
  // With SMOKE_BASE_URL the test drives a real OpenAI-compatible server (for
  // example the local MLX one) instead of the fixture, so tool calling and
  // streaming can be checked against the model the user actually runs.
  const real = process.env.SMOKE_BASE_URL;
  if (!real) await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = real || 'http://127.0.0.1:' + server.address().port + '/v1';
  const modelId = process.env.SMOKE_MODEL || 'fixture';
  const credential = real ? (process.env.SMOKE_API_KEY || 'local') : 'mac-smoke-credential';
  const env = {...process.env, ECA_DESKTOP_DATA_HOME: path.join(temp, 'app-data'),
    ECA_DESKTOP_TEST_HIDDEN: '1', NO_PROXY: '127.0.0.1,localhost', no_proxy: '127.0.0.1,localhost'};
  const application = await electron.launch(process.env.ECA_TEST_EXE
    ? {executablePath: process.env.ECA_TEST_EXE, args: [], env}
    : {args: ['.'], env});
  const errors = [];
  const page = await application.firstWindow();
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  application.process().stderr.on('data', data => console.log('Electron:', String(data).trim().slice(0, 600)));

  await expect(page.getByRole('button', {name: '模型与设置'})).toBeVisible({timeout: 60000});
  console.log('window: ok');

  await page.getByRole('button', {name: '模型与设置'}).click();
  await page.getByLabel('API 地址').fill(base);
  if (process.env.SMOKE_NO_AUTH === '1') {
    // Local servers need no key. This path also skips macOS keychain storage,
    // which blocks on a system prompt for an ad-hoc signed build.
    await page.getByLabel('本机服务无需密钥').check();
  } else {
    await page.getByLabel('API 密钥').fill(credential);
  }
  await expect(page.getByLabel('服务返回的模型')).toBeEnabled({timeout: 20000});
  await page.getByLabel('服务返回的模型').selectOption(modelId);
  await page.getByRole('button', {name: '保存配置', exact: true}).click();
  await expect(page.getByRole('status')).toContainText('配置已保存', {timeout: 15000});
  await page.getByRole('button', {name: '关闭设置'}).click();
  console.log('model connection: ok');

  await application.evaluate(({dialog}, folder) => {
    dialog.showOpenDialog = async () => ({canceled: false, filePaths: [folder]});
  }, project);
  await page.getByRole('button', {name: '打开项目', exact: true}).click();
  await expect(page.locator('.workspace-title')).toContainText('mac 项目', {timeout: 60000});
  console.log('project open: ok');

  await page.getByLabel('任务指令').fill('创建 hello.txt，内容为 hello。不要做别的事。');
  await page.getByRole('button', {name: '发送任务'}).click();
  await expect(page.getByRole('button', {name: '本次允许'})).toBeVisible({timeout: 90000});
  await page.getByRole('button', {name: '本次允许'}).click();
  await expect(page.locator('.tool-record').first()).toBeVisible({timeout: 90000});
  // Models are free to add a trailing newline; the task was the content, not the bytes.
  await expect.poll(() => fs.existsSync(path.join(project, 'hello.txt'))
    ? fs.readFileSync(path.join(project, 'hello.txt'), 'utf8').trim() : null, {timeout: 60000}).toBe('hello');
  console.log('file write through backend: ok');
  console.log('model requests:', requests.length);
  console.log('renderer errors:', errors.length ? errors : 'none');
  console.log('SMOKE PASSED');
  await application.close();
  server.close();
  process.exit(0);
})().catch(async error => {
  console.error('SMOKE FAILED:', error.message);
  server.close();
  process.exit(1);
});
