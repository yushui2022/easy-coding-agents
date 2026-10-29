"""Disposable Linux containers. No host fallback and no write-back from commands."""
import asyncio
import json
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .fsguard import unsymlinked


def snapshot(tools, destination):
    from .workspaces import source_files
    total = count = 0
    destination.chmod(0o755)
    for path in source_files(tools):
        relative = path.relative_to(tools.settings.root)
        # Recheck aliases immediately before copying; never copy links or Git metadata.
        if path.resolve() != tools.settings.root / relative or path.is_symlink():
            raise ValueError('Source aliases are not supported in the sandbox')
        count += 1
        size = path.stat().st_size
        total += size
        if count > 20000 or size > 2_000_000 or total > 50_000_000:
            raise ValueError('Sandbox snapshot exceeds 20,000 files / 2 MB per file / 50 MB total')
        with path.open('rb') as stream:
            raw = stream.read(2_000_001)
        if len(raw) != size:
            raise ValueError('Source changed while preparing sandbox')
        if tools.settings.api_key and tools.settings.api_key.encode() in raw:
            raise ValueError('Configured model credential found in source; sandbox copy refused')
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(0o644)
        for parent in target.parents:
            if parent == destination:
                break
            parent.chmod(0o755)
    return count


def argv(executable, name, source, image, command, timeout=120):
    if ',' in str(source):
        raise ValueError('Sandbox source path cannot contain a comma')
    return [executable, 'run', '--pull=never', '--name', name, '--rm', '--init',
            '--network=none', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            '--pids-limit=128', '--memory=512m', '--memory-swap=512m', '--cpus=1',
            '--user=65534:65534', '--log-driver=none',
            '--mount', f'type=bind,source={source},target=/input,readonly',
            '--tmpfs', '/workspace:rw,nosuid,nodev,size=128m,mode=1777',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m,mode=1777',
            '--workdir=/workspace', '--env', 'HOME=/tmp', '--env', 'PYTHONDONTWRITEBYTECODE=1',
            *[arg for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'FTP_PROXY', 'ALL_PROXY', 'NO_PROXY',
                             'http_proxy', 'https_proxy', 'ftp_proxy', 'all_proxy', 'no_proxy') for arg in ('--env', key + '=')],
            '--entrypoint=/bin/sh', image, '-c',
            f'cp -R /input/. /workspace/ && exec timeout -k 5 {int(timeout)} /bin/sh -c "$1"', 'eca', command]


async def run(tools, command, timeout, runner):
    executable = shutil.which('docker')
    if not executable:
        raise ValueError('Docker sandbox unavailable; refusing host execution')
    root = tools.settings.root
    context = json.loads(await runner([executable, 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'], root, 10, 2000))
    endpoint = context.get('stdout', '').strip()
    if context.get('exit_code') != 0 or context.get('timed_out') or not endpoint.startswith(('unix:///', 'npipe:////./pipe/')):
        raise ValueError('Sandbox requires a local Docker socket; remote contexts are refused')
    prefix = [executable, '--host', endpoint]
    info = json.loads(await runner([*prefix, 'info', '--format', '{{.OSType}}'], root, 10, 2000))
    if info.get('exit_code') != 0 or info.get('timed_out') or info.get('stdout', '').strip() != 'linux':
        raise ValueError('A running Linux Docker engine is required; no host fallback. '
                         'On Windows, start Docker Desktop from the Start menu and wait for engine readiness, '
                         'then retry. This tool does not start or reset Docker Desktop.')
    base = tools.settings.state_dir / 'sandbox'
    if not unsymlinked(base, tools.settings.root):
        raise ValueError('Sandbox storage must not be an alias')
    base.mkdir(parents=True, exist_ok=True)
    name = 'eca-' + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='source-', dir=base) as directory:
        # Synchronous bounded copy avoids a cancelled background thread outliving cleanup.
        snapshot(tools, Path(directory))
        records = tools.state.setdefault('sandbox_runs', [])
        unresolved = [r for r in records if r.get('cleanup') != 'removed']
        if len(unresolved) >= 100:
            raise ValueError('Too many unconfirmed sandbox runs; inspect their containers before continuing')
        completed = [r for r in records if r.get('cleanup') == 'removed']
        records[:] = unresolved + completed[-19:]
        record = {'container': name, 'endpoint': endpoint, 'image': tools.settings.sandbox_image,
                  'created_at': datetime.now(timezone.utc).isoformat(),
                  'execution': 'unknown', 'cleanup': 'pending'}
        records.append(record)
        # Persist identity before dispatch: a crash must not erase the cleanup target.
        tools.checkpoint()
        tools.emit('notice', f'Sandbox container {name}: network disabled; command writes are discarded.')
        try:
            args = argv(executable, name, Path(directory), tools.settings.sandbox_image, command, timeout)
            result = json.loads(await runner([*prefix, *args[1:]],
                                             root, timeout + 10, max(1, tools.settings.output_limit // 3)))
            if result.get('exit_code') in {124, 137}:
                result['timed_out'] = True
            record['execution'] = 'timed_out' if result.get('timed_out') else 'finished'
            record['exit_code'] = result.get('exit_code')
            result['sandbox'] = {'backend': 'docker', 'container': name, 'writes': 'discarded', 'network': 'none'}
            return json.dumps(result, ensure_ascii=False)
        except asyncio.CancelledError:
            record['execution'] = 'cancelled'
            raise
        finally:
            # Killing the Docker client does not stop its container. Always remove by unique name.
            async def remove():
                record['cleanup'] = 'unconfirmed'
                try:
                    outcome = json.loads(await runner([*prefix, 'rm', '-f', name], root, 10, 2000))
                    if outcome.get('timed_out') or (outcome.get('exit_code') != 0 and 'No such container' not in outcome.get('stderr', '')):
                        raise RuntimeError(f'Sandbox cleanup unconfirmed: inspect docker container {name}; do not retry automatically')
                    record['cleanup'] = 'removed'
                finally:
                    tools.checkpoint()
            cleanup = asyncio.create_task(remove())
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await cleanup
                raise
