// Real hidden Electron against this machine's real Codex/Claude/WorkBuddy files.
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs'), path = require('node:path');
process.chdir(path.resolve(__dirname, '..'));

const base = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : require('node:os').tmpdir();
fs.mkdirSync(base, {recursive: true});
const home = fs.mkdtempSync(path.join(base, 'eca-external-'));

let app;
const report = {version: null, rows: 0, sources: [], opened: null, messages: 0, paid_api_calls: 0};

(async () => {
  const env = {...process.env, TEMP: base, TMP: base, ECA_DESKTOP_DATA_HOME: path.join(home, 'app'),
    ECA_DESKTOP_TEST_HIDDEN: '1'};
  delete env.ELECTRON_RUN_AS_NODE;
  app = await electron.launch(process.env.ECA_TEST_EXE
    ? {executablePath: process.env.ECA_TEST_EXE, args: [], env}
    : {args: ['.'], env});
  const page = await app.firstWindow();
  report.version = await app.evaluate(({app}) => app.getVersion());
  await expect(page.getByRole('button', {name: '其他工具的历史'})).toBeVisible();
  await page.getByRole('button', {name: '其他工具的历史'}).click();

  const dialog = page.getByRole('dialog', {name: '其他工具的历史会话'});
  await expect(dialog).toBeVisible();
  const probe = await page.evaluate(async () => {
    try {
      const result = await window.eca.invoke('external.sessions', {limit: 5});
      return {ok: true, count: (result?.sessions || []).length};
    } catch (error) { return {ok: false, error: String(error)}; }
  });
  console.log('PROBE ' + JSON.stringify(probe));
  if (!probe.ok) throw Error('external.sessions failed: ' + probe.error);
  await expect(dialog.locator('.external-row').first()).toBeVisible({timeout: 30000});

  const rows = dialog.locator('.external-row');
  report.rows = await rows.count();
  report.sources = await dialog.locator('.external-badge').evaluateAll(nodes =>
    [...new Set(nodes.map(node => node.textContent))]);

  await rows.first().click();
  await expect(dialog.locator('.external-message').first()).toBeVisible({timeout: 20000});
  report.opened = (await dialog.locator('.external-view-title').textContent() || '').slice(0, 60);
  report.messages = await dialog.locator('.external-message').count();

  const output = path.resolve('../output/playwright');
  fs.mkdirSync(output, {recursive: true});
  fs.writeFileSync(path.join(output, 'external-history.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
  if (!report.rows) throw Error('no external sessions were listed');
  if (!report.messages) throw Error('the opened session showed no messages');
})().catch(error => {console.error(error.message || error);process.exitCode = 1;}).finally(async () => {
  if (app) {await app.evaluate(({app}) => app.exit(0)).catch(() => {});await app.close().catch(() => {});}
});
