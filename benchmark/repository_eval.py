"""Opt-in model editing acceptance on a pinned DeerFlow Git snapshot.

No checkout/reset in the source repository. No dependency installation.
Reports targeted acceptance only, not the upstream integration suite.
"""
import argparse
import asyncio
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from eca.agent import Agent
from eca.config import Settings
from eca.store import Store
from eca.workflow import verified_run, suite_status

REVISION = '34316550dffbe8fbaed5678a6be87c5d3c65155b'
# These unrelated skill-scanner files are absent in the source working tree;
# the first archive extraction also lost one during a read. Do not recreate
# them repeatedly or attempt to bypass host protection. Record the exclusions.
EXCLUDED = {'backend/tests/test_skillscan_native.py',
            'backend/packages/harness/deerflow/skills/skillscan/orchestrator.py'}
OLD = re.compile(r'\blookup_thread_id\b')
HELPER = 'backend/app/channels/connection_identity.py'
LOCAL_STUB = 'backend/tests/test_channels.py'
TEST = 'python -B acceptance_test.py'
PROMPT = '''In this isolated DeerFlow snapshot, migrate the public async helper
lookup_thread_id in the channel connection identity module to resolve_thread_id.
Update every Python import/call of that public helper, including existing tests.
Do not rename ChannelManager._lookup_thread_id or unrelated similarly named methods.
Remove the old public helper name (no compatibility alias).
Fix its connection ownership boundary: if msg.connection_id is present and repo
is None, return None without querying the global store. A present repo returning
None must also never fall back. Propagate repository errors. Preserve unbound
message behavior and attach_connection_identity.
Preserve original tests except the required public-name migration. Change only
Python files that reference this public helper. Preserve all other files,
including AGENTS.md and acceptance_test.py. For this bounded evaluation, do not
install dependencies or run the full upstream suite. The only approved shell
command is: python -B acceptance_test.py
Use navigation tools to locate callers, make the changes and run that contract.
'''


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, check=True, timeout=60).stdout


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(root):
    result = subprocess.run([sys.executable, '-B', 'acceptance_test.py'], cwd=root,
                            capture_output=True, text=True, timeout=60)
    return {'exit_code': result.returncode, 'output': result.stdout + result.stderr}


