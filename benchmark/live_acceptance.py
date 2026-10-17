"""Opt-in real-provider acceptance; never imported by the offline test suite.

Run: python -B benchmark/live_acceptance.py --model MODEL
Credentials: DEEPSEEK_API_KEY or a hidden interactive prompt. No secret files.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eca.agent import Agent
from eca.config import Settings
from eca.store import Store


def tests(body):
    return 'import unittest\n' + body + '\nif __name__ == "__main__": unittest.main()\n'


CASES = {
    'bug': (
        {'stats.py': 'def mean(values):\n    return sum(values) / (len(values) - 1)\n',
         'test_stats.py': tests('from stats import mean\nclass Tests(unittest.TestCase):\n'
             '    def test_mean(self):\n        self.assertEqual(mean([2, 4, 6]), 4)\n'
             '        self.assertEqual(mean([9]), 9)\n        self.assertEqual(mean([-4, 4]), 0)\n'
             '    def test_empty(self):\n        with self.assertRaises(ValueError): mean([])\n')},
        'Fix stats.mean: arithmetic mean, including singleton and negative values; empty input raises ValueError. Preserve tests.'),
    'refactor': (
        {'names.py': 'def normalize_name(value):\n    return " ".join(value.strip().split()).lower()\n',
         'greeting.py': 'from names import normalize_name\ndef greet(value):\n    return "hello " + normalize_name(value)\n',
         'test_names.py': tests('from greeting import greet\nclass Tests(unittest.TestCase):\n'
             '    def test_greeting(self):\n        self.assertEqual(greet("  ADA   Lovelace "), "hello ada lovelace")\n'
             '        self.assertEqual(greet(""), "hello ")\n')},
        'Move normalize_name from names.py into text_utils.py. Update greeting.py, delete names.py using delete tool, preserve behavior and existing tests.'),
    'tests': (
        {'clamp.py': 'def clamp(value, low, high):\n    if low > high:\n        raise ValueError("reversed bounds")\n    return min(high, max(low, value))\n'},
        'Add test_clamp.py using unittest, at least 5 tests covering below, above, inside, equal bounds and reversed bounds. Do not modify clamp.py. Run tests.'),
    'parallel': (
        {'numbers.py': 'def double(x):\n    return x\n',
         'labels.py': 'def label(text):\n    return text\n',
         'test_features.py': tests('from numbers import double\nfrom labels import label\n'
             'class Tests(unittest.TestCase):\n    def test_double(self):\n        self.assertEqual(double(-3), -6)\n'
             '        self.assertEqual(double(0), 0)\n    def test_label(self):\n'
             '        self.assertEqual(label("  ada  "), "ADA")\n')},
        'Use delegate_parallel with exactly two code children: one fixes numbers.double to multiply by 2; the other fixes labels.label to strip whitespace and uppercase. Merge both child changes with merge_agent, then verify in parent. Preserve tests.'),
    'resume': (
        {'left.py': 'def left():\n    return "wrong"\n',
         'right.py': 'def right():\n    return "wrong"\n',
         'test_pair.py': tests('from left import left\nfrom right import right\nclass Tests(unittest.TestCase):\n'
             '    def test_pair(self):\n        self.assertEqual((left(), right()), ("left", "right"))\n')},
        'Fix left.py to return "left" and right.py to return "right". Edit left.py first, then right.py. Preserve tests. Verify both.'),
}


def command(argv, root, timeout=60):
    return subprocess.run(argv, cwd=root, capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=timeout,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)


def verify(name, root, originals):
    checks = {}
    result = command([sys.executable, '-B', '-m', 'unittest', 'discover', '-v'], root)
    checks['unittest_exit_zero'] = result.returncode == 0
    # Independent semantic checks are outside the agent's editable workspace.
    assertions = {
        'bug': 'from stats import mean; assert mean([1,2,6]) == 3; assert mean([5]) == 5',
        'refactor': 'from text_utils import normalize_name; from greeting import greet; assert normalize_name(" A  B ") == "a b"; assert greet(" X ") == "hello x"',
        'parallel': 'from numbers import double; from labels import label; assert double(11)==22; assert label(" x ")=="X"',
        'resume': 'from left import left; from right import right; assert (left(),right())==("left","right")',
        'tests': 'import unittest; assert unittest.defaultTestLoader.discover(".").countTestCases() >= 5',
    }
    checks['external_assertions'] = command([sys.executable, '-B', '-c', assertions[name]], root).returncode == 0
    checks['original_tests_preserved'] = all((root/p).is_file() and (root/p).read_text('utf-8') == text
        for p, text in originals.items() if p.startswith('test_'))
    if name == 'refactor':
        checks['old_module_deleted'] = not (root/'names.py').exists()
    if name == 'tests':
        target = root/'clamp.py'
        content = target.read_bytes()
        checks['implementation_preserved'] = content == originals['clamp.py'].encode()
        try:
            target.write_text('def clamp(value, low, high):\n    return value\n', encoding='utf-8')
            mutant = command([sys.executable, '-B', '-m', 'unittest', 'discover'], root)
            checks['tests_reject_broken_implementation'] = mutant.returncode != 0
        finally:
            target.write_bytes(content)
    return checks, (result.stdout + result.stderr)[-6000:]


async def run_case(name, run_root, key, model, rates=None):
    originals, task = CASES[name]
    root = run_root/name
    root.mkdir()
    for filename, content in originals.items():
        (root/filename).write_text(content, encoding='utf-8', newline='')
    guidance = ('Use Python standard library only. Do not install dependencies or access the network. '
                'Only shell test command approved: python -B -m unittest discover -v. '
                'Do not change AGENTS.md or existing tests unless explicitly requested. '
                'Isolated children cannot run tests; parent must verify after merging.\n')
    (root/'AGENTS.md').write_text(guidance, encoding='utf-8')
    command(['git','init','-q'], root)
    command(['git','add','.'], root)
    baseline_index = command(['git','ls-files','--stage'], root).stdout
    settings = Settings(root.resolve(), model=model, base_url='https://api.deepseek.com/v1',
        api_key=key, permission='accept-edits', project_memory=False, max_turns=24,
        subagent_max_turns=12, subagent_timeout=300, request_timeout=120, max_output_tokens=8192)
    # Explicit caller-supplied snapshot; never guess a provider tariff.
    if rates:
        settings.pricing = {model: rates}
    settings.validate()
    events, denied = [], []
    interrupted = False
    job = None
    async def approve(message, detail):
        ok = message.startswith('Run shell') and detail.strip() == 'python -B -m unittest discover -v'
        if not ok:
            denied.append(message.split('?')[0])
        return ok
    async def ask(_):
        return 'Proceed with the specified acceptance criteria; no further product decisions are needed.'
    def emit(event, data):
        nonlocal interrupted
        # Persist metadata only, not prompts, source, model text or credentials.
        if event in {'turn','tool','subagent_progress'}:
            entry = {'event':event}
            if event == 'tool': entry['name'] = data['name']
            elif event == 'turn': entry['turn'] = data
            else: entry.update(session=data['session'], kind=data['event'])
            events.append(entry)
        if name == 'resume' and not interrupted and event == 'result' and isinstance(data, str) and data.startswith('Saved '):
            interrupted = True
            job.cancel()
    store = Store(root)
    state = store.create()
    agent = Agent(settings, store, state, approve, ask, emit)
    started = time.monotonic()
    error = None
    try:
        job = asyncio.create_task(agent.run(task))
        try:
            await asyncio.wait_for(job, 900)
        except asyncio.CancelledError:
            if not interrupted: raise
        if name == 'resume' and interrupted:
            ident = state['id']
            await agent.close()
            store.close()
            store = Store(root)
            state = store.load(ident)
            agent = Agent(settings, store, state, approve, ask, emit)
            await asyncio.wait_for(agent.run('Continue the original task after interruption. Inspect actual files first; do not repeat completed edits. Verify both functions.'), 900)
    except Exception as exc:
        error = type(exc).__name__
    finally:
        elapsed = round(time.monotonic()-started, 2)
        usage = agent.ledger.summary(state)
        changes = agent.changes.list()
        children = [store.peek(i)['status'] for i in state.get('children', [])]
        test_evidence = False
        for (raw,) in store.db.execute("SELECT result FROM actions WHERE session_id=? AND name='shell'", (state['id'],)):
            try:
                shell = json.loads(raw)
                output = shell.get('stdout', '') + shell.get('stderr', '')
                test_evidence |= shell.get('exit_code') == 0 and bool(re.search(r'Ran [1-9][0-9]* tests?', output))
            except (ValueError, TypeError):
                pass
        pending = set()
        for message in state['messages']:
            if message['role'] == 'assistant':
                pending.update(c['id'] for c in message.get('tool_calls', []))
            elif message['role'] == 'tool':
                pending.discard(message['tool_call_id'])
        await agent.close()
        store.close()
    try:
        checks, test_output = verify(name, root, originals)
    except Exception as exc:
        checks, test_output = {'verifier_completed': False}, type(exc).__name__
    checks['agent_finished'] = state['status'] == 'idle' and error is None
    checks['agent_ran_nonempty_tests'] = test_evidence
    checks['tool_results_paired'] = not pending
    checks['git_index_preserved'] = command(['git','ls-files','--stage'], root).stdout == baseline_index
    checks['guidance_preserved'] = (root/'AGENTS.md').is_file() and (root/'AGENTS.md').read_text('utf-8') == guidance
    if name == 'parallel':
        checks['two_completed_children'] = len(children) == 2 and all(s == 'idle' for s in children)
        checks['merge_used'] = any(e.get('name') == 'merge_agent' for e in events)
    if name == 'resume':
        checks['interrupted_and_resumed'] = interrupted
        checks['no_duplicate_writes'] = len(changes) == 2
    result = dict(case=name, passed=all(checks.values()), checks=checks, elapsed_seconds=elapsed,
        status=state['status'], error_type=error, usage=usage, changes=changes,
        children=children, denied_actions=denied, events=events, unittest_output=test_output)
    (run_root/(name+'.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['case','passed','checks','elapsed_seconds','status','error_type','usage']},ensure_ascii=False), flush=True)
    return result


async def main(args, key):
    runner_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    root = Path(args.output).resolve()/('run-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
    root.mkdir(parents=True)
    print('Artifacts: '+str(root), flush=True)
    results = []
    for name in args.cases:
        print('Starting '+name, flush=True)
        results.append(await run_case(name, root, key, args.model, args.rates))
    report = dict(model=args.model, endpoint='https://api.deepseek.com/v1', runner_sha256=runner_hash,
        commit=command(['git','rev-parse','HEAD'],Path(__file__).resolve().parents[1]).stdout.strip(),
        cases=results, passed=sum(r['passed'] for r in results), total=len(results))
    (root/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),encoding='utf-8')
    print(f"Finished: {report['passed']}/{report['total']}",flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', default=str(Path(__file__).resolve().parents[1]/'output'/'live-acceptance'))
    parser.add_argument('--cases', nargs='+', choices=list(CASES), default=list(CASES))
    parser.add_argument('--rates', type=json.loads, help='Explicit per-million token price snapshot: input, output, cache_read, currency. Omit for unknown costs.')
    args = parser.parse_args()
    credential = os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('DeepSeek credential: ')
    if not credential: parser.error('A DeepSeek credential is required')
    asyncio.run(main(args, credential))
