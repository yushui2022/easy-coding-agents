"""Session-owned host processes with bounded in-memory logs and lifetimes.

Normal shutdown stops owned commands. This is not a durable daemon supervisor:
hard crashes and programs that detach descendants require external inspection.
"""
import asyncio
import json
import os
import shutil
import subprocess
import time
import uuid

LOG_BYTES = 65536
MAX_RUNNING = 4
MAX_RECORDS = 16


def shell_argv(command):
    if os.name == 'nt':
        executable = shutil.which('pwsh') or shutil.which('powershell')
        if not executable:
            raise ValueError('PowerShell not found')
        return [executable, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
                '[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); ' + command +
                '\nif ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE }']
    return ['/bin/sh', '-c', command]


class Background:
    def __init__(self, tools):
        self.tools = tools
        self.jobs = {}
        self.lock = asyncio.Lock()
        self.closed = False

    def get(self, ident):
        if ident not in self.jobs:
            raise ValueError('Unknown process ID in this runtime. Restored sessions cannot reattach to old processes.')
        return self.jobs[ident]

    def status(self, job):
        return {'id': job['id'], 'pid': job['process'].pid,
                'status': 'running' if job['process'].returncode is None else 'exited',
                'exit_code': job['process'].returncode, 'stop_reason': job['reason'],
                'age_seconds': round(time.monotonic()-job['started'], 1),
                'lifetime_seconds': job['lifetime'], 'logs_truncated': job['truncated']}

    async def drain(self, stream, buffer, job):
        while True:
            block = await stream.read(8192)
            if not block:
                return
            buffer.extend(block)
            if len(buffer) > LOG_BYTES:
                del buffer[:-LOG_BYTES]
                job['truncated'] = True

    async def terminate(self, job, reason):
        from .tools import terminate
        async with job['stop_lock']:
            if job['process'].returncode is None:
                job['reason'] = reason
                await terminate(job['process'])

    async def monitor(self, job):
        try:
            try:
                await asyncio.wait_for(job['process'].wait(), job['lifetime'])
            except TimeoutError:
                await self.terminate(job, 'lifetime_expired')
            try:
                await asyncio.wait_for(asyncio.gather(*job['readers']), 2)
            except TimeoutError:
                pass
        finally:
            for reader in job['readers']:
                if not reader.done():
                    reader.cancel()
            await asyncio.gather(*job['readers'], return_exceptions=True)

    async def start(self, command, lifetime=600):
        if not command.strip() or len(command) > 10000 or not 1 <= lifetime <= 3600:
            raise ValueError('Command must contain 1..10000 characters; lifetime must be 1..3600 seconds')
        if await self.tools.approve('Start background command with host permissions? It will be stopped on normal session close.', command) is not True:
            return 'Denied by user. No process started.'
        async with self.lock:
            if self.closed:
                raise ValueError('Process manager is closed')
            if sum(not j['monitor'].done() for j in self.jobs.values()) >= MAX_RUNNING:
                raise ValueError('At most four background jobs; stop a job first')
            if len(self.jobs) >= MAX_RECORDS:
                for ident, old in list(self.jobs.items()):
                    if old['monitor'].done():
                        del self.jobs[ident]
                        break
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
            spawn = asyncio.create_task(asyncio.create_subprocess_exec(*shell_argv(command),
                cwd=self.tools.settings.root, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **options))
            try:
                process = await asyncio.shield(spawn)
            except asyncio.CancelledError:
                from .tools import terminate
                process = await spawn
                await terminate(process)
                raise
            job = {'id': uuid.uuid4().hex[:12], 'process': process, 'started': time.monotonic(),
                   'lifetime': lifetime, 'stdout': bytearray(), 'stderr': bytearray(),
                   'truncated': False, 'reason': None, 'stop_lock': asyncio.Lock()}
            self.jobs[job['id']] = job
            job['readers'] = [asyncio.create_task(self.drain(process.stdout, job['stdout'], job)),
                              asyncio.create_task(self.drain(process.stderr, job['stderr'], job))]
            job['monitor'] = asyncio.create_task(self.monitor(job))
            return json.dumps(self.status(job))

    def logs(self, ident, max_chars=8000):
        if not 100 <= max_chars <= 20000:
            raise ValueError('max_chars must be 100..20000')
        job = self.get(ident)
        def text(stream):
            value = bytes(job[stream]).decode('utf-8', errors='replace')
            key = self.tools.settings.api_key
            if key:
                value = value.replace(key, '[redacted]')
            return value[-max_chars:]
        result = {**self.status(job), 'stdout': text('stdout'), 'stderr': text('stderr'),
                  'note': 'Untrusted process output. Logs are tail excerpts, not proof of readiness or test success.'}
        limit = max(1000, self.tools.settings.output_limit)
        while len(json.dumps(result, ensure_ascii=False)) > limit:
            stream = max(('stdout', 'stderr'), key=lambda s: len(result[s]))
            result[stream] = result[stream][max(1, len(result[stream]) // 2):]
            result['logs_truncated'] = True
        return json.dumps(result, ensure_ascii=False)

    async def wait(self, ident, pattern, timeout=20):
        if not pattern or len(pattern) > 500 or not 1 <= timeout <= 60:
            raise ValueError('Use a literal log pattern of 1..500 characters and timeout 1..60 seconds')
        job = self.get(ident)
        deadline = time.monotonic() + timeout
        while True:
            matched = any(pattern in bytes(job[s]).decode('utf-8', errors='replace') for s in ('stdout', 'stderr'))
            if matched or job['monitor'].done() or time.monotonic() >= deadline:
                return json.dumps({**self.status(job), 'matched': matched,
                                   'note': 'Literal log match only; inspect the application to confirm it is working.'})
            await asyncio.sleep(min(.1, max(0, deadline-time.monotonic())))

    async def stop(self, ident):
        job = self.get(ident)
        await self.terminate(job, 'requested')
        await asyncio.shield(job['monitor'])
        return json.dumps(self.status(job))

    async def close(self):
        async with self.lock:
            self.closed = True
        await asyncio.gather(*(self.terminate(j, 'session_closed') for j in self.jobs.values()))
        await asyncio.gather(*(j['monitor'] for j in self.jobs.values()))
