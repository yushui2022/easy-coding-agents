import fs from 'node:fs';
import path from 'node:path';
import {execFile} from 'node:child_process';

// The token is the only secret here. It is stored encrypted with the same
// safeStorage path as model keys and never leaves the main process except as a
// masked status; the renderer only learns the login name and the repo list.

type Cipher = {isEncryptionAvailable(): boolean; encryptString(value: string): Buffer; decryptString(value: Buffer): string};
type Stored = {encryptedToken?: string; login?: string};
export type Repo = {full_name: string; private: boolean; description: string; updated_at: string; default_branch: string; clone_url: string};
export type Status = {connected: boolean; login: string; encrypted: boolean; encryptionAvailable: boolean};

const API = () => process.env.ECA_GITHUB_API || 'https://api.github.com';

export class GitHub {
  private data: Stored = {};
  private tokenValue: string | undefined;

  // fetch is injected so the module never imports electron and can be tested in plain node.
  constructor(private file: string, private cipher: Cipher, private fetchImpl: typeof fetch) {
    try {
      const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (raw && typeof raw === 'object') this.data = {
        encryptedToken: typeof raw.encryptedToken === 'string' ? raw.encryptedToken : undefined,
        login: typeof raw.login === 'string' ? raw.login : undefined};
    } catch { /* a missing or unreadable file simply means "not connected" */ }
  }

  private write(next: Stored) {
    fs.mkdirSync(path.dirname(this.file), {recursive: true});
    fs.writeFileSync(this.file, JSON.stringify(next, null, 2), {mode: 0o600});
    this.data = next;
  }

  private async call(pathname: string, token: string) {
    const response = await this.fetchImpl(API() + pathname, {
      headers: {'Accept': 'application/vnd.github+json', 'Authorization': `Bearer ${token}`,
        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'ECA-Desktop'}});
    const text = await response.text();
    let body: any = null;
    try {body = text ? JSON.parse(text) : null;} catch {body = null;}
    if (!response.ok) {
      const detail = typeof body?.message === 'string' ? body.message : `HTTP ${response.status}`;
      throw new Error(response.status === 401 ? 'GitHub 拒绝了这个令牌（可能已过期或权限不足）。' : `GitHub 请求失败：${detail}`);
    }
    return body;
  }

  token(): string | undefined {
    if (this.tokenValue) return this.tokenValue;
    if (!this.data.encryptedToken) return undefined;
    try {this.tokenValue = this.cipher.decryptString(Buffer.from(this.data.encryptedToken, 'base64'));}
    catch {this.tokenValue = undefined;}
    return this.tokenValue;
  }

  status(): Status {
    return {connected: !!this.token() && !!this.data.login, login: this.data.login || '',
      encrypted: !!this.data.encryptedToken, encryptionAvailable: this.cipher.isEncryptionAvailable()};
  }

  async connect(rawToken: string): Promise<Status> {
    const token = (rawToken || '').trim();
    if (!token) throw new Error('请输入 GitHub 令牌。');
    if (token.length > 400) throw new Error('令牌格式不正确。');
    if (!this.cipher.isEncryptionAvailable()) throw new Error('系统加密不可用，出于安全考虑不会以明文保存令牌。');
    const user = await this.call('/user', token);
    if (!user || typeof user.login !== 'string') throw new Error('GitHub 没有返回账号信息。');
    this.tokenValue = token;
    this.write({encryptedToken: this.cipher.encryptString(token).toString('base64'), login: user.login});
    return this.status();
  }

  disconnect() {
    this.tokenValue = undefined;
    this.write({});
    return this.status();
  }

  async repos(): Promise<Repo[]> {
    const token = this.token();
    if (!token) throw new Error('请先连接 GitHub 账号。');
    const rows = await this.call('/user/repos?per_page=100&sort=updated&affiliation=owner,collaborator,organization_member', token);
    if (!Array.isArray(rows)) throw new Error('GitHub 返回的仓库列表无法解析。');
    return rows.filter((row: any) => row && typeof row.full_name === 'string').map((row: any) => ({
      full_name: row.full_name, private: row.private === true, description: typeof row.description === 'string' ? row.description : '',
      updated_at: typeof row.updated_at === 'string' ? row.updated_at : '', default_branch: typeof row.default_branch === 'string' ? row.default_branch : '',
      clone_url: typeof row.clone_url === 'string' ? row.clone_url : `https://github.com/${row.full_name}.git`}));
  }

  // The token never appears on the command line: git reads the header from the
  // environment. It is still visible to the same user through the process
  // environment, which is the same exposure as any credential helper.
  async clone(fullName: string, parent: string): Promise<string> {
    const token = this.token();
    if (!token) throw new Error('请先连接 GitHub 账号。');
    if (typeof fullName !== 'string' || !/^[\w.-]+\/[\w.-]+$/.test(fullName)) throw new Error('仓库名称不合法。');
    const target = path.join(parent, fullName.split('/')[1]);
    if (fs.existsSync(target) && fs.readdirSync(target).length) throw new Error(`${target} 已存在且非空，换一个位置或先移走它。`);
    const basic = Buffer.from(`x-access-token:${token}`).toString('base64');
    await new Promise<void>((resolve, reject) => {
      execFile('git', ['clone', '--depth', '1', `https://github.com/${fullName}.git`, target],
        {windowsHide: true, timeout: 300000,
          env: {...process.env, GIT_TERMINAL_PROMPT: '0', GIT_CONFIG_COUNT: '1',
            GIT_CONFIG_KEY_0: 'http.extraheader', GIT_CONFIG_VALUE_0: `Authorization: basic ${basic}`}},
        (error, _stdout, stderr) => {
          if (!error) return resolve();
          const detail = String(stderr || error.message || '').split('\n').filter(Boolean).slice(-2).join(' ').slice(0, 300);
          reject(new Error('克隆失败：' + (detail || 'git 返回了错误。')));
        });
    });
    return target;
  }
}
