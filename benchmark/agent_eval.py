"""Opt-in reproducible coding evaluation. Never runs model calls on import."""
import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchmark.agent_cases import CASES, COMPACT_GOAL, USER_CUSTOMIZATION, USER_NOTES, verify
from benchmark.live_acceptance import command
from eca import __version__
from eca.agent import Agent
from eca.config import Settings
from eca.store import Store
from eca.workflow import verified_run, suite_status

SUITE_VERSION = 4
TEST_COMMAND = 'python -B -m unittest discover -v'
GUIDANCE = ('Use Python standard library only. No dependency installs or network access. '
            f'Only approved shell command: {TEST_COMMAND}. '
            'Preserve AGENTS.md and existing tests. Isolated children cannot run tests; parent must test after merging.\n')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def source_snapshot() -> dict:
    files = sorted([*REPO.glob('eca/*.py'), *(REPO / 'agent_memory_core').rglob('*.py'),
                    REPO / 'benchmark/agent_eval.py', REPO / 'benchmark/agent_cases.py',
                    REPO / 'benchmark/project_cases.py', REPO / 'benchmark/live_acceptance.py'])
    hashes = {p.relative_to(REPO).as_posix(): digest(p.read_bytes()) for p in files}
    return dict(files=hashes, sha256=digest(json.dumps(hashes, sort_keys=True).encode()),
                git_commit=command(['git', 'rev-parse', 'HEAD'], REPO).stdout.strip(),
                git_dirty=bool(command(['git', 'status', '--porcelain'], REPO).stdout), version=__version__)


def paired(messages: list[dict]) -> bool:
    pending, seen = set(), set()
    for message in messages:
        if message['role'] == 'assistant':
            if pending:
                return False
            for call in message.get('tool_calls', []):
                if call['id'] in seen:
                    return False
                pending.add(call['id'])
                seen.add(call['id'])
        elif message['role'] == 'tool':
            if message.get('tool_call_id') not in pending:
                return False
            pending.remove(message['tool_call_id'])
        elif pending:
            return False
    return not pending


def fixture(name: str, root: Path) -> tuple[dict, str]:
    originals, _ = CASES[name]
    root.mkdir(parents=True)
    for filename, content in originals.items():
        (root / filename).parent.mkdir(parents=True, exist_ok=True)
        (root / filename).write_bytes(content.encode())
    (root / 'AGENTS.md').write_bytes(GUIDANCE.encode())
    for argv in (['git', 'init', '-q'], ['git', 'add', '.']):
        if command(argv, root).returncode:
            raise RuntimeError('Fixture Git initialization failed')
    index = command(['git', 'ls-files', '--stage'], root).stdout
    if name == 'user_edits':
        (root / 'calculator.py').write_bytes((originals['calculator.py'] + USER_CUSTOMIZATION).encode())
        (root / 'notes.txt').write_bytes(USER_NOTES.encode())
    return originals, index