async def main(args):
    key = os.environ.get('DEEPSEEK_API_KEY')
    if not key:
        raise ValueError('DEEPSEEK_API_KEY is required')
    source = args.source.resolve()
    output = args.output.resolve()
    if output.is_relative_to(source):
        raise ValueError('Output must be outside the source repository')
    run = output / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    root = run / 'checkout'
    root.mkdir()
    before_status = git(source, 'status', '--porcelain')
    archive = run / 'source.zip'
    git(source, 'archive', '--format=zip', '-o', str(archive), REVISION)
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            if not (root / entry.filename).resolve().is_relative_to(root):
                raise ValueError('Unsafe archive path')
        bundle.extractall(root, members=[e for e in bundle.infolist() if e.filename not in EXCLUDED])
    originals = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    permitted = {p for p, raw in originals.items() if p.endswith('.py') and OLD.search(raw.decode('utf-8', errors='replace'))}
    contract = (REPO / 'benchmark/repository_contract.py').read_bytes()
    (root / 'acceptance_test.py').write_bytes(contract)
    git(root, 'init', '-q')
    git(root, 'add', '.')
    index_before = git(root, 'ls-files', '--stage')
    baseline = check(root)
    if baseline['exit_code'] == 0:
        raise ValueError('Contract unexpectedly passes before edits')
    settings = Settings(root=root, api_key=key, model=args.model,
                        base_url='https://api.deepseek.com/v1', permission='accept-edits',
                        project_memory=False, max_turns=30, max_output_tokens=4096,
                        request_timeout=90, network_retries=1, context_chars=args.context_chars,
                        output_limit=args.output_limit,
                        context_window_tokens=args.context_window_tokens)
    settings.validate()
    store = Store(root)
    state = store.create()
    events = []
    async def approve(message, detail):
        return message.startswith('Run shell') and detail.strip() == TEST
    async def ask(_):
        return 'Follow the original task and its fixed acceptance requirements.'
    def emit(event, data):
        if event == 'turn':
            print('Model turn:', data, flush=True)
        if event == 'tool':
            events.append(data['name'])
    agent = Agent(settings, store, state, approve, ask, emit)
    report = {'revision': REVISION, 'model': args.model, 'source_files': len(originals),
              'excluded_snapshot_files': sorted(EXCLUDED),
              'archive_sha256': sha(archive.read_bytes()), 'permitted_files': sorted(permitted),
              'baseline': baseline, 'prompt': PROMPT, 'status': 'running',
              'limits': {'turns': 30, 'seconds': 600, 'repair_attempts': 1, 'output_limit': args.output_limit, 'context_chars': args.context_chars, 'context_window_tokens': args.context_window_tokens},
              'harness_sha256': sha(Path(__file__).read_bytes()),
              'contract_sha256': sha(contract),
              'runtime_sha256': {p.relative_to(REPO).as_posix(): sha(p.read_bytes()) for p in sorted((REPO/'eca').glob('*.py'))},
              'limitations': 'One targeted task, repository snapshot with two documented exclusions. Package initializers bypassed; AsyncMock store/repo boundaries. No full upstream suite, process-crash or production isolation claim.'}
    def save():
        (run / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    print('Artifacts:', run, flush=True)
    started = time.monotonic()
    error = None
    try:
        await asyncio.wait_for(verified_run(agent, PROMPT, [TEST], 1), timeout=600)
    except Exception as exc:
        error = type(exc).__name__
    finally:
        report.update(status=state['status'], error_type=error, usage=agent.ledger.summary(state),
                      verification=suite_status(agent), tools=events,
                      elapsed_seconds=round(time.monotonic()-started, 2))
        await agent.close()
        store.close()
        save()
    final = check(root)
    changed = [p for p, raw in originals.items() if not (root/p).is_file() or (root/p).read_bytes() != raw]
    remaining, invalid = [], []
    for p in permitted:
        try:
            content = (root/p).read_text('utf-8')
            # This test module also has an unrelated local stub with the same
            # spelling; migrating that stub is explicitly outside task scope.
            if p != LOCAL_STUB and OLD.search(content):
                remaining.append(p)
            ast.parse(content)
        except (SyntaxError, OSError):
            invalid.append(p)
    # Existing caller/test files must be exactly the public identifier rename,
    # preserving assertions, private methods and unrelated behavior.
    migration_only = all((root/p).is_file() and (root/p).read_bytes() ==
                         OLD.sub('resolve_thread_id', originals[p].decode('utf-8')).encode('utf-8')
                         for p in permitted if p not in (HELPER, LOCAL_STUB))
    stub_raw = (root/LOCAL_STUB).read_bytes()
    migration_only &= stub_raw in (originals[LOCAL_STUB],
        originals[LOCAL_STUB].replace(b'(``lookup_thread_id``)', b'(``resolve_thread_id``)'))
    helper_before = ast.parse(originals[HELPER].decode('utf-8'))
    helper_after = ast.parse((root/HELPER).read_text('utf-8'))
    def attach(tree):
        return ast.dump(next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'attach_connection_identity'))
    additions = [p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()
                 and '.git' not in p.relative_to(root).parts and '.eca' not in p.relative_to(root).parts
                 and p.relative_to(root).as_posix() not in originals and p != root/'acceptance_test.py']
    checks = dict(agent_finished=error is None and state['status'] == 'idle',
                  contract_passed=final['exit_code'] == 0, no_old_public_references=not remaining,
                  changed_files_parse=not invalid, caller_and_test_semantics_preserved=migration_only,
                  unrelated_helper_preserved=attach(helper_before) == attach(helper_after),
                  no_unrelated_edits=set(changed) <= permitted, no_unexpected_additions=not additions,
                  contract_unchanged=(root/'acceptance_test.py').read_bytes() == contract,
                  index_preserved=git(root, 'ls-files', '--stage') == index_before,
                  source_status_unchanged=git(source, 'status', '--porcelain') == before_status,
                  workflow_passed=report['verification']['status'] == 'passed')
    report.update(checks=checks, passed=all(checks.values()), changed_files=changed,
                  unexpected_additions=additions, final=final, remaining_references=remaining, invalid_files=invalid)
    (run/'changes.diff').write_bytes(git(root, 'diff', '--no-ext-diff'))
    save()
    print(json.dumps({'passed': report['passed'], 'checks': checks, 'requests': report['usage']['requests']}), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=REPO/'output/repository-eval')
    parser.add_argument('--model', default='deepseek-flash')
    parser.add_argument('--output-limit', type=int, default=120000)
    parser.add_argument('--context-chars', type=int, default=200000)
    parser.add_argument('--context-window-tokens', type=int, default=65536)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args)))
