// Real hidden Electron: the skills pane lists <name>/SKILL.md from every tool.
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs'), path = require('node:path');
process.chdir(path.resolve(__dirname, '..'));

const base = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : require('node:os').tmpdir();
fs.mkdirSync(base, {recursive: true});
const home = fs.mkdtempSync(path.join(base, 'eca-skills-'));

let app;
const report = {version: null, rows: 0, sources: [], opened: '', body_chars: 0, paid_api_calls: 0};

(async () => {
  const env = {...process.env, TEMP: base, TMP: base, ECA_DESKTOP_DATA_HOME: path.join(home, 'app'),
    ECA_DESKTOP_TEST_HIDDEN: '1'};
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.ECA_TEST_EXE;
  app = await electron.launch(process.env.ECA_TEST_EXE
    ? {executablePath: process.env.ECA_TEST_EXE, args: [], env}
    : {args: ['.'], env});
  const page = await app.firstWindow();
  report.version = await app.evaluate(({app}) => app.getVersion());

  await page.getByRole('button', {name: '技能', exact: true}).click();
  const dialog = page.getByRole('dialog', {name: '技能'});
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('.external-row').first()).toBeVisible({timeout: 20000});

  report.rows = await dialog.locator('.external-row').count();
  report.sources = await dialog.locator('.external-badge').evaluateAll(nodes =>
    [...new Set(nodes.map(node => node.textContent))]);

  await dialog.locator('.external-row').first().click();
  await expect(dialog.locator('.skill-body')).toBeVisible({timeout: 10000});
  report.opened = (await dialog.locator('.external-view-title').textContent() || '').slice(0, 60);
  report.body_chars = (await dialog.locator('.skill-body').textContent() || '').length;

  const output = path.resolve('../output/playwright');
  fs.mkdirSync(output, {recursive: true});
  fs.writeFileSync(path.join(output, 'skills-pane.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
  if (!report.rows) throw Error('no skills were listed');
  if (!report.body_chars) throw Error('the skill body did not render');
})().catch(error => {console.error(error.message || error);process.exitCode = 1;}).finally(async () => {
  if (app) {await app.evaluate(({app}) => app.exit(0)).catch(() => {});await app.close().catch(() => {});}
});
