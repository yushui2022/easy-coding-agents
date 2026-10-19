"""Synthetic long session for repeatable desktop responsiveness measurements."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eca.store import Store

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
(root/'eca.toml').write_text('[agent]\nproject_memory=false\nmax_turns=8\n', encoding='utf-8')
(root/'README.md').write_text('Synthetic desktop performance fixture. No user data.\n', encoding='utf-8')
store = Store(root)
state = store.create()
state['title'] = '订单服务 · 修复并发写入与回滚'
for i in range(60):
    state['messages'].extend([
        {'role':'user','content':f'检查第 {i+1} 个模块的失败恢复与并发写入行为。'},
        {'role':'assistant','content':'已定位相关调用方，开始检查。','tool_calls':[
            {'id':f'call-{i}','type':'function','function':{'name':'shell','arguments':json.dumps({'command':f'python -m unittest tests.test_orders_{i}'})}}]},
        {'role':'tool','tool_call_id':f'call-{i}','content':json.dumps({'exit_code':0,'timed_out':False,
            'stdout':('PASS order rollback; batch transaction; concurrent writes; request idempotency.\n'*600)},ensure_ascii=False)},
        {'role':'assistant','content':f'### 第 {i+1} 组检查结果\n\n已运行指定命令，退出码为 0。\n\n'+
            ('- **事务边界**：检查调用方保留既有提交与回滚语义。\n- **下一步**：继续检查错误恢复和集成测试。\n'*15)}])
state['status']='idle'
store.save(state)
store.close()