async def run_case(name: str, root: Path, args: argparse.Namespace, key: str, provider_factory=None) -> dict:
    originals, index = fixture(name, root)
    settings = Settings(root.resolve(), model=args.model, base_url=args.base_url, api_key=key,
        permission='accept-edits', project_memory=False, max_turns=args.max_turns,
        max_output_tokens=args.max_output_tokens, request_timeout=90, network_retries=1,
        subagent_max_turns=8, subagent_timeout=args.timeout, context_window_tokens=32768,
        context_chars=16000 if name == 'compact' else 100000,
        pricing={args.model: args.rates} if args.rates else {})
    settings.shared_request_limit = getattr(args, 'shared_request_limit', 0)
    worker = getattr(args, 'worker_model', None)
    if worker:
        settings.model_profiles = {'eval_worker': {'model': worker, 'base_url': args.worker_base_url,
            'api_format': 'openai', 'api_key_env': args.worker_api_key_env,
            'max_output_tokens': args.max_output_tokens}}
        settings.worker_profiles = ['eval_worker']
    settings.validate()
    denied, questions, interrupted, fault = 0, 0, False, False
    events = []
    job = None
    async def approve(message, detail):
        nonlocal denied
        approved = message.startswith('Run shell') and detail.strip() == TEST_COMMAND
        denied += int(not approved)
        return approved
    async def ask(_):
        nonlocal questions
        questions += 1
        return 'Use the original requirements and acceptance criteria. No additional product decisions are available.'
    def emit(event, data):
        nonlocal interrupted
        if event == 'turn':
            print(f'{root.name}: model turn {data}', flush=True)
        if event == 'tool':
            events.append(data['name'])
        if name == 'resume' and not interrupted and event == 'result' and isinstance(data, str) and data.startswith('Saved '):
            interrupted = True
            job.cancel()
    store = Store(root)
    state = store.create()
    if name == 'compact':
        state['messages'] = [dict(role='user', content=COMPACT_GOAL),
                             dict(role='assistant', content='Historical investigation notes, no edits or tests executed.\n' +
                                  ('Repeated context filler; this is not validation evidence.\n' * 500))]
        store.save(state)
    def create_agent():
        return Agent(settings, store, state, approve, ask, emit,
                     provider=provider_factory(settings) if provider_factory else None)
    agent = create_agent()
    if name == 'tool_failure':
        execute = agent.tools.execute
        async def flaky(name, arguments):
            nonlocal fault
            if name == 'read' and not fault:
                fault = True
                return 'Error: injected transient read failure. No file was read or changed. Retry the read.'
            return await execute(name, arguments)
        agent.tools.execute = flaky
    started, error = time.monotonic(), None
    try:
        job = asyncio.create_task(verified_run(agent, CASES[name][1],
            [TEST_COMMAND] if args.verify else [], args.repair_attempts, worker_first='eval_worker' if worker else None))
        try:
            await asyncio.wait_for(job, args.timeout)
        except asyncio.CancelledError:
            if not interrupted:
                raise
        if interrupted:
            ident = state['id']
            await agent.close()
            store.close()
            store = Store(root)
            state = store.load(ident)
            agent = create_agent()
            await asyncio.wait_for(verified_run(agent,
                                   'Continue the original task after interruption. Inspect files before retrying edits. Verify both functions.',
                                   [TEST_COMMAND] if args.verify else [], args.repair_attempts),
                                   max(0.01, args.timeout - (time.monotonic() - started)))
    except Exception as exc:
        error = type(exc).__name__  # No provider bodies or credentials in reports.
    finally:
        model_elapsed = time.monotonic() - started
        usage = agent.ledger.summary(state)
        verification = suite_status(agent)
        changes = agent.changes.list()
        children = [store.peek(ident)['status'] for ident in state.get('children', [])]
        compact_requests = store.db.execute("SELECT COUNT(*) FROM usage_requests WHERE session_id=? AND purpose='compact'", (state['id'],)).fetchone()[0]
        rows = store.db.execute('SELECT name,result FROM actions WHERE session_id=? ORDER BY id', (state['id'],)).fetchall()
        successful_tests = False
        failures = 0
        for tool, raw in rows:
            failures += int(isinstance(raw, str) and raw.startswith(('Error:', 'Tool failed:', 'Denied')))
            if tool == 'shell':
                try:
                    value = json.loads(raw)
                    successful_tests |= value.get('exit_code') == 0 and bool(re.search(r'Ran [1-9][0-9]* tests?', value.get('stdout', '') + value.get('stderr', '')))
                except (ValueError, TypeError):
                    pass
        await agent.close()
        store.close()
    try:
        checks, output = await asyncio.to_thread(verify, name, root, originals)
    except Exception as exc:
        checks, output = {'verifier_completed': False}, type(exc).__name__
    checks.update(agent_finished=state['status'] == 'idle' and error is None,
                  agent_ran_nonempty_tests=successful_tests, tool_results_paired=paired(state['messages']),
                  git_index_preserved=command(['git', 'ls-files', '--stage'], root).stdout == index,
                  guidance_preserved=(root / 'AGENTS.md').is_file() and (root / 'AGENTS.md').read_bytes() == GUIDANCE.encode())
    if name == 'parallel':
        checks.update(two_completed_children=len(children) == 2 and all(s == 'idle' for s in children), merge_used='merge_agent' in events)
    if name == 'resume':
        checks.update(interrupted_and_resumed=interrupted, no_duplicate_writes=len(changes) == 2)
    if name == 'compact':
        checks['compaction_exercised'] = compact_requests > 0 and state.get('context_start', 0) > 0
    if name == 'tool_failure':
        checks['fault_exercised'] = fault
    if args.verify:
        checks['verification_suite_passed'] = verification['status'] == 'passed'
    return dict(case=name, trial=root.name, passed=all(checks.values()), checks=checks,
                status=state['status'], error_type=error, model_elapsed_seconds=round(model_elapsed, 2),
                elapsed_seconds=round(time.monotonic() - started, 2), usage=usage,
                tool_calls=len(rows), tool_failures=failures, clarification_requests=questions,
                human_interventions=0, scripted_resumes=int(interrupted), compact_requests=compact_requests,
                denied_actions=denied, changes=changes, children=children, test_output=output,
                verification=verification,
                first_verification_passed=(verification.get('rounds', [{}])[0].get('status') == 'passed'
                                           if verification.get('rounds') else None),
                repair_rounds=max(0, len(verification.get('rounds', [])) - 1))


