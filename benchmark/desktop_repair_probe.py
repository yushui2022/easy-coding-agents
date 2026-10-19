"""Replay a preserved faulty candidate through real DesktopRPC verification/repair.

No renderer automation. Credentials arrive on private stdin; checks live outside
the candidate project. First stage is read-only assessment, then runtime repair.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchmark.agent_cases import verify
from benchmark.project_cases import CASES
from benchmark.agent_eval import source_snapshot, write_json
from eca.desktop_rpc import DesktopRPC


def check(root, case):
    checks, output = verify(case, root, CASES[case][0])
    return {'checks': checks, 'passed': all(checks.values()), 'output': output}


async def run(source, root, secret, inject_completion=False):
    case = 'shop_migration'
    root.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for item in source.rglob('*.py'):
        relative = item.relative_to(source)
        if any(part.startswith('.') for part in relative.parts):
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)
        hashes[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    command = f"python -B '{Path(__file__).as_posix()}' check {case}"
    (root/'AGENTS.md').write_text('Isolated regression replay. Standard library only. '
        'Preserve all existing test files byte-for-byte. No dependency installs, network or interactive windows. '
        'Only approved shell command: '+command+'\n', encoding='utf-8')
    (root/'eca.toml').write_text('[agent]\nproject_memory=false\nauto_compact=true\nmax_turns=24\nshared_request_limit=40\n', encoding='utf-8')
    before = await asyncio.to_thread(check, root, case)
    snapshot = source_snapshot()
    metrics, approvals = [], []
    def send(message):
        params = message.get('params', {})
        if params.get('event') == 'request_end':
            metrics.append(params['data'])
        if params.get('event') in {'notice','verification_suite','verification_progress'}:
            data = params['data']
            print(json.dumps({'event':params['event'], 'status':data.get('status') if isinstance(data,dict) else data}),flush=True)
    rpc = DesktopRPC(send)
    model = {key:secret[key] for key in ('api_key','api_format','base_url')}
    model.update(model='deepseek-flash', thinking_mode='fast')
    prompt = ('现有文件是下面任务的候选实现。本次分两个阶段：第一阶段只阅读并简短汇报现有实现，不修改文件。'
        '随后运行时会执行所选验收命令。如果运行时给出失败诊断并要求修复，进入第二阶段，'
        '根据实际诊断修改候选代码，保留全部已有测试并可新增测试；不要修改外部验收脚本。原始需求：\n'
        + CASES[case][1])
    start = time.monotonic()
    try:
        await rpc.dispatch('initialize', {'protocol':1})
        await rpc.dispatch('project.open', {'path':str(root),'model':model})
        await rpc.dispatch('permissions.set', {'mode':'accept-edits'})
        if inject_completion:
            # Deliberate premature-completion fault. Only this first response is
            # synthetic; every repair request uses the real configured provider.
            provider = rpc.runtime.agent.provider
            complete = provider.complete
            first = True
            async def premature(messages, tools, emit):
                nonlocal first
                if first:
                    first = False
                    return {'role':'assistant','content':'Candidate ready for runtime verification.'}, {}
                return await complete(messages, tools, emit)
            provider.complete = premature
        await rpc.dispatch('task.start', {'prompt':prompt,'checks':[command],'repair_attempts':2})
        timed_out = False
        while rpc.run_id:
            if time.monotonic()-start > 300:
                timed_out = True
                await rpc.dispatch('task.cancel', {})
                break
            for entry,future in list(rpc.pending.values()):
                if future.done(): continue
                allowed = entry['kind']=='approval' and str(entry.get('detail','')).strip()==command
                approvals.append({'kind':entry['kind'],'allowed':allowed})
                await rpc.dispatch('input.reply', {**entry,'value':allowed if entry['kind']=='approval' else '按原需求和实际验收结果处理。'})
            await asyncio.sleep(.1)
        if rpc.finishing: await rpc.finishing
        after = await asyncio.to_thread(check, root, case)
        after['checks']['all_candidate_tests_preserved'] = all(
            (root/name).is_file() and hashlib.sha256((root/name).read_bytes()).hexdigest() == digest
            for name,digest in hashes.items() if Path(name).name.startswith('test_'))
        after['passed'] = all(after['checks'].values())
        agent = rpc.runtime.agent
        report = {'case':case,'model':'deepseek-flash','thinking_mode':'fast',
            'route':'DesktopRPC.task.start -> Runtime.verified_run -> real DeepSeek repair',
            'scope':'Preserved faulty candidate; explicit read-only first stage to exercise automatic repair, not an unaided fresh task.',
            'synthetic_initial_completion':inject_completion,
            'actual_provider_requests':len(metrics),
            'source':snapshot,'candidate':str(source),'candidate_hashes':hashes,
            'prompt':prompt,'check_command':command,'before':before,'after':after,
            'suite':rpc.snapshot()['suite'],'timed_out':timed_out,
            'elapsed_seconds':round(time.monotonic()-start,2),'metrics':metrics,
            'usage':agent.ledger.summary(agent.state),'approvals':approvals,'human_interventions':0,
            'source_unchanged_at_finish':source_snapshot()['sha256']==snapshot['sha256']}
        write_json(root.parent/(root.name+'.json'),report)
        print(json.dumps({'event':'complete','passed':after['passed'],'seconds':report['elapsed_seconds'],
                         'rounds':[r['status'] for r in report['suite'].get('rounds',[])]}),flush=True)
    finally:
        await rpc.close()


if __name__ == '__main__':
    if sys.argv[1] == 'check':
        result = check(Path.cwd(), sys.argv[2])
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0 if result['passed'] else 1)
    asyncio.run(run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), json.loads(sys.stdin.readline()), '--inject-completion' in sys.argv[3:]))
