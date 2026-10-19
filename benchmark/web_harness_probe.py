"""Replay the real, originally broken HTML through the Desktop task path, unaided."""
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from eca.desktop_rpc import DesktopRPC
from benchmark.agent_eval import source_snapshot, write_json, paired

CHECK = "python -B 'G:/Projects/easy-coding-agents/benchmark/scene_browser_check.py'"


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    original = Path('G:/Projects/deepseek-glass-ecosystem/.eca/sessions.sqlite3')
    with sqlite3.connect(original.as_uri()+'?mode=ro', uri=True) as db:
        # Change 4 is the last HTML before any Codex debugging feedback.
        row = db.execute("SELECT after FROM file_changes WHERE id=4 AND path='index.html'").fetchone()
    if not row:
        raise ValueError('Original pre-feedback HTML revision missing')
    (root / 'index.html').write_bytes(row[0])
    guidance = ('This is an isolated copy of a real HTML task. Preserve the scene and its existing controls. '
        'Do not change AGENTS.md or eca.toml. No dependency installs, arbitrary shell, or interactive browser control. '
        'A hidden browser test is available; it does not interact with user windows. '
        f'The sole approved shell command is: {CHECK}\n')
    (root / 'AGENTS.md').write_text(guidance, encoding='utf-8')
    (root / 'eca.toml').write_text('[agent]\nproject_memory=false\nauto_compact=true\nmax_turns=30\nshared_request_limit=60\n',encoding='utf-8')
    return {'source': str(original), 'change_id': 4,
            'html_sha256': hashlib.sha256(row[0]).hexdigest(),
            'guidance_sha256': hashlib.sha256(guidance.encode()).hexdigest()}


async def main(root, secret):
    origin = prepare(root)
    metrics, events, approvals = [], [], []
    source = source_snapshot()
    model = {k: secret[k] for k in ('api_key','api_format','base_url')}
    model.update(model='deepseek-flash', thinking_mode='fast')
    def send(message):
        params = message.get('params', {})
        name, data = params.get('event'), params.get('data')
        if name == 'request_end':
            metrics.append(data)
        if name in ('turn','tool','run_finished','error','notice'):
            entry = {'event': name, 'name': data.get('name') if isinstance(data,dict) else None}
            events.append(entry)
            print(json.dumps(entry),flush=True)
    rpc = DesktopRPC(send)
    start = time.monotonic()
    error = None
    try:
        await rpc.dispatch('initialize',{'protocol':1})
        await rpc.dispatch('project.open',{'path':str(root),'model':model})
        await rpc.dispatch('permissions.set',{'mode':'accept-edits'})
        prompt = ('这个目录是一份现有的 Three.js 玻璃微缩生态场景页面，现在存在加载及显示问题。'
            '请自行排查并修好实际文件，保留生态场景及拖动、缩放、暂停、昼夜控制、重置功能。'
            '初始、重置及窄屏应完整展示玻璃盒体，不应把主体裁切。不要安装依赖或启动交互窗口。'
            f'已提供可执行的隔离浏览器验收命令：{CHECK}。你可以运行它获取实际错误并自查修复。'
            '保留 AGENTS.md 和 eca.toml，不得修改验收脚本；完成后执行验收并如实报告未验证部分。')
        await rpc.dispatch('task.start',{'prompt':prompt,'checks':[CHECK]})
        while rpc.run_id:
            if time.monotonic()-start > 480:
                error = 'ProbeTimeout'
                await rpc.dispatch('task.cancel',{})
                break
            for entry,future in list(rpc.pending.values()):
                if future.done(): continue
                allowed = entry['kind']=='approval' and str(entry.get('detail','')).strip()==CHECK
                approvals.append({'kind':entry['kind'],'allowed':allowed})
                await rpc.dispatch('input.reply',{**entry,'value':allowed if entry['kind']=='approval' else '按原有需求自行决定，先检查实际文件并执行提供的验收。'})
            await asyncio.sleep(.1)
        if rpc.finishing: await rpc.finishing
        agent = rpc.runtime.agent
        state = agent.state
        actions = []
        for name,args,result in agent.store.db.execute('SELECT name,args,result FROM actions WHERE session_id=? ORDER BY id',(state['id'],)):
            actions.append({'name':name,'args':json.loads(args) if name=='shell' else None,'result':result if name=='shell' else None})
        report = {'origin':origin,'source':source,'model':'deepseek-flash','thinking_mode':'fast',
            'route':'DesktopRPC.task.start -> Runtime -> Agent; production desktop repair budget remains zero',
            'prompt':prompt,'elapsed_seconds':round(time.monotonic()-start,2),'error_type':error,
            'status':state['status'],'suite':rpc.snapshot()['suite'],'usage':agent.ledger.summary(state),
            'requests':metrics,'actions':actions,'approvals':approvals,'events':events,
            'human_interventions':0,'tool_results_paired':paired(state['messages']),
            'guidance_preserved':hashlib.sha256((root/'AGENTS.md').read_bytes()).hexdigest()==origin['guidance_sha256'],
            'final_response':next((m.get('content') for m in reversed(state['messages']) if m['role']=='assistant' and m.get('content')),''),
            'source_unchanged_at_finish':source_snapshot()['sha256']==source['sha256']}
        write_json(root.parent / (root.name+'.json'), report)
        print(json.dumps({'event':'complete','status':report['status'],'suite':report['suite']['status'],
                          'elapsed_seconds':report['elapsed_seconds'],'requests':report['usage']['requests']}),flush=True)
    finally:
        await rpc.close()


if __name__=='__main__':
    try:
        asyncio.run(main(Path(sys.argv[1]).resolve(),json.loads(sys.stdin.readline())))
    except Exception as exc:
        print(json.dumps({'event':'runner_error','type':type(exc).__name__}),flush=True)
        raise SystemExit(2)
