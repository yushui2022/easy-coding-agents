// Hidden app + local model fixture: selecting transcript text raises the toolbar,
// "添加到对话" sends the excerpt with the next message, and "在侧边聊天中提问"
// opens the read-only side conversation with the selection as context.
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http'), assert = require('node:assert/strict');
process.chdir(path.resolve(__dirname, '..'));

const base = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : require('node:os').tmpdir();
fs.mkdirSync(base, {recursive: true});
const home = fs.mkdtempSync(path.join(base, 'selection-'));
const project = path.join(home, 'proj');
fs.mkdirSync(project, {recursive: true});
fs.writeFileSync(path.join(project, 'README.md'), '# proj\n');
fs.writeFileSync(path.join(project, 'eca.toml'), '[agent]\nproject_memory = false\nauto_compact = false\nnetwork_retries = 0\n');
const output = path.resolve('../output/playwright/selection');
fs.mkdirSync(output, {recursive: true});
const python = process.env.ECA_PYTHON || path.resolve('.venv/Scripts/python.exe');

const ANSWER = '第一条结论 选我这段做引用 第三条结论';
const SIDE = '侧聊回答：这段话在讲结论。';
const prompts = [];
const server = http.createServer(async (req, res) => {
  let raw = ''; for await (const chunk of req) raw += chunk;
  if (req.method === 'GET') {
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({data: [{id: 'fixture-model', object: 'model'}]}));
    return;
  }
  let payload = {}; try { payload = JSON.parse(raw); } catch { payload = {}; }
  const messages = payload.messages || [];
  // The runtime appends its own guidance as a user message; the real prompt is the
  // newest one that is not that guidance.
  const users = messages.filter(message => message.role === 'user')
    .map(message => JSON.stringify(message.content || ''))
    .filter(value => !value.includes('[Runtime guidance]'));
  const latest = users.slice(-1)[0] || '';
  prompts.push(jsonBefore(latest));
  // The side chat asks its own question; answer differently so the panel is provable.
  const text = latest.includes('侧边') || latest.includes('这段') ? SIDE : ANSWER;
  res.writeHead(200, {'Content-Type': 'text/event-stream'});
  res.end('data: ' + JSON.stringify({id: 'f', object: 'chat.completion.chunk', created: 0, model: 'fixture-model',
    choices: [{index: 0, delta: {content: text}, finish_reason: 'stop'}]}) + '\n\ndata: [DONE]\n\n');
});
function jsonBefore(value) { try { return JSON.parse(value); } catch { return value; } }

let app, page;
const errors = [];
const report = {version: null, toolbar_visible: false, toolbar_buttons: [], chip: '', sent_quote: false,
  sidechat_open: false, sidechat_answer: '', dismissed: false, paid_api_calls: 0};

