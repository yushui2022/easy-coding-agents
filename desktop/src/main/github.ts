import fs from 'node:fs';
import path from 'node:path';

// The token is the only secret here. It is stored encrypted with the same
// safeStorage path as model keys and never leaves the main process except as a
// masked status; the renderer only learns the login name and the repo list.
//
// Signing in is the OAuth device flow (the flow GitHub documents for apps with no
// server of their own): the app shows an eight-character code, the browser does
// the consent, and the access token arrives over a poll. It needs an OAuth App
// client id — not a secret — which can be baked in, set through
// ECA_GITHUB_CLIENT_ID, or pasted in the settings pane. Pasting a personal access
// token and reusing a local `gh` login stay available for people who prefer them.

type Cipher = {isEncryptionAvailable(): boolean; encryptString(value: string): Buffer; decryptString(value: Buffer): string};
type Stored = {encryptedToken?: string; login?: string; clientId?: string};
export type Repo = {full_name: string; private: boolean; description: string; updated_at: string; default_branch: string; clone_url: string};
export type Status = {connected: boolean; login: string; encrypted: boolean; encryptionAvailable: boolean; oauthReady: boolean};
export type DeviceStart = {userCode: string; verificationUri: string; expiresIn: number; interval: number};
export type DevicePoll = {status: 'pending' | 'slow_down' | 'connected' | 'expired' | 'denied' | 'failed'; login?: string; interval?: number; message?: string};
type Options = {clientId?: string; ghToken?: () => Promise<string | undefined>};

const API = () => process.env.ECA_GITHUB_API || 'https://api.github.com';
// OAuth endpoints live on github.com, not on the API host, so tests override this one.
const OAUTH = () => process.env.ECA_GITHUB_OAUTH || 'https://github.com';
const CLIENT_ID = /^[A-Za-z0-9._-]{8,64}$/;

export class GitHub {
  private data: Stored = {};
  private tokenValue: string | undefined;
  private device: {code: string; expires: number} | undefined;
  private gh: boolean | undefined;

