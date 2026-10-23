// Real hidden Electron: the fifth work mode exists, is labelled, and sticks.
// No model call is made, so this costs nothing and needs no API key.
const {_electron: electron, expect} = require('@playwright/test');
const fs = require('node:fs'), path = require('node:path');
process.chdir(path.resolve(__dirname, '..'));

const base = fs.existsSync('G:/') ? 'G:/DevCache/Temp/easy-coding-agents' : require('node:os').tmpdir();
fs.mkdirSync(base, {recursive: true});
const home = fs.mkdtempSync(path.join(base, 'eca-research-'));
const project = path.join(home, 'research-project');
fs.mkdirSync(project, {recursive: true});
fs.writeFileSync(path.join(project, 'README.md'), '# fixture\n');
const python = process.env.ECA_PYTHON || path.resolve('.venv/Scripts/python.exe');

let app;
const report = {mode: process.env.ECA_TEST_EXE ? 'packaged' : 'development', paid_api_calls: 0};

(async () => {
  const env = {...process.env, TEMP: base, TMP: base, ECA_DESKTOP_DATA_HOME: path.join(home, 'app'),
    ECA_DESKTOP_TEST_HIDDEN: '1', ECA_PYTHON: python};
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
  await page.waitForTimeout(1200);

  const chip = page.locator('.mode-chip');
  await chip.click();
  const menu = page.getByRole('dialog', {name: '工作模式'});
  await expect(menu).toBeVisible();

  const rows = menu.getByRole('menuitemradio');
  report.modes = await rows.allInnerTexts();
  await expect(rows).toHaveCount(5);
  const research = menu.getByRole('menuitemradio', {name: /网络调研/});
  await expect(research).toBeVisible();
  await expect(research).toContainText('只读');

  await research.click();
  await expect(chip).toContainText('网络调研');

  // The choice has to reach the backend, not just the label.
  report.backend_mode = await page.evaluate(async () => {
    const state = await window.eca.invoke('snapshot', {preview: true});
    return state.settings && state.settings.mode;
  });
  if (report.backend_mode !== 'research') throw Error('backend mode is ' + report.backend_mode);

  // Re-open the menu: the stored choice is the checked one.
  await chip.click();
  await expect(page.getByRole('dialog', {name: '工作模式'}).getByRole('menuitemradio', {name: /网络调研/}))
    .toHaveAttribute('aria-checked', 'true');

  const output = path.resolve('../output/playwright');
  fs.mkdirSync(output, {recursive: true});
  fs.writeFileSync(path.join(output, 'research-mode.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
})().catch(error => {console.error(error.message || error);process.exitCode = 1;}).finally(async () => {
  if (app) {await app.evaluate(({app}) => app.exit(0)).catch(() => {});await app.close().catch(() => {});}
});
