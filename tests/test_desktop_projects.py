import asyncio
import os
from pathlib import Path
import tempfile
import unittest

from eca.desktop_projects import DesktopProjects
from eca.store import Store
from test_desktop_sessions import WaitingProvider
from test_runtime import FakeProvider, call


class ConcurrentProjects(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.temp.name)
        self.a, self.b = self.root/'项目 A', self.root/'项目 B'
        for root in (self.a, self.b):
            root.mkdir()
            (root/'eca.toml').write_text('[agent]\nproject_memory=false\nauto_compact=false\n')
        self.events = []
        self.hub = DesktopProjects(self.events.append)
        self.init = await self.hub.dispatch('initialize', {'protocol': 1})
        self.sa = await self.open(self.a)

    async def asyncTearDown(self):
        await self.hub.close()
        self.temp.cleanup()

    async def open(self, root):
        return await self.hub.dispatch('project.open', {'path': str(root)})

    async def provider(self, provider):
        worker = self.hub.active.active
        await worker.runtime.agent.provider.close()
        worker.runtime.agent.provider = provider
        return worker

    async def waiting(self, text):
        provider = WaitingProvider(text)
        worker = await self.provider(provider)
        result = await self.hub.dispatch('task.start', {'prompt': text})
        await asyncio.wait_for(provider.entered.wait(), 3)
        return worker, provider, result

    async def test_projects_run_switch_and_cancel_independently(self):
        a, pa, ra = await self.waiting('A stream')
        sb = await self.open(self.b)
        b, pb, rb = await self.waiting('B stream')
        self.assertIn('concurrent_projects', self.init['capabilities'])
        self.assertNotEqual(a.runtime.agent.store, b.runtime.agent.store)
        snap = await self.hub.dispatch('snapshot', {})
        self.assertEqual(snap['running_count'], 2)
        self.assertEqual(len(snap['projects']), 2)
        for root in (self.a, self.b):
            with self.assertRaisesRegex(ValueError, 'Another ECA'):
                Store(root)
        with self.assertRaises(ValueError):
            await self.hub.dispatch('project.close', {'project_id': self.sa['project_id']})
        await self.open(self.a)
        live = await self.hub.dispatch('live', {'project_id': sb['project_id'],
            'session_id': sb['session_id'], 'stream_id': a.stream_id, 'stream_offset': 3})
        self.assertEqual(live['stream'], 'A stream')
        self.events.clear()
        b.emit('text', 'more B')
        self.assertEqual(self.events, [])
        await self.hub.dispatch('task.cancel', {'project_id': sb['project_id'],
            'session_id': sb['session_id'], 'run_id': rb['run_id']})
        await b.finishing
        self.assertTrue(pb.cancelled)
        self.assertFalse(pa.cancelled)
        await self.hub.dispatch('project.close', {'project_id': sb['project_id']})
        self.assertTrue((await self.hub.dispatch('live', {}))['any_busy'])
        self.assertEqual(self.hub.active_project, self.sa['project_id'])
        reopened = Store(self.b)
        reopened.close()
        pa.release.set()
        await a.finishing

    async def test_failed_open_and_canonical_path_leave_running_project_intact(self):
        a, pa, _ = await self.waiting('still running')
        with self.assertRaises(FileNotFoundError):
            await self.open(self.root/'absent')
        locked = Store(self.b)
        try:
            with self.assertRaisesRegex(ValueError, 'Another ECA'):
                await self.open(self.b)
        finally:
            locked.close()
        self.assertEqual(self.hub.active_project, self.sa['project_id'])
        again = await self.open(self.a/'.')
        self.assertEqual(len(again['projects']), 1)
        self.assertIs(self.hub.active.active, a)
        self.assertFalse(pa.cancelled)

    async def test_approvals_files_and_models_are_project_local(self):
        worker = await self.provider(FakeProvider([call('write', {'path': 'same.txt', 'content': 'from A'}),
            {'role': 'assistant', 'content': 'done'}]))
        await self.hub.dispatch('task.start', {'prompt': 'A'})
        async with asyncio.timeout(3):
            while not worker.pending:
                await asyncio.sleep(.01)
        entry = next(iter(worker.pending.values()))[0]
        sb = await self.open(self.b)
        await self.hub.dispatch('model.select', {'model': {'model': 'B model'}})
        with self.assertRaises(ValueError):
            await self.hub.dispatch('input.reply', {**entry, 'project_id': sb['project_id'], 'value': True})
        await self.hub.dispatch('input.reply', {**entry, 'project_id': self.sa['project_id'], 'value': True})
        await worker.finishing
        self.assertEqual((self.a/'same.txt').read_text(), 'from A')
        self.assertFalse((self.b/'same.txt').exists())
        result = await self.hub.dispatch('session.switch', {'project_id': self.sa['project_id'], 'id': self.sa['session_id']})
        self.assertNotEqual(result['settings']['model'], 'B model')
        await self.open(self.b)
        self.assertEqual((await self.hub.dispatch('snapshot', {}))['settings']['model'], 'B model')

    async def test_copied_session_ids_still_route_by_project(self):
        # Copied repositories may contain identical .eca session identifiers.
        store = Store(self.b)
        try:
            state = dict(self.hub.active.active.runtime.agent.state)
            state['root'] = str(self.b)
            store.save(state)
        finally:
            store.close()
        sb = await self.open(self.b)
        self.assertEqual(sb['session_id'], self.sa['session_id'])
        a = self.hub.projects[self.sa['project_id']].active
        b = self.hub.active.active
        await self.hub.dispatch('model.select', {'project_id': sb['project_id'], 'model': {'model': 'copied-B'}})
        self.assertNotEqual(a.runtime.agent.settings.model, 'copied-B')
        self.assertEqual(b.runtime.agent.settings.model, 'copied-B')

    async def test_eof_cancels_all_projects_and_reopen_does_not_replay(self):
        a, pa, _ = await self.waiting('A')
        await self.open(self.b)
        b, pb, _ = await self.waiting('B')
        await self.hub.close()
        self.assertTrue(all(p.cancelled and p.closed for p in (pa, pb)))
        for root in (self.a, self.b):
            store = Store(root)
            try:
                self.assertEqual(store.load(store.list(top_level=True)[0][0])['status'], 'interrupted')
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
