"""Opt-in larger real-model build and external acceptance; no production secrets."""
import argparse
import asyncio
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from eca.agent import Agent
from eca.config import Settings
from eca.store import Store


def run(argv, cwd, env=None, timeout=180):
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)


def validate(root, output, phase):
    env={**os.environ,'STOCKFLOW_PROJECT':str(root),'PYTHONUTF8':'1'}
    results={}
    for kind in ['external','local']:
        junit=output/f'{phase}-{kind}.xml'
        args=[sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',f'--junitxml={junit}']
        if kind=='external':
            args += [str(REPO/'benchmark/stockflow_contract.py'), '-c',str(output/'external.ini'),
                     '--basetemp',str(output/f'{phase}-pytest')]
        result=run(args,root,env)
        counts=dict(tests=0,failures=0,errors=0,skipped=0)
        if junit.exists():
            for suite in ET.parse(junit).getroot().iter('testsuite'):
                for key in counts: counts[key]+=int(suite.get(key,0))
        results[kind]=dict(exit_code=result.returncode,**counts,
            passed=result.returncode==0 and counts['tests']>= (30 if kind=='external' else 20)
                   and not any(counts[k] for k in ['failures','errors','skipped']),
            output=(result.stdout+result.stderr)[-24000:])
    modules=list((root/'stockflow').rglob('*.py'))
    results['structure']=dict(modules=len(modules),python_lines=sum(len(p.read_text('utf-8').splitlines()) for p in modules),
        passed=len([p for p in modules if len(p.read_text('utf-8').splitlines())>10])>=8
            and all((root/p).is_file() for p in ['README.md','requirements.txt','pyproject.toml','.gitignore']))
    return results


async def main(args,key):
    root=Path(args.project).resolve()
    contract=(REPO/'benchmark/stockflow_requirements.md').read_text('utf-8')
    if not args.resume:
        root.mkdir(parents=True,exist_ok=False)
        (root/'SPEC.md').write_text(contract,encoding='utf-8')
        (root/'AGENTS.md').write_text('Build the product specified in SPEC.md. Preserve SPEC.md and AGENTS.md. '
            'Use only preinstalled dependencies. Only approved shell: python -B -m pytest -q -p no:cacheprovider. '
            'Use file tools for changes; no deployment, installations, network or git commands. '
            'Read SPEC.md first. Own tests belong in tests/. Do not write into output/.\n',encoding='utf-8')
        (root/'.gitignore').write_text('.eca/\n.env\n__pycache__/\n.pytest_cache/\noutput/\n*.sqlite*\n',encoding='utf-8')
        result=run(['git','init','-q'],root)
        if result.returncode: raise RuntimeError('Git initialization failed')
    output=REPO/'output'/'stockflow'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output.mkdir(parents=True)
    (output/'external.ini').write_text('[pytest]\n',encoding='utf-8')
    protected={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['SPEC.md','AGENTS.md']}
    settings=Settings(root,model='deepseek-flash',base_url='https://api.deepseek.com/v1',api_key=key,
        permission='accept-edits',project_memory=False,max_turns=80,context_chars=args.context_chars,max_output_tokens=16384,
        request_timeout=180,subagent_max_turns=24,subagent_timeout=600,subagent_max_calls=6,
        pricing={'deepseek-flash':args.rates} if args.rates else {})
    settings.validate()
    async def approve(message,detail):
        return message.startswith('Run shell') and detail.strip()=='python -B -m pytest -q -p no:cacheprovider'
    async def ask(_): return 'Use SPEC.md as the complete contract and make routine engineering choices yourself.'
    def emit(event,data):
        if event=='tool': print('tool: '+data['name'],flush=True)
        elif event=='turn': print('turn: '+str(data),flush=True)
        elif event=='notice': print('notice: '+str(data).replace(key,'[REDACTED]')[:400],flush=True)
    store=Store(root)
    state=store.load('latest') if args.resume else store.create()
    agent=Agent(settings,store,state,approve,ask,emit)
    report=dict(project=str(root),model=settings.model,context_chars=settings.context_chars,resumed=args.resume,session_id=state['id'],
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        baseline=run(['git','rev-parse','HEAD'],REPO).stdout.strip(),
        contract_sha256=hashlib.sha256((REPO/'benchmark/stockflow_contract.py').read_bytes()).hexdigest(),phases=[])
    prompt='Implement the complete StockFlow project described in SPEC.md. Read it and build all modules, tests and documentation. Run tests and fix failures before finishing.'
    if args.resume: prompt=('Continue StockFlow from its current files and SPEC.md. Finish pending work and verify. '
        'Do not reread the entire source tree: services and main factory are already implemented. '
        'Prioritize creating tests and running them NOW, then fix concrete failures. Finish README and packaging. '
        'Use pytest failures to guide targeted reads, not another architecture review.')
    started=time.monotonic()
    try:
        for phase in range(1,4):
            error=None
            try: await asyncio.wait_for(agent.run(prompt),2400)
            except Exception as exc: error=type(exc).__name__
            checks=await asyncio.to_thread(validate,root,output,phase)
            checks['protected_files']=dict(passed=all((root/p).is_file() and hashlib.sha256((root/p).read_bytes()).hexdigest()==digest for p,digest in protected.items()))
            entry=dict(phase=phase,status=state['status'],error_type=error,checks=checks,usage=agent.ledger.summary(state))
            report['phases'].append(entry)
            report.update(elapsed_seconds=round(time.monotonic()-started,2),usage=entry['usage'])
            report['passed']=state['status']=='idle' and error is None and all(c['passed'] for c in checks.values())
            (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(dict(phase=phase,status=state['status'],passed=report['passed'],
                checks={k:{a:b for a,b in v.items() if a!='output'} for k,v in checks.items()})),flush=True)
            if report['passed']: break
            prompt='External acceptance found issues. Fix the implementation, add regression tests, and rerun local tests. Preserve SPEC.md and AGENTS.md.\n'+json.dumps(checks,ensure_ascii=False)
        print('Report: '+str(output/'report.json'),flush=True)
    finally:
        report.update(status=state['status'],usage=agent.ledger.summary(state),elapsed_seconds=round(time.monotonic()-started,2))
        report.setdefault('passed',False)
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        await agent.close()
        store.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',default='G:/Projects/eca-stockflow')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--context-chars',type=int,default=400000,help='Character budget for this larger project, not a token count')
    p.add_argument('--rates',type=json.loads,help='Explicit per-million input/output/cache_read/currency snapshot; default unknown')
    args=p.parse_args()
    key=os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('DeepSeek credential: ')
    if not key: p.error('Credential required')
    asyncio.run(main(args,key))
