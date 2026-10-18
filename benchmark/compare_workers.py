"""Paired fixed-fixture evaluations; never infer a win from worker reports."""
import asyncio
from copy import copy
import json
import os
from pathlib import Path

from benchmark.agent_eval import main, parser


async def compare(args):
    if not args.worker_model or not args.verify:
        raise ValueError('Supply --worker-model and --verify; select the same fixed cases for both arms')
    if not os.environ.get(args.api_key_env) or not os.environ.get(args.worker_api_key_env):
        raise ValueError('Missing parent or worker credential environment variable')
    if any(name in {'compact', 'resume'} for name in args.cases):
        raise ValueError('Select cases other than compact/resume for this paired comparison')
    baseline = copy(args)
    baseline.worker_model = None
    key = os.environ[args.api_key_env]
    first = await main(baseline, key)
    second = await main(args, key)
    reports = [json.loads((path/'report.json').read_text('utf-8')) for path in (first, second)]
    result = {'single_model': {'report': str(first), 'summary': reports[0]['summary']},
              'worker_first': {'report': str(second), 'summary': reports[1]['summary']},
              'notice': 'Compare external oracle success, elapsed time and usage. Sequential trials are noisy; repeat before concluding. Unknown costs are not zero.'}
    output = Path(second)/'comparison.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return output


if __name__ == '__main__':
    print(asyncio.run(compare(parser().parse_args())))
