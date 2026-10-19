import { spawn, execFile, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { createInterface } from 'node:readline';

export class RpcClient extends EventEmitter {
  child: ChildProcessWithoutNullStreams;
  private next = 0;
  private requests = new Map<number, {resolve: (value: any) => void; reject: (error: Error) => void; timer: NodeJS.Timeout}>();
  exited = false;
  constructor(command: string, args: string[], cwd: string) {
    super();
    this.child = spawn(command, args, {cwd, windowsHide: true, stdio: 'pipe', env: {...process.env, PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1'}});
    // Backend diagnostics are deliberately not forwarded verbatim to the renderer.
    this.child.stderr.on('data', () => this.emit('diagnostic', '后端产生诊断信息。请检查连接配置。'));
    const lines = createInterface({input: this.child.stdout});
    lines.on('line', line => {
      try {
        const message = JSON.parse(line);
        if (message.jsonrpc !== '2.0') throw new Error('protocol');
        if (message.method === 'event') this.emit('event', message.params);
        else {
          const request = this.requests.get(message.id);
          if (!request) return;
          clearTimeout(request.timer); this.requests.delete(message.id);
          if (message.error) request.reject(new Error(message.error.message));
          else request.resolve(message.result);
        }
      } catch { this.fail('后端通信格式异常，请重新打开应用。'); }
    });
    this.child.on('error', () => this.fail('无法启动随附的 ECA 运行时。'));
    this.child.on('exit', () => {this.exited = true; this.fail('后端已退出。任务不会自动重试，请重新打开项目检查进度。'); this.emit('exit');});
    this.child.stdin.on('error', () => this.fail('后端连接已关闭。'));
  }
  private fail(message: string) {
    for (const request of this.requests.values()) {clearTimeout(request.timer); request.reject(new Error(message));}
    this.requests.clear();
    this.emit('failure', message);
  }
  call(method: string, params: Record<string, unknown> = {}): Promise<any> {
    if (this.exited || this.child.stdin.destroyed) return Promise.reject(new Error('后端未连接。'));
    const id = ++this.next;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {this.requests.delete(id); reject(new Error('操作等待超时；不要重复提交任务，请先检查当前状态。'));}, 30000);
      this.requests.set(id, {resolve, reject, timer});
      this.child.stdin.write(JSON.stringify({jsonrpc: '2.0', id, method, params}) + '\n');
    });
  }
  async close(): Promise<boolean> {
    if (this.exited) return true;
    this.child.stdin.end();
    return new Promise(resolve => {
      const timer = setTimeout(() => resolve(false), 10000);
      this.child.once('exit', () => {clearTimeout(timer); resolve(true);});
    });
  }
  async forceClose() {
    if (this.exited || !this.child.pid) return;
    if (process.platform === 'win32') {
      await new Promise<void>(resolve => execFile('taskkill', ['/PID', String(this.child.pid), '/T', '/F'], {windowsHide: true}, () => resolve()));
    } else this.child.kill('SIGKILL');
  }
}
