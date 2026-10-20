"""Synthetic transcript resembling a long desktop tool sequence; no model calls."""
from pathlib import Path
import asyncio
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eca.config import Settings
from eca.store import Store
from eca.tools import Tools

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
# A model label exercises the composer badge. No request is sent to this endpoint.
(root / 'eca.toml').write_text('[agent]\nproject_memory=false\nmodel="deepseek-flash"\nbase_url="http://127.0.0.1:1/v1"\nthinking_mode="fast"\n', encoding='utf-8')
(root / 'glass-terrarium').mkdir()
store = Store(root)
state = store.create()
state['title'] = '玻璃生态 · 检查页面与运行结果'
state['messages'] = [
    {'role': 'user', 'content': '检查玻璃立方体场景的页面和运行结果，保留已有修改。'},
    {'role': 'assistant', 'content': '先检查场景文件和本地运行环境，再执行页面检查。',
     'reasoning_content': '先看目录结构，再读场景文件；注意保留已有修改。', 'reasoning_scope': 'fixture:deepseek-flash'},
]
tools = Tools(Settings(root), state, None, None, lambda *_: None)
for i in range(8):
    name = 'read' if i in (0, 4) else 'shell'
    if name == 'read':
        image = root / 'glass-terrarium' / ('shot.png' if i == 0 else 'shot2.png')
        image.write_bytes(b'\x89PNG\r\n\x1a\n')
        args = {'path': str(image)}
        output = asyncio.run(tools.execute(name, args))
    else:
        args = {'command': ('node --check glass-terrarium/scene.js' if i == 7 else
            '$base="' + str(root / 'glass-terrarium') + '"\n' +
            'Get-ChildItem -LiteralPath $base\n' +
            'Write-Output "Synthetic fixture; no user files or browser inspected. ' + 'preview ' * 24 + '"')}
        output = json.dumps({'exit_code': 0, 'timed_out': False, 'stdout': 'Synthetic fixture result; not evidence of real scene validation.\n' * 100})
    state['messages'].extend([
        {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': f'call-{i}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]},
        {'role': 'tool', 'tool_call_id': f'call-{i}', 'content': output},
    ])
state['status'] = 'idle'
store.save(state)
store.close()
