const {test}=require('node:test');
const assert=require('node:assert/strict');
const {transformSync}=require('esbuild');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const file=path.resolve(__dirname,'../src/renderer/transcript-model.ts');
const loaded=new Module(file,module);loaded.filename=file;loaded.paths=module.paths;
loaded._compile(transformSync(fs.readFileSync(file,'utf8'),{loader:'ts',format:'cjs'}).code,file);
const {transcriptNodes,resultInfo,relativeTarget,toolTarget,failureHint,visibleEntries}=loaded.exports;
const call=(id,content=null)=>({role:'assistant',content,tool_calls:[{id,function:{name:'shell',arguments:'{"command":"python -m unittest"}'}}]});
const result=(id,content='{"exit_code":0}')=>({role:'tool',tool_call_id:id,content});
test('consecutive calls pair with results in one group; prose and users preserve boundaries',()=>{
  const nodes=transcriptNodes([{role:'user',content:'start'},call('a'),result('a'),call('b'),result('b'),call('c','继续检查'),result('c'),{role:'user',content:'next'},call('d'),result('d')]);
  assert.deepEqual(nodes.map(n=>n.kind),['message','tools','message','tools','message','tools']);
  assert.deepEqual(nodes[1].entries.map(e=>e.call.id),['a','b']);
  assert.equal(nodes[1].entries[1].result.tool_call_id,'b');
});
test('pagination gaps never link tools across missing history; orphan results stay visible',()=>{
  const nodes=transcriptNodes([{...call('a'),message_index:0},{...result('a'),message_index:5}, {...call('b'),message_index:6},{...result('b'),message_index:7}]);
  assert.deepEqual(nodes.map(n=>n.kind),['tools','gap','message','tools']);
  assert.equal(nodes[0].entries[0].result,undefined);assert.equal(nodes[1].count,4);
  assert.equal(nodes[3].entries[0].result.tool_call_id,'b');
});
test('tool ids reused in later turns never replace older results',()=>{
  const nodes=transcriptNodes([call('a'),result('a','old'),{role:'user',content:'next'},call('a'),result('a','new')]);
  assert.equal(nodes[0].entries[0].result.content,'old');assert.equal(nodes[2].entries[0].result.content,'new');
});
test('unknown, denied, interrupted, failed and timed-out outcomes stay distinct',()=>{
  for(const [content,kind] of [['Denied by user.','denied'],['Tool failed: broken','error'],['Stopped: repeated identical tool calls.','stopped'],['Interrupted; verify state','stopped'],['{"exit_code":2}','error'],['{"exit_code":0,"timed_out":true}','error'],['{"isError":true}','error'],['Saved a.txt','returned']])assert.equal(resultInfo({content}).kind,kind);
  assert.equal(resultInfo(undefined).kind,'unknown');assert.equal(resultInfo(undefined,true).kind,'pending');
  assert.equal(resultInfo({content:'truncated',tool_summary:{exit_code:0}}).kind,'returned');
});
test('an interrupted call explains itself in Chinese and read-only ones say nothing changed',()=>{
  const safe=resultInfo({content:'Interrupted: this read-only step was cancelled before it returned, so nothing was changed and retrying it is safe.'});
  assert.equal(safe.kind,'stopped');assert.equal(safe.label,'已中断');
  assert.match(safe.hint,/只读操作不改变任何东西/);
  assert.doesNotMatch(safe.hint,/read-only/,'the model-facing English stays out of the UI');
  const unknown=resultInfo({content:'Interrupted: outcome unknown. Inspect current files/processes before retrying. Do not assume this action failed or succeeded.'});
  assert.equal(unknown.kind,'stopped');assert.match(unknown.hint,/重试前先核对当前文件和进程状态/);
  assert.equal(resultInfo({content:'Stopped: repeated identical tool calls.'}).hint,'Stopped: repeated identical tool calls.');
});
test('collapse keeps failures, denied, unfinished and opened records in original order',()=>{
  const entries=Array.from({length:9},(_,i)=>({key:String(i),call:call(String(i)).tool_calls[0],source:{},result:result(String(i))}));
  entries[0].result=result('0','Error: broken');entries[2].result=result('2','Denied by user');entries[3].result=undefined;
  assert.deepEqual(visibleEntries(entries,false,false).map(e=>e.index),[0,2,3,6,7,8]);
  assert.deepEqual(visibleEntries(entries,false,false,new Set(['1'])).map(e=>e.index),[0,1,2,3,6,7,8]);
  assert.equal(visibleEntries(entries,true,false).length,9);
});
test('paths are abbreviated only within the exact project; raw command remains accessible',()=>{
  assert.equal(relativeTarget('c:\\Work\\My App\\src\\测试.py','C:\\work\\my app'),'src/测试.py');
  assert.equal(relativeTarget('C:\\work\\my application\\a','C:\\work\\my app'),'C:\\work\\my application\\a');
  assert.equal(relativeTarget('C:/work/../secret','C:/work'),'C:/work/../secret');
  assert.equal(relativeTarget('/WORK/file','/work'),'/WORK/file');
  const tool={function:{name:'shell',arguments:JSON.stringify({command:'echo "hello"\npython -V'})}};
  assert.equal(toolTarget(tool).raw,'echo "hello"\npython -V');
  const truncated={function:{arguments:'{"path":"C:\\\\work\\\\a.py","content":"incomplete'}};
  assert.ok(toolTarget(truncated).raw.endsWith('a.py'));
});
test('existing PNG decode failures explain text-tool limitation without claiming image inspection',()=>{
  const entry={call:{function:{name:'read',arguments:'{"path":"shot.png"}'}},result:{content:"Error: 'utf-8' codec can't decode byte 0x89"}};
  assert.match(failureHint(entry),/无法查看图片/);
});
