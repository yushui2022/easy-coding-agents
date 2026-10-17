"""Bounded source snapshots and conflict-checked, journaled integration."""
import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess


def source_files(tools):
    """Respect Git ignores without copying Git metadata or credentials."""
    from .tools import SKIP
    try:
        result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
            cwd=tools.settings.root, capture_output=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result is None or result.returncode:
        yield from tools.files()
        return
    for name in sorted(set(os.fsdecode(result.stdout).split('\0')) - {''}):
        parts = Path(name).parts
        if any(part.lower() in SKIP for part in parts):
            continue
        try:
            target = tools.path(name)
        except ValueError:
            continue
        # Do not reinterpret aliases as independent source files.
        if target != tools.settings.root / name:
            continue
        if target.is_file():
            yield target


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def workspace(store, state):
    path = store.root / '.eca' / 'workspaces' / state['id']
    if path.resolve() != path or not path.is_relative_to(store.root / '.eca'):
        raise ValueError('Invalid isolated workspace path')
    return path


async def parallel(agent, tasks):
    from .agent import Agent
    if agent.child or agent.settings.mode == 'chat':
        return 'Denied: delegation unavailable.'
    remaining = agent.settings.subagent_max_calls - agent.child_calls
    if not tasks or len(tasks) > min(remaining, 8):
        raise ValueError('Batch exceeds remaining subagent calls or concurrency limit (8)')
    for task in tasks:
        if (not isinstance(task, dict) or set(task) - {'task', 'mode'} or
            not isinstance(task.get('task'), str) or not task['task'].strip() or len(task['task']) > 12000 or
            task.get('mode', 'plan') not in {'plan', 'code'}):
            raise ValueError('Each task needs task text and optional plan/code mode')
        if task.get('mode') == 'code' and agent.settings.mode != 'code':
            return 'Denied: child mode exceeds parent permissions.'
    # Read once before starting any child; include current uncommitted source bytes.
    files, size = {}, 0
    for path in source_files(agent.tools):
        if path.stat().st_size > 2_000_000:
            raise ValueError('Snapshot contains a file over 2 MB; narrow the project root')
        data = path.read_bytes()
        size += len(data)
        if size > 20_000_000 or len(files) >= 2000:
            raise ValueError('Snapshot exceeds 20 MB / 2000 files; narrow the project root')
        files[path.relative_to(agent.settings.root).as_posix()] = data
    agent.child_calls += len(tasks)
    states = []
    for task in tasks:
        state = agent.store.create(task.get('mode', 'plan'))
        state.update(status='preparing', title=task['task'][:80], parent_id=agent.state['id'], billing_root=agent.state.get('billing_root', agent.state['id']),
                     isolated=True, model_profile=agent.settings.model_profile, baseline={p: digest(data) for p, data in files.items()},
                     usage_tracking_complete=agent.state.get('usage_tracking_complete', True))
        agent.state.setdefault('children', []).append(state['id'])
        states.append(state)
        agent.store.save(state)
        agent.store.save(agent.state)
    try:
        for state in states:
            root = workspace(agent.store, state)
            root.mkdir(parents=True, exist_ok=False)
            for name, data in files.items():
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            state['status'] = 'queued'
            agent.store.save(state)
            agent.emit('subagent_progress', dict(session=state['id'], event='status', data='queued'))
    except Exception as exc:
        for state in states:
            state.update(status='error', stop_reason=f'Snapshot preparation failed: {type(exc).__name__}')
            agent.store.save(state)
        raise
    semaphore = asyncio.Semaphore(agent.settings.subagent_concurrency)
    prompt_lock = asyncio.Lock()

    async def approve(session, message, detail):
        async with prompt_lock:
            agent.emit('notice', f'Approval for isolated Agent {session[:8]}')
            if message.startswith('Write '):
                agent.emit('diff', detail)
            return await agent.tools.approve(message, detail)

    async def question(*args):
        async with prompt_lock:
            return await agent.tools.question(*args)

    async def run(task, state):
        settings = replace(agent.settings, mode=state['mode'], max_turns=min(
            agent.settings.max_turns, agent.settings.subagent_max_turns))
        def emit(event, data):
            if event != 'text':
                agent.emit('subagent_progress', dict(session=state['id'], event=event, data=data))
        async def child_approve(message, detail):
            return await approve(state['id'], message, detail)
        child = None
        try:
            async with semaphore:
                child = Agent(settings, agent.store, state, child_approve, question, emit, child=True)
                emit('status', 'running')
                await asyncio.wait_for(child.run(task['task']), agent.settings.subagent_timeout)
        except TimeoutError:
            state.update(status='timeout', stop_reason='Child time limit reached')
        except asyncio.CancelledError:
            state.update(status='interrupted', stop_reason='Parent cancelled; queued/running task stopped')
            raise
        except Exception as exc:
            state.update(status='error', stop_reason=f'Child failed: {type(exc).__name__}')
        finally:
            if child is not None:
                try:
                    await child.close()
                except Exception as exc:
                    state.update(status='error', stop_reason=f'Child cleanup failed: {type(exc).__name__}')
            agent.store.save(state)
            emit('status', state['status'])
        summary = next((m.get('content') for m in reversed(state['messages'])
                        if m['role'] == 'assistant' and not m.get('tool_calls')), '')
        try:
            changes = review(agent, state)
        except (OSError, ValueError):
            changes = [{'status':'unavailable', 'notice':'Inspect the retained workspace manually.'}]
        return dict(session=state['id'], status=state['status'], summary=(summary or '')[:2000],
                    stop_reason=state.get('stop_reason'), changes=changes,
                    workspace=str(workspace(agent.store, state)), notice='Isolated edits need merge_agent; report is unverified.')

    jobs = [asyncio.create_task(run(task, state)) for task, state in zip(tasks, states)]
    try:
        return json.dumps(await asyncio.gather(*jobs), ensure_ascii=False)
    finally:
        for job in jobs:
            if not job.done():
                job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        for state in states:
            if state['status'] in {'queued', 'preparing'}:
                state.update(status='interrupted', stop_reason='Batch stopped before this task started')
                agent.store.save(state)