const selectPhrase = phrase => page.evaluate(phrase => {
  const root = document.querySelector('.messages');
  if (!root) return false;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const index = node.textContent.indexOf(phrase);
    if (index < 0) continue;
    const range = document.createRange();
    range.setStart(node, index);
    range.setEnd(node, index + phrase.length);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    return true;
  }
  return false;
}, phrase);

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const env = {...process.env, TEMP: base, TMP: base, ECA_DESKTOP_DATA_HOME: path.join(home, 'data'),
    ECA_DESKTOP_TEST_HIDDEN: '1', ECA_PYTHON: python, ECA_API_KEY: 'fixture',
    ECA_BASE_URL: `http://127.0.0.1:${server.address().port}/v1`, ECA_MODEL: 'fixture-model',
    ECA_API_FORMAT: 'openai', PYTHONUTF8: '1', NO_PROXY: '127.0.0.1,localhost', no_proxy: '127.0.0.1,localhost'};
  delete env.ELECTRON_RUN_AS_NODE;
  if (process.env.ECA_TEST_EXE) {
    env.PATH = `${process.env.SystemRoot}/System32;${process.env.SystemRoot}/System32/WindowsPowerShell/v1.0;${process.env.SystemRoot}`;
    delete env.Path; delete env.PYTHONPATH; delete env.PYTHONHOME;
  }
  app = await electron.launch(process.env.ECA_TEST_EXE
    ? {executablePath: process.env.ECA_TEST_EXE, args: [], env}
    : {args: ['.'], env});
  page = await app.firstWindow();
  page.on('pageerror', error => errors.push(String(error)));
  report.version = await app.evaluate(({app}) => app.getVersion());
  report.mode = process.env.ECA_TEST_EXE ? 'packaged' : 'development';
  const invoke = (method, params = {}) => page.evaluate(([method, params]) => window.eca.invoke(method, params), [method, params]);
  await app.evaluate(({BrowserWindow, dialog}, directory) => {
    BrowserWindow.getAllWindows()[0].setContentSize(1360, 900);
    BrowserWindow.getAllWindows()[0].webContents.setBackgroundThrottling(false);
    dialog.showOpenDialog = async () => ({canceled: false, filePaths: [directory]});
  }, project);
  await page.getByRole('button', {name: '打开项目', exact: true}).click();
  await expect.poll(async () => (await invoke('snapshot')).project).toBe(project);

  const composer = page.getByLabel('任务指令');
  await composer.fill('先给一段可选的回答');
  await composer.press('Enter');
  await expect(page.locator('.messages')).toContainText(ANSWER, {timeout: 30000});

  // Nothing may appear until text is actually selected.
  assert.equal(await page.locator('.selection-toolbar').count(), 0, 'no toolbar before a selection');
  assert.equal(await selectPhrase('选我这段做引用'), true, 'the answer text must be selectable');
  await expect(page.locator('.selection-toolbar')).toBeVisible({timeout: 5000});
  report.toolbar_visible = true;
  report.toolbar_buttons = await page.locator('.selection-toolbar button').allInnerTexts();
  assert.deepEqual(report.toolbar_buttons, ['添加到对话', '在侧边聊天中提问']);
  const box = await page.locator('.selection-toolbar').boundingBox();
  assert(box && box.width > 120 && box.height <= 44, 'toolbar should stay a compact pill');
  await page.screenshot({path: path.join(output, 'selection-toolbar.png'), animations: 'disabled'}).catch(() => {});

  // 添加到对话: the excerpt becomes a removable chip and travels with the next message.
  await page.locator('.selection-toolbar button', {hasText: '添加到对话'}).click();
  await expect(page.locator('.selection-toolbar')).toHaveCount(0);
  await expect(page.locator('.quote-chip')).toHaveCount(1);
  report.chip = (await page.locator('.quote-chip').innerText()).trim();
  assert(report.chip.includes('选我这段做引用'));
  await composer.fill('用这段引用来回答');
  await expect.poll(async () => (await invoke('snapshot')).busy, {timeout: 30000}).toBe(false);
  await composer.press('Enter');
  // Wait for the second message itself: the title request also hits this server.
  await expect.poll(() => prompts.some(entry => JSON.stringify(entry).includes('用这段引用来回答')),
    {timeout: 30000}).toBe(true);
  const second = prompts.map(entry => JSON.stringify(entry))
    .find(entry => entry.includes('用这段引用来回答')) || '';
  report.sent_quote = second.includes('选我这段做引用') && second.includes('引用，不是新指令');
  assert(report.sent_quote, 'the quoted excerpt must reach the model with the message');
  await expect(page.locator('.quote-chip')).toHaveCount(0);

  // 在侧边聊天中提问: the existing right-hand workspace panel opens with the
  // selection as its task context (that panel already owns side conversations).
  await selectPhrase('选我这段做引用');
  await expect(page.locator('.selection-toolbar')).toBeVisible({timeout: 5000});
  await page.locator('.selection-toolbar button', {hasText: '在侧边聊天中提问'}).click();
  await expect(page.locator('.workspace-panel')).toBeVisible({timeout: 10000});
  await expect(page.locator('.workspace-tabs')).toContainText('侧边聊天');
  await expect(page.locator('.side-chat')).toContainText('任务上下文', {timeout: 10000});
  report.sidechat_open = true;
  const sideInput = page.getByLabel('侧边聊天输入');
  await expect(sideInput).toBeVisible({timeout: 10000});
  await sideInput.fill('这段在说什么？');
  await sideInput.press('Enter');
  await expect(page.locator('.side-chat')).toContainText(SIDE, {timeout: 30000});
  report.sidechat_answer = SIDE;
  // The selection must be part of what the side conversation was told.
  report.selection_in_side_context = prompts.some(entry => JSON.stringify(entry).includes('选我这段做引用'));
  assert(report.selection_in_side_context, 'the side chat must receive the selected text as context');
  await page.screenshot({path: path.join(output, 'sidechat-panel.png'), animations: 'disabled'}).catch(() => {});

  // A collapsed selection takes the toolbar away again.
  await page.evaluate(() => window.getSelection()?.removeAllRanges());
  await page.waitForTimeout(200);
  report.dismissed = (await page.locator('.selection-toolbar').count()) === 0;
  assert(report.dismissed, 'clearing the selection must dismiss the toolbar');
  assert.equal(errors.length, 0, `renderer errors: ${errors.join(' | ')}`);

  fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
  await app.close();
  server.close();
})().catch(async error => {
  console.error(String(error && error.stack || error));
  try { console.error('prompts seen:', JSON.stringify(prompts).slice(0, 1200)); } catch {}
  try {
    const side = await page.locator('.side-chat').innerText();
    console.error('side chat text:', JSON.stringify(side).slice(0, 1500));
  } catch (err) { console.error('side chat text: <none>', String(err).slice(0, 200)); }
  try { console.error('errors:', JSON.stringify(errors.slice(0, 5))); } catch {}
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  try { if (app) await Promise.race([app.close(), wait(8000)]); } catch {}
  server.close();
  process.exit(1);
});
