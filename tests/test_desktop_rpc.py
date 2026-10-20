import asyncio
import json
import os
from pathlib import Path
from dataclasses import replace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from eca.desktop_rpc import DesktopRPC
from eca.store import Store
from test_runtime import FakeProvider, call


class DesktopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.temp.name)
        (self.root / 'eca.toml').write_text('[agent]\nproject_memory=false\nauto_compact=false\n')
        self.events = []
        self.rpc = DesktopRPC(self.events.append)
        await self.rpc.dispatch('initialize', {'protocol': 1})
        await self.rpc.dispatch('project.open', {'path': str(self.root)})

    async def asyncTearDown(self):
        await self.rpc.close()
        self.temp.cleanup()

    async def wait_input(self):
        async with asyncio.timeout(3):
            while not self.rpc.pending:
                await asyncio.sleep(.01)
        return next(iter(self.rpc.pending.values()))[0]

    async def fake(self, responses):
        await self.rpc.runtime.agent.provider.close()
        self.rpc.runtime.agent.provider = FakeProvider(responses)

    async def test_handshake_and_exclusive_project(self):
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('initialize', {'protocol': 99})
        with self.assertRaises(ValueError):
            Store(self.root)

    async def test_preview_bounds_logs_preserves_source_and_loads_full_message(self):
        state = self.rpc.runtime.agent.state
        arguments = json.dumps({'path': 'large.txt', 'content': '界'*5000})
        result = json.dumps({'exit_code': 2, 'timed_out': False, 'stdout': 'line\n'*2000})
        state['messages'] = [{'role':'user', 'content': str(i)} for i in range(60)] + [
            {'role':'assistant', 'content':'done',
             'tool_calls':[{'id':'big','type':'function','function':{'name':'write','arguments':arguments}}]},
            {'role':'tool','tool_call_id':'big','content':result}]
        preview = await self.rpc.dispatch('snapshot', {'preview':True})
        self.assertEqual(preview['messages'][0]['message_index'], 12)
        self.assertEqual(len(preview['messages'][-1]['content']), 2000)
        self.assertEqual(preview['messages'][-1]['tool_summary']['exit_code'], 2)
        self.assertTrue(preview['messages'][-2]['truncated'])
        self.assertNotIn('private', str(preview))
        self.assertEqual(state['messages'][-2]['tool_calls'][0]['function']['arguments'], arguments)
        full = await self.rpc.dispatch('session.message', {'id':state['id'],'index':61})
        self.assertEqual(full['content'], result)
        self.assertEqual(self.rpc.snapshot()['messages'][-1]['content'], result)
        for index in (True, -1, 62, '1'):
            with self.assertRaises(ValueError):
                await self.rpc.dispatch('session.message', {'id':state['id'],'index':index})
        self.rpc.emit('result', result)
        self.assertTrue(self.rpc.snapshot(preview=True)['events'][-1]['truncated'])
        self.assertEqual(self.rpc.snapshot()['events'][-1]['data'], result)
        reference = preview['messages'][-1]['message_ref']
        self.assertEqual((await self.rpc.dispatch('session.message', {'id':state['id'],'index':61,'message_ref':reference}))['content'], result)
        state['messages'][61]['content'] = 'changed by compaction'
        with self.assertRaisesRegex(ValueError, 'history changed'):
            await self.rpc.dispatch('session.message', {'id':state['id'],'index':61,'message_ref':reference})

    async def test_history_preview_uses_absolute_cursor_and_redacts_all_paths(self):
        state = self.rpc.runtime.agent.state
        self.rpc.secrets.add('fixture-private-secret')
        state['messages'] = [{'role':'assistant','content':f'{i} fixture-private-secret'} for i in range(120)]
        page = await self.rpc.dispatch('session.messages', {'id':state['id'],'before':70,'preview':True})
        self.assertEqual(page['before'], 20)
        self.assertEqual([m['message_index'] for m in page['messages']], list(range(20,70)))
        self.assertNotIn('fixture-private-secret', str(page))
        self.assertIn('[redacted]', str(page))
        single = await self.rpc.dispatch('session.message', {'id':state['id'],'index':20})
        self.assertEqual(single['content'], '20 [redacted]')
        capped = await self.rpc.dispatch('session.messages', {'id':state['id'],'before':999,'preview':True})
        self.assertEqual(capped['messages'][-1]['message_index'],119)
        self.rpc.runtime.agent.store.save(state)
        ident = state['id']
        await self.rpc.dispatch('session.switch', {})
        historical = await self.rpc.dispatch('session.message', {'id':ident,'index':20})
        self.assertEqual(historical, single)

    async def test_tool_execution_retires_saved_stream_without_losing_history(self):
        text = '我会安排三个子任务。'
        self.rpc.emit('text', text)
        cursor = await self.rpc.dispatch('live', {})
        state = self.rpc.runtime.agent.state
        state['messages'].append({'role': 'assistant', 'content': text})
        self.rpc.emit('tool', {'name': 'delegate_parallel', 'args': {}})
        snapshot = await self.rpc.dispatch('snapshot', {})
        self.assertEqual(snapshot['stream'], '')
        self.assertEqual(snapshot['messages'][-1]['content'], text)
        after = await self.rpc.dispatch('live', cursor)
        self.assertEqual(after['stream'], '')
        self.assertNotEqual(after['stream_id'], cursor['stream_id'])

    async def test_stream_delta_unicode_reset_stale_cursor_and_redaction(self):
        self.rpc.emit('text', '你好🌲')
        first = await self.rpc.dispatch('live', {})
        self.rpc.emit('text', '。测试')
        delta = await self.rpc.dispatch('live', first)
        self.assertNotIn('stream', delta)
        self.assertEqual(delta['stream_delta'], '。测试')
        self.assertEqual(first['stream']+delta['stream_delta'], self.rpc.stream)
        self.assertEqual((await self.rpc.dispatch('live', delta))['stream_delta'], '')
        for offset in (True, -1, 999, '1'):
            value = await self.rpc.dispatch('live', {'stream_id':self.rpc.stream_id,'stream_offset':offset})
            self.assertIn('stream', value)
        self.rpc.emit('turn', 2)
        self.rpc.emit('text', 'next')
        reset = await self.rpc.dispatch('live', delta)
        self.assertEqual(reset['stream'], 'next')
        self.assertNotEqual(reset['stream_id'], delta['stream_id'])
        self.rpc.secrets.add('fixture-private-secret')
        self.rpc.emit('text', 'fixture-private-secret')
        protected = await self.rpc.dispatch('live', {'stream_id':self.rpc.stream_id,'stream_offset':10})
        self.assertEqual(protected['stream'], 'next[redacted]')
        self.assertNotEqual(self.rpc.backend_id, DesktopRPC(lambda _:None).backend_id)

    async def test_live_progress_hides_replay_and_avoids_database_reads(self):
        from unittest.mock import patch
        self.rpc.runtime.agent.state['messages'].append({'role': 'assistant', 'content': 'public', 'reasoning_content': 'private thought', 'reasoning_scope': 'scope'})
        self.rpc.emit('request_start', {'id': 'r'})
        self.rpc.emit('model_activity', {'phase': 'thinking', 'reasoning_chars': 42})
        with patch.object(self.rpc.runtime.agent.store, 'list', side_effect=AssertionError('live must not query history')):
            live = await self.rpc.dispatch('live', {})
        self.assertEqual(live['activity']['reasoning_chars'], 42)
        self.assertIn('private thought', str(self.rpc.snapshot()))  # thinking is shown, bounded
        self.assertNotIn('reasoning_scope', str(self.rpc.snapshot()))  # replay scope stays internal
        self.assertNotIn('model_activity', [entry['event'] for entry in self.rpc.events])

    async def test_context_usage_is_a_bounded_estimate_and_exposed_everywhere(self):
        live = await self.rpc.dispatch('live', {})
        usage = live['context']
        self.assertTrue(usage['estimated'])
        self.assertGreater(usage['input_limit'], 0)
        self.assertGreater(usage['estimated_tokens'], 0)
        self.assertLess(usage['ratio'], 1)
        self.assertGreaterEqual(usage['ratio'], 0)
        self.assertFalse(usage['auto_compact'])  # the fixture project disables it
        self.assertEqual(self.rpc.snapshot()['context'], usage)
        # Unchanged state within two seconds reuses the cached estimate.
        self.assertEqual((await self.rpc.dispatch('live', {}))['context'], usage)

    async def test_manual_compaction_guards_and_reports(self):
        with patch.object(self.rpc.runtime.agent, 'compact', AsyncMock()) as compact:
            result = await self.rpc.dispatch('context.compact', {})
        compact.assert_awaited_once()
        self.assertIn('before_tokens', result)
        self.assertIn('context', result)
        self.assertIn('summary_chars', result)
        self.rpc.run_id = 'busy'
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('context.compact', {})

    async def test_live_tool_target_rate_reset_stale_updates_and_approval(self):
        self.rpc.secrets.add('fixture-private-secret')
        self.rpc.emit('request_start', {'id': 'first'})
        self.rpc.emit('model_activity', {'request_id': 'first', 'phase': 'responding', 'tokens_per_second': 20})
        self.rpc.emit('request_end', {'id': 'first', 'usage': {}, 'tokens_per_second': 25})
        self.rpc.emit('tool', {'name': 'read', 'args': {'path': 'fixture-private-secret/a.py', 'content': 'not a subject'}})
        self.rpc.emit('input_requested', {'kind': 'approval'})
        self.rpc.emit('input_closed', {})
        live = await self.rpc.dispatch('live', {})
        self.assertEqual(live['activity']['target'], '[redacted]/a.py')
        self.assertEqual(live['activity']['tool'], 'read')
        self.assertNotIn('tokens_per_second', live['activity'])
        self.rpc.emit('tool', {'name': 'shell', 'args': {'command': 'x'*170+'fixture-private-secret'}})
        self.assertNotIn('fixture-pr', (await self.rpc.dispatch('live', {}))['activity']['target'])
        self.assertEqual(live['last_request']['tokens_per_second'], 25)
        self.rpc.emit('request_start', {'id': 'second'})
        self.rpc.emit('model_activity', {'request_id': 'first', 'phase': 'thinking', 'tokens_per_second': 123})
        live = await self.rpc.dispatch('live', {})
        self.assertEqual(live['activity']['phase'], 'waiting_model')
        self.assertNotIn('target', live['activity'])
        self.assertNotIn('tokens_per_second', live['activity'])

    async def test_edit_policy_resolves_pending_edits_but_not_commands_or_questions(self):
        edit = asyncio.create_task(self.rpc.approve('Write file.txt?', 'diff'))
        entry = await self.wait_input()
        await self.rpc.dispatch('permissions.set', {'mode': 'accept-edits'})
        self.assertTrue(await edit)
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('input.reply', {**entry, 'value': True})
        shell = asyncio.create_task(self.rpc.approve('Run shell command? host', 'echo test'))
        await self.wait_input()
        self.assertFalse(shell.done())
        await self.rpc.dispatch('permissions.set', {'mode': 'full-access'})
        self.assertTrue(await shell)
        question = asyncio.create_task(self.rpc.question('Choose a colour'))
        question_entry = await self.wait_input()
        await self.rpc.dispatch('permissions.set', {'mode': 'full-access'})
        self.assertFalse(question.done())
        await self.rpc.dispatch('input.reply', {**question_entry, 'value': 'blue'})
        self.assertEqual(await question, 'blue')
        await self.rpc.dispatch('permissions.set', {'mode': 'ask'})
        self.assertFalse(self.rpc.auto_approve('Write another.txt?'))

    async def test_full_access_scope_and_file_conflicts(self):
        await self.rpc.dispatch('permissions.set', {'mode': 'full-access'})
        await self.rpc.dispatch('session.switch', {})
        self.assertEqual(self.rpc.snapshot()['approval_mode'], 'full-access')
        tools = self.rpc.runtime.agent.tools
        path = self.root / 'conflict.txt'
        path.write_text('first')
        tools.remember_file(path, b'first')
        path.write_text('user changes')
        with self.assertRaisesRegex(ValueError, 'changed'):
            await tools.change(path, path.read_bytes(), 'agent changes')
        with self.assertRaises(ValueError):
            tools.path('../outside.txt')
        self.assertEqual(path.read_text(), 'user changes')
        await self.rpc.dispatch('project.close', {})
        await self.rpc.dispatch('project.open', {'path': str(self.root)})
        self.assertEqual(self.rpc.snapshot()['approval_mode'], 'ask')

    async def test_approval_write_undo_conflict_and_resume(self):
        await self.fake([call('write', {'path': 'hello.txt', 'content': 'hello'}), {'role': 'assistant', 'content': 'done'}])
        started = await self.rpc.dispatch('task.start', {'prompt': 'write'})
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('task.start', {'prompt': 'duplicate'})
        entry = await self.wait_input()
        self.assertFalse((self.root / 'hello.txt').exists())
        await self.rpc.dispatch('input.reply', {**entry, 'value': True})
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('input.reply', {**entry, 'value': True})
        await self.rpc.finishing
        self.assertEqual((self.root / 'hello.txt').read_text(), 'hello')
        finished = [event['params'] for event in self.events if event.get('params', {}).get('event') == 'run_finished'][-1]
        self.assertEqual(finished['run_id'], started['run_id'])
        self.assertFalse(self.rpc.snapshot()['busy'])
        change = self.rpc.snapshot()['changes'][0]['id']
        (self.root / 'hello.txt').write_text('user edit')
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('changes.undo', {'id': change})
        (self.root / 'hello.txt').write_text('hello')
        await self.rpc.dispatch('changes.undo', {'id': change})
        self.assertFalse((self.root / 'hello.txt').exists())
        await self.rpc.dispatch('session.switch', {})
        await self.rpc.dispatch('session.switch', {'id': started['session_id']})
        self.assertEqual(self.rpc.snapshot()['messages'][-1]['content'], 'done')

    async def test_denied_and_cancel_pending(self):
        await self.fake([call('write', {'path': 'no.txt', 'content': 'no'}), {'role': 'assistant', 'content': 'denied'}])
        await self.rpc.dispatch('task.start', {'prompt': 'write'})
        entry = await self.wait_input()
        await self.rpc.dispatch('input.reply', {**entry, 'value': False})
        await self.rpc.finishing
        self.assertFalse((self.root / 'no.txt').exists())
        await self.fake([call('write', {'path': 'cancel.txt', 'content': 'no'})])
        started = await self.rpc.dispatch('task.start', {'prompt': 'cancel'})
        entry = await self.wait_input()
        await self.rpc.dispatch('task.cancel', {'run_id': started['run_id']})
        await self.rpc.finishing
        self.assertFalse(self.rpc.pending)
        self.assertEqual(self.rpc.snapshot()['status'], 'interrupted')
        self.assertFalse((self.root / 'cancel.txt').exists())
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('input.reply', {**entry, 'value': True})

    async def test_repair_option_reaches_runtime_and_retains_all_check_rounds(self):
        await self.fake([{'role':'assistant','content':'initial'}, {'role':'assistant','content':'repair'}])
        await self.rpc.dispatch('permissions.set', {'mode':'full-access'})
        ok = json.dumps({'exit_code':0,'timed_out':False,'stdout':'2 passed'})
        fail = json.dumps({'exit_code':1,'timed_out':False,'stdout':'assertion failed'})
        with patch('eca.tools.run_process', AsyncMock(side_effect=[ok, fail, ok, ok])) as process:
            await self.rpc.dispatch('task.start', {'prompt':'fix','checks':['pytest','python check.py'],'repair_attempts':1})
            await self.rpc.finishing
        self.assertEqual(process.await_count, 4)
        suite = self.rpc.snapshot()['suite']
        self.assertEqual(suite['status'], 'passed')
        self.assertEqual(suite['repair_budget'], 1)
        self.assertEqual([r['status'] for r in suite['rounds']], ['failed','passed'])
        self.assertEqual(len(self.rpc.runtime.agent.provider.contexts), 2)
        events = [e['params']['data']['status'] for e in self.events
                  if e.get('params',{}).get('event')=='verification_progress']
        self.assertIn('repairing', events)
        await self.rpc.dispatch('session.switch', {'id':self.rpc.runtime.agent.state['id']})
        self.assertEqual(len(self.rpc.snapshot()['suite']['rounds']), 2)

    async def test_invalid_repair_options_fail_without_starting_or_poisoning_session(self):
        await self.fake([])
        for params in ({'checks':'pytest'}, {'checks':None}, {'checks':['pytest'],'repair_attempts':True},
                       {'checks':['pytest'],'repair_attempts':1.5}, {'checks':['pytest'],'repair_attempts':4},
                       {'checks':[],'repair_attempts':1}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                await self.rpc.dispatch('task.start', {'prompt':'work', **params})
            self.assertIsNone(self.rpc.run_id)
            self.assertIsNone(self.rpc.runtime.task)
            self.assertEqual(self.rpc.runtime.agent.state['status'], 'idle')
        self.assertEqual(self.rpc.runtime.agent.provider.contexts, [])

    async def test_denied_check_never_triggers_automatic_repair(self):
        await self.fake([{'role':'assistant','content':'done'}])
        with patch('eca.tools.run_process', AsyncMock()) as process:
            await self.rpc.dispatch('task.start', {'prompt':'work','checks':['pytest'],'repair_attempts':3})
            entry = await self.wait_input()
            await self.rpc.dispatch('input.reply', {**entry,'value':False})
            await self.rpc.finishing
        process.assert_not_awaited()
        self.assertEqual(self.rpc.snapshot()['suite']['stop_reason'], 'unsafe_to_retry')
        self.assertEqual(len(self.rpc.runtime.agent.provider.contexts), 1)

    async def test_cancel_during_repair_stops_provider_and_keeps_first_failure(self):
        entered = asyncio.Event()
        class RepairWait(FakeProvider):
            async def complete(self, *args):
                if self.contexts:
                    entered.set()
                    await asyncio.Event().wait()
                return await super().complete(*args)
        await self.fake([])
        self.rpc.runtime.agent.provider = RepairWait([{'role':'assistant','content':'done'}])
        await self.rpc.dispatch('permissions.set', {'mode':'full-access'})
        fail = json.dumps({'exit_code':1,'timed_out':False,'stdout':'failed'})
        with patch('eca.tools.run_process', AsyncMock(return_value=fail)) as process:
            run = await self.rpc.dispatch('task.start', {'prompt':'work','checks':['pytest'],'repair_attempts':2})
            await asyncio.wait_for(entered.wait(), 5)
            await self.rpc.dispatch('task.cancel', {'run_id':run['run_id']})
            await asyncio.wait_for(self.rpc.finishing, 5)
        process.assert_awaited_once()
        self.assertEqual(self.rpc.snapshot()['suite']['status'], 'interrupted')
        self.assertEqual(self.rpc.snapshot()['suite']['rounds'][0]['status'], 'failed')
        self.assertFalse(self.rpc.pending)

    async def test_question_and_redaction(self):
        self.rpc.secrets.add('private-test-key')
        task = asyncio.create_task(self.rpc.question('Question private-test-key'))
        entry = await self.wait_input()
        await self.rpc.dispatch('input.reply', {**entry, 'value': 'answer'})
        self.assertEqual(await task, 'answer')
        self.assertNotIn('private-test-key', str(self.events))

    async def test_cancel_waiting_provider_and_eof_cleanup(self):
        entered = asyncio.Event()
        class Waiting(FakeProvider):
            async def complete(self, *args):
                entered.set()
                await asyncio.Event().wait()
        await self.fake([])
        self.rpc.runtime.agent.provider = Waiting([])
        await self.rpc.dispatch('task.start', {'prompt': 'wait'})
        await entered.wait()
        await asyncio.wait_for(self.rpc.close(), 2)
        store = Store(self.root)
        try:
            self.assertEqual(store.load('latest')['status'], 'interrupted')
        finally:
            store.close()

    async def test_model_selection_preserves_execution_boundary_and_project_choice(self):
        agent = self.rpc.runtime.agent
        original_model = agent.settings.model
        agent.settings = replace(agent.settings, mode='plan', sandbox='docker', permission='ask')
        agent.state.update(mode='plan', sandbox='docker')
        await self.rpc.dispatch('model.select', {'model': {
            'model': 'desktop-only', 'api_key': 'private-model-key',
            'api_format': 'openai', 'base_url': 'https://example.com/v1'}})
        selected = self.rpc.runtime.agent.settings
        self.assertEqual((selected.mode, selected.sandbox, selected.permission), ('plan', 'docker', 'ask'))
        self.assertEqual(selected.model, 'desktop-only')
        self.assertNotIn('private-model-key', str(self.rpc.snapshot()))
        self.assertNotIn('desktop-only', (self.root / 'eca.toml').read_text())
        await self.rpc.dispatch('session.switch', {})
        self.assertEqual(self.rpc.runtime.agent.settings.model, 'desktop-only')
        await self.rpc.dispatch('model.select', {'model': {}})
        self.assertEqual(self.rpc.runtime.agent.settings.model, original_model)
        await self.rpc.dispatch('session.switch', {})
        self.assertEqual(self.rpc.runtime.agent.settings.model, original_model)

    async def test_desktop_model_overrides_saved_cli_profile_on_session_switch(self):
        (self.root / 'eca.toml').write_text('[agent]\nproject_memory=false\n'
            '[model_profiles.old]\nmodel="old-cli"\nbase_url="https://example.com/v1"\n'
            'api_format="openai"\napi_key_env="TEST_UNUSED_KEY"\n')
        state = self.rpc.runtime.agent.store.create('code')
        state['model_profile'] = 'old'
        self.rpc.runtime.agent.store.save(state)
        await self.rpc.dispatch('model.select', {'model': {'model': 'chosen-desktop',
            'api_key': 'desktop-test-key', 'base_url': 'https://example.com/v1', 'api_format': 'openai'}})
        await self.rpc.dispatch('session.switch', {'id': state['id']})
        self.assertEqual(self.rpc.runtime.agent.settings.model, 'chosen-desktop')
        self.assertNotIn('desktop-test-key', str(self.rpc.snapshot()))

    async def test_model_error_and_existing_cli_session_recovery(self):
        class Failing(FakeProvider):
            async def complete(self, *args):
                raise RuntimeError('Simulated provider error')
        await self.fake([])
        self.rpc.runtime.agent.provider = Failing([])
        await self.rpc.dispatch('task.start', {'prompt': 'fail once'})
        await self.rpc.finishing
        self.assertEqual(self.rpc.snapshot()['status'], 'error')
        self.assertTrue(any(e.get('params', {}).get('event') == 'error' for e in self.events))
        await self.rpc.dispatch('project.close', {})
        # Produce the same on-disk session the CLI leaves on unexpected termination.
        store = Store(self.root)
        try:
            state = store.load('latest')
            state['status'] = 'running'
            state['messages'].append({'role': 'user', 'content': 'Do not automatically replay this task'})
            store.save(state)
        finally:
            store.close()
        reopened = await self.rpc.dispatch('project.open', {'path': str(self.root)})
        self.assertEqual(reopened['status'], 'interrupted')
        self.assertFalse(reopened['busy'])
        self.assertFalse(reopened['pending'])
        self.assertIn('Do not automatically replay', reopened['messages'][-1]['content'])
