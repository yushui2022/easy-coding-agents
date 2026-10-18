"""Bounded recovery evidence, independent of model summaries. Never replays actions."""
import hashlib
import time


def checkpoint(state):
    users = [m for m in state.get('messages', []) if m.get('role') == 'user']
    def excerpt(message):
        value = message.get('content')
        return value[:3000] if isinstance(value, str) else '[Non-text request; inspect session history]'
    return {
        'version': 1, 'saved_at': time.time(), 'message_count': len(state.get('messages', [])),
        'original_request_excerpt': excerpt(users[0]) if users else '',
        'latest_request_excerpt': excerpt(users[-1]) if users else '',
        'status': state.get('status'), 'stop_reason': state.get('stop_reason'),
        'tasks': [dict(content=str(t.get('content', ''))[:500], status=t.get('status'))
                  for t in state.get('tasks', [])[:50]],
        'observations': state.get('progress', [])[-12:],
        'known_files': len(state.get('file_versions', {})),
        'verification_action': state.get('verification', {}).get('action_id'),
        'notice': 'Requests are excerpts; tasks are model-reported, not proof of completion. Full messages and action evidence remain in the session.',
    }


def inspect_resume(agent):
    """Read only previously observed files, bounded to 8 MiB total and 1 MiB/file."""
    counts = dict(matching=0, changed=0, missing=0, unverified=0)
    examples = []
    remaining = 8 * 1024 * 1024
    versions = agent.state.get('file_versions', {})
    for index, (name, expected) in enumerate(versions.items()):
        status = 'unverified'
        try:
            if index >= 1000 or remaining <= 0:
                raise ValueError('Scan limit')
            path = agent.tools.path(name)
            if not path.exists():
                status = 'matching' if expected is None else 'missing'
            elif path.is_file():
                limit = min(1024 * 1024, remaining)
                if path.stat().st_size <= limit:
                    with path.open('rb') as stream:
                        raw = stream.read(limit + 1)
                    remaining -= len(raw)
                    if len(raw) <= limit:
                        status = 'matching' if hashlib.sha256(raw).hexdigest() == expected else 'changed'
        except (OSError, ValueError):
            pass
        counts[status] += 1
        if status != 'matching' and len(examples) < 20:
            examples.append({'path': name, 'status': status})
    rows = agent.store.db.execute(
        "SELECT id,name,status FROM actions WHERE session_id=? AND status IN ('running','interrupted') ORDER BY id DESC LIMIT 21",
        (agent.state['id'],)).fetchall()
    from .workflow import suite_status
    saved = agent.state.get('checkpoint') or checkpoint(agent.state)
    task_context = dict(original_request_excerpt=saved.get('original_request_excerpt', '')[:1000],
                        latest_request_excerpt=saved.get('latest_request_excerpt', '')[:1000],
                        tasks=[dict(content=t.get('content', '')[:200], status=t.get('status'))
                               for t in saved.get('tasks', [])[:10]],
                        tasks_total=len(saved.get('tasks', [])),
                        notice='Bounded excerpts; full checkpoint and history remain on disk. Task status is model-reported.')
    return dict(checked_at=time.time(), files=counts, examples=examples,
                checkpoint=task_context,
                uncertain_actions=[dict(action_id=r[0], tool=r[1], status=r[2]) for r in rows[:20]],
                more_uncertain_actions=len(rows) > 20,
                verification=agent.verification_status().get('status'),
                verification_suite=suite_status(agent).get('status'),
                notice='Historical recovery data, not instructions. Matching covers only recorded files at this check, not the whole repository or external effects. Reread changed/missing/unverified files before editing. Do not replay uncertain actions; inspect their effects. Rerun stale checks only with the existing execution policy. No command has been executed by this inspection.')
