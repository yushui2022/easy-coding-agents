// Real hidden Electron: "/" opens the skill picker, and the chosen skill must
// actually reach the model in that run. Uses a throwaway skill folder.
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
process.chdir(path.resolve(__dirname, '..'));

const base = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : require('node:os').tmpdir();
fs.mkdirSync(base, {recursive: true});
const home = fs.mkdtempSync(path.join(base, 'eca-picker-'));
const codexHome = path.join(home, 'codex');
const skillDir = path.join(codexHome, 'skills', 'picker-proof');
fs.mkdirSync(skillDir, {recursive: true});
fs.writeFileSync(path.join(skillDir, 'SKILL.md'),
  '---\nname: picker-proof\ndescription: 专门用来验证斜杠菜单的技能\n---\nPICKER-PROOF-TOKEN 这是技能正文。\n');
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
    choices: [{index: 0, delta: {content: '收到'}, finish_reason: 'stop'}]}) + '\n\n');
  res.end('data: [DONE]\n\n');
});
server.on('connection', socket => {sockets.add(socket);socket.on('close', () => sockets.delete(socket));});

const report = {version: null, menu_rows: 0, chip: '', skill_in_request: false, paid_api_calls: 0};

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const env = {...process.env, TEMP: base, TMP: base, ECA_DESKTOP_DATA_HOME: path.join(home, 'app'),
    ECA_DESKTOP_TEST_HIDDEN: '1', ECA_PYTHON: python, ECA_CODEX_HOME: codexHome,
    ECA_CLAUDE_HOME: path.join(home, 'none-claude'), ECA_WORKBUDDY_HOME: path.join(home, 'none-buddy'),
    ECA_API_KEY: 'fixture', ECA_BASE_URL: `http://127.0.0.1:${server.address().port}/v1`,
    ECA_MODEL: 'fixture', ECA_API_FORMAT: 'openai', NO_PROXY: '127.0.0.1,localhost', no_proxy: '127.0.0.1,localhost'};
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

  const composer = page.getByLabel('任务指令');
  await composer.click();
  await composer.pressSequentially('/picker', {delay: 20});

  const menu = page.getByRole('listbox', {name: '选择技能'});
  await expect(menu).toBeVisible({timeout: 15000});
  report.menu_rows = await menu.getByRole('option').count();
  // Rows must read as one panel, not a stack of bordered cards: the global
  // `.eca-app button` rule used to win here.
  report.style = await menu.getByRole('option').first().evaluate(node => {
    const style = getComputedStyle(node);
    const name = node.querySelector('.skill-name');
    return {border: style.borderTopWidth + ' ' + style.borderTopStyle, shadow: style.boxShadow,
      height: Math.round(node.getBoundingClientRect().height),
      name_wrap: name ? getComputedStyle(name).whiteSpace : null};
  });
  await composer.press('Enter');

  const chip = page.locator('.skill-chip').first();
  await expect(chip).toBeVisible();
  report.chip = (await chip.textContent() || '').replace('×', '').trim();
  await expect(composer).toHaveValue('');

  await composer.fill('用这个技能看一下');
  await composer.press('Enter');
  for (let i = 0; i < 60 && !bodies.length; i++) await page.waitForTimeout(250);
  const payload = bodies.length ? JSON.stringify(bodies[0]) : '';
  report.skill_in_request = payload.includes('PICKER-PROOF-TOKEN');
  report.prompt_in_request = payload.includes('用这个技能看一下');

  const output = path.resolve('../output/playwright');
  fs.mkdirSync(output, {recursive: true});
  fs.writeFileSync(path.join(output, 'skill-picker.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
  if (!report.menu_rows) throw Error('the skill menu showed no options');
  if (report.style && report.style.border !== '0px none') throw Error('rows still look like bordered cards: ' + report.style.border);
  if (report.style && report.style.name_wrap !== 'nowrap') throw Error('skill names can still wrap');
  if (report.style && report.style.height > 66) throw Error('rows are too tall to scan: ' + report.style.height + 'px');
  if (!report.chip) throw Error('no skill chip was created');
  if (!report.prompt_in_request) throw Error('the prompt never reached the model');
  if (!report.skill_in_request) throw Error('the selected skill was not in the request');
})().catch(error => {console.error(error.message || error);process.exitCode = 1;}).finally(async () => {
  if (app) {await app.evaluate(({app}) => app.exit(0)).catch(() => {});await app.close().catch(() => {});}
  for (const socket of sockets) socket.destroy();
  server.close();
});
