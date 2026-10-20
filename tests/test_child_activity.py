import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eca.desktop_rpc import DesktopRPC
from test_runtime import FakeProvider, call

DONE = {'role': 'assistant', 'content': 'Child result'}


class ChildConsoleTests(unittest.TestCase):
    def test_serial_tool_details_and_diff_still_reach_cli_with_redaction(self):
        from io import StringIO
        from types import SimpleNamespace
        from rich.console import Console
        from eca.cli import App
        app = object.__new__(App)
        output = StringIO()
        app.console = Console(file=output, width=100, color_system=None)
        app.args = SimpleNamespace(json=False)
        app.settings = SimpleNamespace(api_key='private-child-key')
        app.streaming = False
        for event, data in [
            ('tool', {'name': 'write', 'args': {'path': 'child.py'}}),
            ('result', 'wrote child.py private-child-key'),
            ('diff', '+print("child")'),
            ('notice', 'child notice'),
        ]:
            app.emit('subagent_progress', {'session': 'child-session', 'child': {'isolated': False},
                                          'event': event, 'data': data})
        rendered = output.getvalue()
        for expected in ('Agent child-se', 'child.py', '+print("child")', 'child notice', '[redacted]'):
            self.assertIn(expected, rendered)
        self.assertNotIn('private-child-key', rendered)


class ChildActivityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.temp.name)
        (self.root / 'eca.toml').write_text('[agent]\nproject_memory=false\nauto_compact=false\n')
        self.events = []
        self.rpc = DesktopRPC(self.events.append)
        await self.rpc.dispatch('initialize', {'protocol': 1})
        await self.rpc.dispatch('project.open', {'path': str(self.root)})
        self.agent = self.rpc.runtime.agent
        await self.agent.provider.close()

    async def asyncTearDown(self):
        await self.rpc.close()
        self.temp.cleanup()

    def view(self, child, **extra):
        return self.rpc.child_views.snapshot({'owner': self.agent.state['id'], 'id': child, **extra})

    async def test_live_serial_origin_and_read_never_repairs_running_state(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class Streaming(FakeProvider):
            async def complete(self, messages, tools, emit):
                emit('text', 'live child output')
                entered.set()
                await release.wait()
                return DONE, {}
        self.agent.provider = FakeProvider([call('delegate', {'task': 'Inspect entry point'}), DONE])
        with patch('eca.agent.Provider', return_value=Streaming([])):
            await self.rpc.dispatch('task.start', {'prompt': 'Delegate inspection'})
            await asyncio.wait_for(entered.wait(), 3)
            child = self.agent.state['children'][0]
            view = self.view(child)
            self.assertEqual(view['stream'], 'live child output')
            self.assertEqual(view['status'], 'running')
            self.assertEqual(view['parent_call_id'], 'call1')
            self.assertEqual(view['parent_message_index'], 1)
            self.assertEqual(view['ordinal'], 1)
            self.assertEqual(self.rpc.stream, '')
            self.assertEqual(self.agent.store.peek(child)['status'], 'running')
            self.assertNotIn('messages', self.view(child, backend_id=view['backend_id'], message_revision=view['message_revision']))
            self.assertEqual(len(self.rpc.snapshot()['sessions']), 1)
            release.set()
            await asyncio.wait_for(self.rpc.finishing, 3)
        final = self.view(child)
        self.assertEqual(final['status'], 'idle')
        self.assertEqual(final['stream'], '')
        self.assertEqual(final['messages'][-1]['content'], 'Child result')
        self.assertTrue(any(m.get('params', {}).get('event') == 'subagent_progress' for m in self.events))
        # Reopen chooses the parent, even if the child was last saved.
        self.agent.store.save(self.agent.store.peek(child))
        owner = self.agent.state['id']
        await self.rpc.dispatch('project.close', {})
        opened = await self.rpc.dispatch('project.open', {'path': str(self.root)})
        self.assertEqual(opened['session_id'], owner)
        self.assertEqual(opened['children'][0]['id'], child)

    async def test_parallel_cancel_updates_queued_and_running_views(self):
        entered = asyncio.Event()
        class Waiting(FakeProvider):
            async def complete(self, *_):
                entered.set()
                await asyncio.Future()
        self.agent.settings.subagent_concurrency = 1
        self.agent.provider = FakeProvider([call('delegate_parallel', {'tasks': [{'task': 'A'}, {'task': 'B'}]}), DONE])
        with patch('eca.agent.Provider', return_value=Waiting([])):
            run = await self.rpc.dispatch('task.start', {'prompt': 'Parallel inspection'})
            await asyncio.wait_for(entered.wait(), 3)
            children = self.rpc.snapshot()['children']
            self.assertEqual([c['status'] for c in children], ['running', 'queued'])
            await self.rpc.dispatch('task.cancel', {'run_id': run['run_id']})
            await asyncio.wait_for(self.rpc.finishing, 3)
        self.assertEqual([self.view(c['id'])['status'] for c in children], ['interrupted', 'interrupted'])
        self.assertEqual([self.agent.store.peek(c['id'])['status'] for c in children], ['interrupted', 'interrupted'])

    async def test_history_paging_redaction_and_owner_scope(self):
        state = self.agent.store.create('plan')
        state.update(parent_id=self.agent.state['id'], title='old child', status='running',
                     messages=[{'role': 'assistant', 'content': 'secret-fixture-' + str(i)} for i in range(123)])
        self.agent.state['children'] = [state['id']]
        self.agent.store.save(state)
        self.rpc.secrets.add('secret-fixture')
        view = self.view(state['id'])
        self.assertEqual(view['status'], 'interrupted')
        self.assertEqual(self.agent.store.peek(state['id'])['status'], 'running')
        self.assertEqual((view['before'], len(view['messages'])), (73, 50))
        self.assertNotIn('secret-fixture', json.dumps(view))
        older = self.view(state['id'], before=view['before'])
        self.assertEqual((older['before'], older['messages'][0]['message_index']), (23, 23))
        with self.assertRaises(ValueError):
            self.view(state['id'], owner='another-owner')
        with self.assertRaises(ValueError):
            self.view(self.agent.state['id'])
        with self.assertRaises(ValueError):
            self.view(state['id'][:8])

    async def test_child_initialization_failure_is_not_left_running(self):
        self.agent.provider = FakeProvider([call('delegate', {'task': 'Inspect'}), DONE])
        with patch('eca.agent.Provider', side_effect=RuntimeError('unavailable')):
            await self.rpc.dispatch('task.start', {'prompt': 'Delegate'})
            await asyncio.wait_for(self.rpc.finishing, 3)
        child = self.agent.state['children'][0]
        self.assertEqual(self.view(child)['status'], 'error')
        self.assertEqual(self.agent.store.peek(child)['status'], 'error')

    async def test_legacy_long_result_recovers_origin_without_changing_storage(self):
        state = self.agent.store.create('plan')
        state.update(parent_id=self.agent.state['id'], title='legacy', status='idle')
        self.agent.store.save(state)
        self.agent.state.update(children=[state['id']], messages=[
            call('delegate', {'task': 'legacy'}, 'old-call'),
            {'role': 'tool', 'tool_call_id': 'old-call',
             'content': json.dumps({'session': state['id'], 'summary': 'x' * 12000})}])
        meta = self.rpc.snapshot(preview=True)['children'][0]
        self.assertEqual((meta['parent_call_id'], meta['parent_message_index']), ('old-call', 0))
        self.assertNotIn('parent_call_id', self.agent.store.peek(state['id']))

    async def test_finished_child_is_renamed_by_the_model(self):
        class Naming(FakeProvider):
            def __init__(self):
                super().__init__([DONE, {'role': 'assistant', 'content': '入口审计'}])
        self.agent.settings.api_key = 'fixture'
        self.agent.provider = FakeProvider([call('delegate', {'task': 'Inspect entry point thoroughly'}), DONE])
        with patch('eca.agent.Provider', return_value=Naming()):
            await self.rpc.dispatch('task.start', {'prompt': 'Delegate inspection'})
            await asyncio.wait_for(self.rpc.finishing, 10)
        child = self.agent.state['children'][0]
        stored = self.agent.store.peek(child)
        self.assertEqual((stored['title'], stored.get('title_source')), ('入口审计', 'model'))
        self.assertEqual(self.view(child)['title'], '入口审计')