async def merge(agent, session, paths):
    from .tools import Tools
    if agent.child or agent.settings.mode != 'code':
        return 'Denied: merge requires a parent in code mode.'
    state = agent.store.peek(session)
    if state.get('parent_id') != agent.state['id'] or not state.get('isolated') or state['status'] in {'preparing', 'queued', 'running'}:
        raise ValueError('Not a completed isolated child of this session')
    if not paths or len(paths) > 100 or len(set(paths)) != len(paths) or not all(isinstance(x, str) for x in paths):
        raise ValueError('Select 1..100 unique file paths to merge')
    child_tools = Tools(replace(agent.settings, root=workspace(agent.store, state)), state,
                        agent.tools.approve, agent.tools.question, agent.emit)
    if not child_tools.settings.root.is_dir():
        raise ValueError('Isolated workspace is unavailable')
    changes = []
    for name in paths:
        source, target = child_tools.path(name), agent.tools.path(name)
        name = target.relative_to(agent.settings.root).as_posix()
        if source.relative_to(child_tools.settings.root).as_posix() != name:
            raise ValueError('Child and parent paths resolve differently')
        if source.exists() and (not source.is_file() or source.stat().st_size > 2_000_000):
            raise ValueError('Only text files up to 2 MB can be merged')
        if not source.exists():
            recorded = agent.store.db.execute(
                'SELECT after,status FROM file_changes WHERE session_id=? AND path=? ORDER BY id DESC LIMIT 1',
                (state['id'], name)).fetchone()
            if name not in state['baseline'] or recorded is None or recorded[0] is not None or recorded[1] not in {'applied', 'accepted'}:
                raise ValueError('Missing child file has no completed deletion record')
        if target.exists() and (not target.is_file() or target.stat().st_size > 2_000_000):
            raise ValueError('Target cannot be compared safely')
        before = target.read_bytes() if target.exists() else None
        after = source.read_bytes() if source.exists() else None
        if before == after:
            continue
        if digest(before) != state['baseline'].get(name):
            raise ValueError(f'Merge conflict: {name}; parent changed since snapshot')
        if before is not None and '\x00' in before.decode('utf-8') or after is not None and '\x00' in after.decode('utf-8'):
            raise ValueError('Binary files cannot be merged')
        changes.append((target, before, after.decode('utf-8') if after is not None else None))
    # Preflight the whole selection before any write. Each write rechecks after approval.
    return json.dumps([await agent.tools.change(target, before, content)
                       for target, before, content in changes], ensure_ascii=False)


def review(agent, state):
    """Read-only summary of child file-tool changes; never repairs running sessions."""
    if not state.get('isolated'):
        return []
    from .tools import Tools
    child_tools = Tools(replace(agent.settings, root=workspace(agent.store, state)), state, None, None, lambda *_: None)
    rows = agent.store.db.execute('SELECT DISTINCT path FROM file_changes WHERE session_id=? LIMIT 201', (state['id'],)).fetchall()
    result = []
    for (name,) in rows[:200]:
        path = child_tools.path(name)
        if path.exists() and (not path.is_file() or path.stat().st_size > 2_000_000):
            result.append(dict(path=name, status='unreadable'))
            continue
        current = path.read_bytes() if path.exists() else None
        if digest(current) != state.get('baseline', {}).get(name):
            result.append(dict(path=name, status='deleted' if current is None else 'modified' if name in state['baseline'] else 'added'))
    if len(rows)>200:
        result.append(dict(status='truncated'))
    return result
