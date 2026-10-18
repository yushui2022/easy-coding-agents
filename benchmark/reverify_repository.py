"""Reverify an unchanged repository-eval patch without any model/API calls."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark.repository_eval import git, TEST
from eca.agent import Agent
from eca.config import Settings
from eca.store import Store
from eca.workflow import verified_run, suite_status


class VerificationOnly:
    async def complete(self, messages, tools, emit):
        return {'role': 'assistant', 'content': 'No edits requested; run the external verification command.'}, {}

    async def close(self):
        pass


async def main(run):
    run = run.resolve()
    report = json.loads((run/'report.json').read_text('utf-8'))
    root = run/'checkout'
    if not all(v for k, v in report['checks'].items() if k != 'workflow_passed'):
        raise ValueError('Original task must have passed independent acceptance')
    patch = git(root, 'diff', '--no-ext-diff')
    if patch != (run/'changes.diff').read_bytes():
        raise ValueError('Model patch changed since original acceptance')
    if hashlib.sha256((root/'acceptance_test.py').read_bytes()).hexdigest() != report['contract_sha256']:
        raise ValueError('Acceptance contract changed')
    async def approve(message, detail):
        return message.startswith('Run shell') and detail.strip() == TEST
    store = Store(root)
    agent = Agent(Settings(root, project_memory=False), store, store.create(),
                  approve, approve, lambda *_: None, provider=VerificationOnly())
    started = time.monotonic()
    try:
        before = agent.memory().fingerprint()
        if before is None:
            raise ValueError('Snapshot still unavailable')
        passed = await verified_run(agent, 'Verification only. Do not edit files.', [TEST], 0)
        after = agent.memory().fingerprint()
        evidence = {'original_report': 'report.json', 'model_api_calls': 0,
                    'method': 'Verification-only stub response, real shell test and runtime workflow. No coding rerun.',
                    'passed': passed and before == after and patch == git(root, 'diff', '--no-ext-diff'),
                    'fingerprint_before': before, 'fingerprint_after': after,
                    'patch_sha256': hashlib.sha256(patch).hexdigest(),
                    'verification': suite_status(agent),
                    'elapsed_seconds': round(time.monotonic()-started, 2)}
        destination = run/('reverification-' + str(time.time_ns()) + '.json')
        destination.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        print(json.dumps({'report': str(destination), **evidence}, indent=2))
        return 0 if evidence['passed'] else 1
    finally:
        await agent.close()
        store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args().run)))
