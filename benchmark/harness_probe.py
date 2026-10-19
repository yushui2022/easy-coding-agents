"""Live, unaided harness probe. Credentials are accepted only on private stdin.

Reuses the existing versioned fixtures and external acceptance oracles. This does
not change the Agent, its prompts, tools, or repair implementation.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchmark import agent_eval as evaluation
from eca.config import Settings
from eca.connectivity import list_models
from eca.provider import Provider

DEFAULT_CASES = ['shop_migration', 'shop_batch', 'shop_idempotency', 'user_edits',
                 'tool_failure', 'compact', 'resume']


def summarize_actions(root):
    with sqlite3.connect(f'{(root / ".eca/sessions.sqlite3").as_uri()}?mode=ro', uri=True) as db:
        actions = db.execute('SELECT name,args,result FROM actions ORDER BY id').fetchall()
    shell, tools = [], {}
    for name, args, result in actions:
        tools[name] = tools.get(name, 0) + 1
        if name != 'shell':
            continue
        try:
            data = json.loads(result)
        except (ValueError, TypeError):
            continue
        shell.append({'command': json.loads(args).get('command'),
                      'exit_code': data.get('exit_code'), 'timed_out': data.get('timed_out'),
                      'output': (data.get('stdout', '') + data.get('stderr', ''))[-4000:]})
    return {'tool_counts': tools, 'shell_results': shell,
            'first_agent_shell_passed': shell[0]['exit_code'] == 0 if shell else None}


async def main(options, credential):
    model = options.model
    endpoint = credential['base_url']
    key = credential['api_key']
    settings = Settings(REPO, model=model, base_url=endpoint, api_key=key,
                        api_format=credential['api_format'], thinking_mode=options.thinking_mode)
    catalogue = await list_models(settings)
    if model not in catalogue.get('models', []):
        raise ValueError('Selected model is absent from the live provider catalogue')
    root = Path(options.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    args = evaluation.parser().parse_args(['--model', model, '--base-url', endpoint,
        '--cases', *options.cases, '--verify', '--repair-attempts', '2',
        '--max-turns', '24', '--max-output-tokens', '8192', '--timeout', '300',
        '--shared-request-limit', '60'])
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(),
                'model': model, 'endpoint': endpoint, 'thinking_mode': options.thinking_mode,
                'source': evaluation.source_snapshot(), 'cases': options.cases, 'repeats': 1,
                'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'verification_commands': [evaluation.TEST_COMMAND], 'repair_attempts': 2,
                'max_turns': 24, 'max_output_tokens': 8192, 'timeout_seconds': 300,
                'shared_request_limit': 60,
                'human_assistance_policy': 'No manual edits or diagnostic hints during trials. Fixed clarification replies.',
                'scope': 'Synthetic maintenance fixtures; not a production-repository or enterprise benchmark.',
                'first_pass_definition': 'First runtime verification after the agent finishes; internal self-corrections may precede it.'}
    results = []
    evaluation.write_json(root / 'manifest.json', manifest)
    evaluation.report(root, manifest, results)
    print(json.dumps({'event': 'started', 'output': str(root), 'cases': options.cases}), flush=True)
    for name in options.cases:
        metrics = []

        class MeasuredProvider(Provider):
            async def complete(self, messages, tools, emit):
                def forward(event, data):
                    if event == 'request_end':
                        metrics.append(data)
                    emit(event, data)
                return await super().complete(messages, tools, forward)

        def factory(config):
            config.thinking_mode = options.thinking_mode
            return MeasuredProvider(config)

        trial = root / f'{name}-01'
        print(json.dumps({'event': 'case_start', 'case': name}), flush=True)
        try:
            result = await evaluation.run_case(name, trial, args, key, provider_factory=factory)
            result['action_summary'] = summarize_actions(trial)
        except Exception as exc:
            result = {'case': name, 'trial': trial.name, 'passed': False,
                      'checks': {'runner_completed': False}, 'status': 'infrastructure_error',
                      'error_type': type(exc).__name__}
        result['request_metrics'] = metrics
        result['thinking_mode'] = options.thinking_mode
        results.append(result)
        evaluation.write_json(root / f'{trial.name}.json', result)
        evaluation.report(root, manifest, results)
        print(json.dumps({'event': 'case_finish', 'case': name, 'passed': result['passed'],
                          'seconds': result.get('elapsed_seconds'),
                          'requests': result.get('usage', {}).get('requests'),
                          'failed_checks': [k for k, v in result['checks'].items() if not v]}, ensure_ascii=False), flush=True)
    manifest['source_unchanged_at_finish'] = evaluation.source_snapshot()['sha256'] == manifest['source']['sha256']
    evaluation.write_json(root / 'manifest.json', manifest)
    evaluation.report(root, manifest, results)
    print(json.dumps({'event': 'complete', 'summary': evaluation.aggregate(results, len(options.cases))}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--model', default='deepseek-flash')
    parser.add_argument('--thinking-mode', choices=['fast', 'balanced', 'deep'], default='fast')
    parser.add_argument('--cases', nargs='+', choices=list(evaluation.CASES), default=DEFAULT_CASES)
    args = parser.parse_args()
    try:
        asyncio.run(main(args, json.loads(sys.stdin.readline())))
    except Exception as error:
        print(json.dumps({'event': 'runner_error', 'type': type(error).__name__}), flush=True)
        raise SystemExit(2)
