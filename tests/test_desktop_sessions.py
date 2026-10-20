import asyncio
import os
from pathlib import Path
import tempfile
import unittest

from eca.desktop_sessions import DesktopSessions
from eca.store import Store
from test_runtime import FakeProvider, call


class WaitingProvider:
    def __init__(self, name):
        self.name = name
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False
        self.closed = False

    async def complete(self, messages, tools, emit):
        self.entered.set()
        emit('text', self.name)
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return {'role': 'assistant', 'content': self.name}, {}

    async def close(self):
        self.closed = True


class ConcurrentSessions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.temp.name)
        (self.root/'eca.toml').write_text('[agent]\nproject_memory=false\nauto_compact=false\n')
        self.events = []
        self.hub = DesktopSessions(self.events.append)
        await self.hub.dispatch('initialize', {'protocol': 1})
        self.first = (await self.hub.dispatch('project.open', {'path': str(self.root)}))['session_id']

    async def asyncTearDown(self):
        await self.hub.close()
        self.temp.cleanup()

    async def provider(self, provider):
        worker = self.hub.active
        await worker.runtime.agent.provider.close()
        worker.runtime.agent.provider = provider
        return worker

    async def start_waiting(self, name):
        provider = WaitingProvider(name)
        worker = await self.provider(provider)
        result = await self.hub.dispatch('task.start', {'prompt': name, 'session_id': self.hub.active_id})
        await asyncio.wait_for(provider.entered.wait(), 3)
        return worker, provider, result

    async def test_parallel_switch_stream_cursors_independent_cancel_and_project_lock(self):
        a, pa, ra = await self.start_waiting('session A')
        snap = await self.hub.dispatch('session.switch', {})
        second = snap['session_id']
        b, pb, rb = await self.start_waiting('session B')
        self.assertFalse(pa.cancelled)
        live = await self.hub.dispatch('live', {})
        self.assertEqual(live['running_count'], 2)
        self.assertEqual(live['stream'], 'session B')
        self.assertIs(a.runtime.agent.store, b.runtime.agent.store)
        with self.assertRaisesRegex(ValueError, 'Another ECA'):
            Store(self.root)
        with self.assertRaisesRegex(ValueError, '仍有会话'):
            await self.hub.dispatch('project.close', {})
        with self.assertRaises(ValueError):
            await self.hub.dispatch('task.start', {'prompt': 'duplicate', 'session_id': self.first})
        await self.hub.dispatch('session.switch', {'id': self.first})
        restored = await self.hub.dispatch('live', {'session_id': second, 'stream_id': a.stream_id, 'stream_offset': 4})
        self.assertIn('stream', restored)
        self.assertEqual(restored['stream'], 'session A')
        self.events.clear()
        b.emit('text', ' background')
        self.assertEqual(self.events, [])
        self.assertEqual(a.stream, 'session A')
        self.assertEqual(a.runtime.agent.state['status'], 'running')
        await self.hub.dispatch('task.cancel', {'session_id': second, 'run_id': rb['run_id']})
        await b.finishing
        self.assertTrue(pb.cancelled)
        self.assertFalse(pa.cancelled)
        self.assertTrue((await self.hub.dispatch('live', {}))['any_busy'])
        pa.release.set()
        await a.finishing
        self.assertFalse((await self.hub.dispatch('live', {}))['any_busy'])
        self.assertEqual(a.runtime.agent.state['messages'][-1]['content'], 'session A')
        self.assertNotIn('session B', str(a.runtime.agent.state['messages']))

    async def test_background_approval_reply_scoping_and_file_conflict(self):
        target = self.root/'shared.txt'
        target.write_text('original')
        a = await self.provider(FakeProvider([call('write', {'path': 'shared.txt', 'content': 'from A'}),
                                             {'role': 'assistant', 'content': 'A complete'}]))
        await self.hub.dispatch('task.start', {'prompt': 'A edit'})
        async with asyncio.timeout(3):
            while not a.pending:
                await asyncio.sleep(.01)
        entry = next(iter(a.pending.values()))[0]
        second = (await self.hub.dispatch('session.switch', {}))['session_id']
        b = await self.provider(FakeProvider([call('write', {'path': 'shared.txt', 'content': 'from B'}),
                                             {'role': 'assistant', 'content': 'B complete'}]))
        await self.hub.dispatch('permissions.set', {'mode': 'accept-edits', 'session_id': second})
        await self.hub.dispatch('task.start', {'prompt': 'B edit'})
        await b.finishing
        snapshot = await self.hub.dispatch('snapshot', {})
        self.assertEqual(next(s for s in snapshot['sessions'] if s['id'] == self.first)['pending_count'], 1)
        with self.assertRaises(ValueError):
            await self.hub.dispatch('input.reply', {**entry, 'session_id': second, 'value': True})
        await self.hub.dispatch('input.reply', {**entry, 'value': True})
        await a.finishing
        self.assertEqual(target.read_text(), 'from B')
        self.assertIn('File changed while awaiting approval', str(a.runtime.agent.state['messages']))
        with self.assertRaises(ValueError):
            await self.hub.dispatch('input.reply', {**entry, 'value': True})

    async def test_model_and_permission_are_session_local(self):
        await self.hub.dispatch('permissions.set', {'mode': 'full-access', 'session_id': self.first})
        second = (await self.hub.dispatch('session.switch', {}))['session_id']
        self.assertEqual(self.hub.active.approval_mode, 'ask')
        await self.hub.dispatch('model.select', {'session_id': second,
            'model': {'model': 'session-b-model', 'api_format': 'openai', 'base_url': 'http://127.0.0.1:9/v1'}})
        await self.hub.dispatch('session.switch', {'id': self.first})
        snapshot = await self.hub.dispatch('snapshot', {})
        self.assertNotEqual(snapshot['settings']['model'], 'session-b-model')
        self.assertEqual(snapshot['approval_mode'], 'full-access')
        await self.hub.dispatch('session.switch', {'id': second})
        self.assertEqual((await self.hub.dispatch('snapshot', {}))['settings']['model'], 'session-b-model')

    async def test_eof_cleanup_cancels_all_and_recovery_does_not_replay(self):
        a, pa, _ = await self.start_waiting('A')
        await self.hub.dispatch('session.switch', {})
        b, pb, _ = await self.start_waiting('B')
        await self.hub.dispatch('session.switch', {})
        c, pc, _ = await self.start_waiting('C')
        await self.hub.close()
        self.assertTrue(all(p.cancelled and p.closed for p in (pa, pb, pc)))
        with self.assertRaises(ValueError):
            await self.hub.dispatch('task.start', {'prompt': 'after close'})
        reopened = Store(self.root)
        try:
            self.assertEqual(len(reopened.list(top_level=True)), 3)
            for row in reopened.list(top_level=True):
                self.assertEqual(reopened.load(row[0])['status'], 'interrupted')
        finally:
            reopened.close()

    async def test_sidechat_survives_switch_and_close_cancels_it(self):
        side = await self.hub.dispatch('sidechat.open', {'session_id': self.first})
        entry = self.hub.active.side_chats.entries[side['id']]
        provider = WaitingProvider('side A')
        await entry['agent'].provider.close()
        entry['agent'].provider = provider
        await self.hub.dispatch('sidechat.send', {'id': side['id'], 'session_id': self.first, 'prompt': 'hello'})
        await asyncio.wait_for(provider.entered.wait(), 3)
        await self.hub.dispatch('session.switch', {})
        self.assertTrue((await self.hub.dispatch('live', {}))['any_busy'])
        snapshot = await self.hub.dispatch('sidechat.snapshot', {'id': side['id'], 'session_id': self.first})
        self.assertTrue(snapshot['busy'])
        await self.hub.close()
        self.assertTrue(provider.cancelled)

    async def test_project_cannot_close_during_a_model_update(self):
        entered, release = asyncio.Event(), asyncio.Event()
        provider = self.hub.active.runtime.agent.provider
        original = provider.close
        async def closing():
            entered.set()
            await release.wait()
            await original()
        provider.close = closing
        change = asyncio.create_task(self.hub.dispatch('model.select', {
            'session_id': self.first, 'model': {'model': 'changed'}}))
        await asyncio.wait_for(entered.wait(), 3)
        try:
            with self.assertRaisesRegex(ValueError, '配置仍在更新'):
                await self.hub.dispatch('project.close', {})
        finally:
            release.set()
            await change
        self.assertEqual((await self.hub.dispatch('snapshot', {}))['settings']['model'], 'changed')


if __name__ == '__main__':
    unittest.main()