def aggregate(results: list[dict], planned: int) -> dict:
    subtotals = {}
    for result in results:
        for currency, amount in result.get('usage', {}).get('priced_subtotals', {}).items():
            subtotals[currency] = subtotals.get(currency, Decimal(0)) + Decimal(amount)
    return dict(planned=planned, completed=len(results), passed=sum(bool(r['passed']) for r in results),
                incomplete=planned-len(results), requests=sum(r.get('usage', {}).get('requests', 0) for r in results),
                first_verification_passes=sum(r.get('first_verification_passed') is True for r in results),
                repair_rounds=sum(r.get('repair_rounds', 0) for r in results),
                elapsed_seconds=round(sum(r.get('elapsed_seconds', 0) for r in results), 2),
                priced_subtotals={key: str(value) for key, value in subtotals.items()},
                cost_complete=bool(results) and len(results) == planned and all(
                    r.get('usage', {}).get('incomplete_cost_requests', 1) == 0 and r.get('usage', {}).get('requests', 0) > 0
                    for r in results))


def report(root: Path, manifest: dict, results: list[dict]) -> None:
    summary = aggregate(results, len(manifest['cases']) * manifest['repeats'])
    write_json(root / 'report.json', dict(manifest=manifest, summary=summary, trials=results))
    lines = ['# ECA coding baseline', '',
             f"Model: `{manifest['model']}`. Runtime: {manifest['source']['version']}. Suite: {SUITE_VERSION}.",
             f"Passed: {summary['passed']}/{summary['planned']}; completed: {summary['completed']}; incomplete: {summary['incomplete']}.",
             f"Model requests (including retries, compaction and descendants): {summary['requests']}.",
             f"First verification passes: {summary['first_verification_passes']}; automatic repair rounds: {summary['repair_rounds']}.",
             f"Priced subtotals: {summary['priced_subtotals'] or 'unknown'}; cost complete: {summary['cost_complete']}.", '',
             '| Trial | Pass | Seconds | Requests | Human interventions | Failed checks |',
             '|---|---|---:|---:|---:|---|']
    for result in results:
        failed = ', '.join(k for k, value in result['checks'].items() if not value)
        lines.append(f"| {result['trial']} | {result['passed']} | {result.get('elapsed_seconds', 0)} | {result.get('usage', {}).get('requests', 0)} | {result.get('human_interventions', 0)} | {failed} |")
    lines += ['', 'Synthetic Python and multi-module SQLite fixtures, not a production-repository benchmark or a competitor ranking. '
              'One trial is not a reliable success-rate estimate. Model aliases may change upstream. '
              'Compaction uses synthetic history; resume uses cooperative cancellation. '
              'Approved test code executes with host permissions; this is not adversarial isolation. '
              'No manual repairs are applied during trials. Unknown costs are not zero.']
    (root / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


async def main(args: argparse.Namespace, key: str) -> Path:
    if getattr(args, 'worker_model', None):
        if not args.verify or not os.environ.get(args.worker_api_key_env):
            raise ValueError('Worker comparison requires --verify and a worker credential environment variable')
        if any(name in {'compact', 'resume'} for name in args.cases):
            raise ValueError('Worker-first comparison currently excludes compact/resume fixtures')
    if not key:
        raise ValueError('Missing API credential; set the selected environment variable')
    if not 1 <= args.repeats <= 10 or not 1 <= args.max_turns <= 60 or not 10 <= args.timeout <= 1800:
        raise ValueError('repeats must be 1..10, max_turns 1..60, timeout 10..1800')
    if len(set(args.cases)) != len(args.cases):
        raise ValueError('Duplicate cases are not allowed; use --repeats')
    if not 0 <= args.repair_attempts <= 3 or (args.repair_attempts and not args.verify):
        raise ValueError('repair-attempts requires --verify and must be 0..3')
    Settings(REPO, model=args.model, base_url=args.base_url, max_output_tokens=args.max_output_tokens,
             pricing={args.model: args.rates} if args.rates else {}).validate()
    root = Path(args.output).resolve() / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    source = source_snapshot()
    manifest = dict(suite_version=SUITE_VERSION, created_at=datetime.now(timezone.utc).isoformat(),
                    source=source, model=args.model, endpoint=args.base_url, cases=args.cases, repeats=args.repeats,
                    max_turns=args.max_turns, max_output_tokens=args.max_output_tokens, timeout=args.timeout,
                    verification_commands=[TEST_COMMAND] if args.verify else [], repair_attempts=args.repair_attempts,
                    settings=dict(api_format='openai', context_window_tokens=32768, context_reserve_tokens=1024,
                                  context_chars=100000, compact_case_context_chars=16000, project_memory=False,
                                  subagent_max_turns=8, subagent_max_calls=3, subagent_concurrency=2,
                                  subagent_timeout=args.timeout, request_timeout=90, network_retries=1,
                                  reasoning_effort='', temperature='provider default',
                                  mode='code', sandbox='none', permission='accept-edits', concurrency=1),
                    worker_model=getattr(args, 'worker_model', None), shared_request_limit=getattr(args, 'shared_request_limit', 0),
                    rates=args.rates, human_assistance_policy='none; fixed replies to clarification requests',
                    fixture_hashes={name: digest(json.dumps(CASES[name], ensure_ascii=False, sort_keys=True).encode()) for name in args.cases})
    write_json(root / 'manifest.json', manifest)
    print('Artifacts: ' + str(root), flush=True)
    results = []
    report(root, manifest, results)
    try:
        for repeat in range(1, args.repeats + 1):
            for name in args.cases:
                trial = f'{name}-{repeat:02d}'
                print('Starting ' + trial, flush=True)
                try:
                    result = await run_case(name, root / trial, args, key)
                except Exception as exc:
                    result = dict(case=name, trial=trial, passed=False, checks={'runner_completed': False},
                                  status='infrastructure_error', error_type=type(exc).__name__)
                results.append(result)
                write_json(root / (trial + '.json'), result)
                report(root, manifest, results)
                print(json.dumps(dict(trial=trial, passed=result['passed'], failed_checks=[k for k,v in result['checks'].items() if not v])), flush=True)
    finally:
        manifest['source_unchanged_at_finish'] = source_snapshot()['sha256'] == source['sha256']
        report(root, manifest, results)
        write_json(root / 'manifest.json', manifest)
    return root


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--base-url', default='https://api.deepseek.com/v1')
    p.add_argument('--api-key-env', default='DEEPSEEK_API_KEY')
    p.add_argument('--output', default=str(REPO / 'output' / 'agent-eval'))
    p.add_argument('--cases', nargs='+', choices=list(CASES), default=list(CASES))
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--max-turns', type=int, default=16)
    p.add_argument('--max-output-tokens', type=int, default=4096)
    p.add_argument('--timeout', type=int, default=360)
    p.add_argument('--rates', type=json.loads, help='Verified per-million rates; omit to keep costs unknown')
    p.add_argument('--verify', action='store_true', help='Run the explicit runtime verification workflow after each task')
    p.add_argument('--worker-model', help='Use the existing worker-first/check/main-repair pipeline for comparison')
    p.add_argument('--worker-base-url', default='https://api.deepseek.com/v1')
    p.add_argument('--worker-api-key-env', default='DEEPSEEK_API_KEY')
    p.add_argument('--shared-request-limit', type=int, default=0)
    p.add_argument('--repair-attempts', type=int, default=0, help='With --verify, permit 0..3 automatic repair rounds')
    return p


if __name__ == '__main__':
    options = parser().parse_args()
    try:
        output = asyncio.run(main(options, os.environ.get(options.api_key_env, '')))
        result = json.loads((output / 'report.json').read_text('utf-8'))['summary']
        raise SystemExit(0 if result['passed'] == result['planned'] else 1)
    except (ValueError, OSError) as exc:
        print('Evaluation setup failed: ' + type(exc).__name__, file=sys.stderr)
        raise SystemExit(2)