  // fetch is injected so the module never imports electron and can be tested in plain node.
  constructor(private file: string, private cipher: Cipher, private fetchImpl: typeof fetch, private options: Options = {}) {
    try {
      const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (raw && typeof raw === 'object') this.data = {
        encryptedToken: typeof raw.encryptedToken === 'string' ? raw.encryptedToken : undefined,
        login: typeof raw.login === 'string' ? raw.login : undefined,
        clientId: typeof raw.clientId === 'string' ? raw.clientId : undefined};
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

  // Device-flow endpoints answer form-encoded bodies and only speak JSON when asked.
  private async post(pathname: string, form: Record<string, string>) {
    const response = await this.fetchImpl(OAUTH() + pathname, {method: 'POST',
      headers: {'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'ECA-Desktop'},
      body: new URLSearchParams(form).toString()});
    const text = await response.text();
    let body: any = null;
    try {body = text ? JSON.parse(text) : null;} catch {body = null;}
    return {ok: response.ok, status: response.status, body};
  }

  private oauthError(body: any, status = 0): string {
    const code = typeof body?.error === 'string' ? body.error : '';
    if (code === 'device_flow_disabled') return '这个 OAuth App 没启用 Device Flow：到 GitHub → Settings → Developer settings → OAuth Apps 勾选 Enable Device Flow。';
    if (code === 'incorrect_client_credentials') return 'OAuth App 的 Client ID 不正确。';
    if (code === 'unsupported_grant_type') return 'GitHub 不接受这种授权方式，请检查 Client ID。';
    if (code === 'expired_token' || code === 'bad_verification_code') return '验证码已失效，请重新开始登录。';
    if (code === 'access_denied') return '你在 GitHub 上取消了这次授权。';
    const detail = typeof body?.error_description === 'string' ? body.error_description : '';
    if (detail) return `GitHub 登录失败：${detail}`;
    if (!code && status) return `GitHub 登录失败：HTTP ${status}。`;
    return 'GitHub 登录失败，请稍后再试。';
  }

  token(): string | undefined {
    if (this.tokenValue) return this.tokenValue;
    if (!this.data.encryptedToken) return undefined;
    try {this.tokenValue = this.cipher.decryptString(Buffer.from(this.data.encryptedToken, 'base64'));}
    catch {this.tokenValue = undefined;}
    return this.tokenValue;
  }

  clientId(): string {
    const id = this.options.clientId || this.data.clientId || process.env.ECA_GITHUB_CLIENT_ID || '';
    return String(id).trim();
  }

  oauthReady(): boolean {
    return CLIENT_ID.test(this.clientId());
  }

  // The client id is public, so it is stored as plain text next to the encrypted token.
  setClientId(raw: string): string {
    const id = String(raw ?? '').trim();
    if (id && !CLIENT_ID.test(id)) throw new Error('Client ID 格式不对，应该是一串字母数字（GitHub OAuth App 的 Client ID）。');
    const next: Stored = {...this.data};
    if (id) next.clientId = id; else delete next.clientId;
    this.write(next);
    return this.clientId();
  }

  status(): Status {
    return {connected: !!this.token() && !!this.data.login, login: this.data.login || '',
      encrypted: !!this.data.encryptedToken, encryptionAvailable: this.cipher.isEncryptionAvailable(), oauthReady: this.oauthReady()};
  }

  async connect(rawToken: string): Promise<Status> {
    const token = (rawToken || '').trim();
    if (!token) throw new Error('请输入 GitHub 令牌。');
    if (token.length > 400) throw new Error('令牌格式不正确。');
    if (!this.cipher.isEncryptionAvailable()) throw new Error('系统加密不可用，出于安全考虑不会以明文保存令牌。');
    const user = await this.call('/user', token);
    if (!user || typeof user.login !== 'string') throw new Error('GitHub 没有返回账号信息。');
    this.tokenValue = token;
    this.write({...this.data, encryptedToken: this.cipher.encryptString(token).toString('base64'), login: user.login});
    return this.status();
  }

  disconnect() {
    this.tokenValue = undefined;
    this.device = undefined;
    const next: Stored = {...this.data};
    delete next.encryptedToken;
    delete next.login;
    this.write(next);
    return this.status();
  }

  // Step one of the device flow: show the user a short code and send them to the
  // verification page. Nothing here is secret — the device code stays in memory.
  async startDevice(): Promise<DeviceStart> {
    const clientId = this.clientId();
    if (!this.oauthReady()) throw new Error('还没有配置 OAuth App 的 Client ID，暂时只能粘贴访问令牌。');
    const {ok, status, body} = await this.post('/login/device/code', {client_id: clientId, scope: 'repo'});
    if (!ok || typeof body?.device_code !== 'string' || typeof body?.user_code !== 'string') {
      throw new Error(this.oauthError(body, ok ? 0 : status));
    }
    const expiresIn = Number(body.expires_in) > 0 ? Number(body.expires_in) : 900;
    this.device = {code: body.device_code, expires: Date.now() + expiresIn * 1000};
    return {userCode: body.user_code, verificationUri: typeof body.verification_uri === 'string' ? body.verification_uri : 'https://github.com/login/device',
      expiresIn, interval: Number(body.interval) > 0 ? Number(body.interval) : 5};
  }

  // Step two: the renderer polls this on the interval GitHub returned. Only the
  // token exchange can turn a pending login into a connected account.
  async pollDevice(): Promise<DevicePoll> {
    const device = this.device;
    if (!device) return {status: 'failed', message: '没有进行中的登录，请重新开始。'};
    if (Date.now() > device.expires) {this.device = undefined; return {status: 'expired', message: '验证码已过期，请重新开始。'};}
    const clientId = this.clientId();
    if (!this.oauthReady()) {this.device = undefined; return {status: 'failed', message: '还没有配置 OAuth App 的 Client ID。'};}
    const {ok, status, body} = await this.post('/login/oauth/access_token',
      {client_id: clientId, device_code: device.code, grant_type: 'urn:ietf:params:oauth:grant-type:device_code'});
    if (typeof body?.access_token === 'string' && body.access_token) {
      this.device = undefined;
      const next = await this.connect(body.access_token);
      return {status: 'connected', login: next.login};
    }
    const code = typeof body?.error === 'string' ? body.error : '';
    if (code === 'authorization_pending') return {status: 'pending'};
    if (code === 'slow_down') return {status: 'slow_down', interval: Number(body?.interval) > 0 ? Number(body.interval) : 10};
    this.device = undefined;
    if (code === 'expired_token' || code === 'bad_verification_code') return {status: 'expired', message: this.oauthError(body)};
    if (code === 'access_denied') return {status: 'denied', message: this.oauthError(body)};
    return {status: 'failed', message: this.oauthError(body, ok ? 0 : status)};
  }

  cancelDevice() {
    this.device = undefined;
  }

  // A local `gh auth login` already holds a token; reusing it is one click instead
  // of a browser round trip. It is optional and never required.
  private async ghToken(): Promise<string | undefined> {
    if (!this.options.ghToken) return undefined;
    try {const token = await this.options.ghToken(); return token ? token.trim() || undefined : undefined;}
    catch {return undefined;}
  }

  async ghAvailable(): Promise<boolean> {
    if (this.gh === undefined) this.gh = !!(await this.ghToken());
    return this.gh;
  }

  async connectGh(): Promise<Status> {
    const token = await this.ghToken();
    if (!token) throw new Error('没有找到本机 gh 的登录令牌，先在终端运行 gh auth login。');
    const next = await this.connect(token);
    this.gh = true;
    return next;
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
    const {execFile} = await import('node:child_process');
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
