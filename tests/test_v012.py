import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from eca.code_index import CodeIndex, IndexCancelled
from eca.config import Settings
from eca.tools import Tools
from eca.sandbox import run
from eca.store import Store
from test_runtime import yes
from test_sandbox_index import output


class UpgradeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.tmp.name).resolve()
        self.tools = Tools(Settings(self.root), {}, yes, yes, lambda *_: None)

    async def asyncTearDown(self):
        await self.tools.close()
        self.tmp.cleanup()

    def test_definition_ranks_first_and_old_cache_migrates(self):
        (self.root / 'a.py').write_text('# Target\n' * 80)
        target = self.root / 'z.py'
        target.write_text('class Target:\n    pass\n')
        index = CodeIndex(self.tools)
        index.query('Target')
        with closing(sqlite3.connect(self.root / '.eca/code-index.sqlite3')) as db:
            db.execute('DROP TABLE symbols')
        result = json.loads(index.query('Target', 1))
        self.assertEqual(result['index']['updated'], 0)
        self.assertEqual(result['results'][0]['path'], 'z.py')
        self.assertEqual(result['results'][0]['matched_symbols'][0]['line'], 1)
        target.write_text('class Renamed: pass\n')
        self.assertEqual(json.loads(index.query('Target'))['results'][0]['path'], 'a.py')
        target.unlink()
        index.query('Target')
        with closing(sqlite3.connect(self.root / '.eca/code-index.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM symbols').fetchone()[0], 0)

    def test_cancel_rolls_back_changed_files(self):
        path = self.root / 'main.py'
        path.write_text('class Before: pass\n')
        CodeIndex(self.tools).query('Before')
        path.write_text('class After: pass\n')
        event = Event()
        def sources(_):
            yield path
            event.set()
        with patch('eca.workspaces.source_files', sources), self.assertRaises(IndexCancelled):
            CodeIndex(self.tools, event).query('After')
        with closing(sqlite3.connect(self.root / '.eca/code-index.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT name FROM symbols').fetchone()[0], 'Before')
        self.assertEqual(json.loads(CodeIndex(self.tools).query('After'))['results'][0]['matched_symbols'][0]['name'], 'After')

    async def test_async_cancel_joins_worker(self):
        started, stopped = Event(), Event()
        def query(index, *args):
            started.set()
            try:
                if not index.cancelled.wait(5):
                    raise AssertionError('worker cancellation was not delivered')
                index.check_cancelled()
            finally:
                stopped.set()
        with patch.object(CodeIndex, 'query', query):
            task = asyncio.create_task(self.tools.code_search('Target'))
            self.assertTrue(await asyncio.to_thread(started.wait, 5))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(stopped.is_set())

    async def test_container_identity_persisted_before_dispatch_and_cleanup(self):
        store = Store(self.root)
        try:
            self.tools.state = store.create()
            self.tools.checkpoint = lambda: store.save(self.tools.state)
            async def runner(args, *rest):
                if 'context' in args:
                    return output('unix:///socket')
                if 'info' in args:
                    return output('linux')
                saved = store.peek(self.tools.state['id'])['sandbox_runs'][-1]
                if 'run' in args:
                    self.assertEqual(saved['cleanup'], 'pending')
                    self.assertEqual(saved['container'], args[args.index('--name') + 1])
                    return output('done')
                return output('', 1)
            with patch('eca.sandbox.shutil.which', return_value='docker'), self.assertRaisesRegex(RuntimeError, 'cleanup unconfirmed'):
                await run(self.tools, 'echo ok', 2, runner)
            saved = store.peek(self.tools.state['id'])['sandbox_runs'][-1]
            self.assertEqual(saved['execution'], 'finished')
            self.assertEqual(saved['cleanup'], 'unconfirmed')
            self.assertNotIn('command', saved)
        finally:
            store.close()

    async def test_failed_checkpoint_prevents_dispatch(self):
        from unittest.mock import AsyncMock
        runner = AsyncMock(side_effect=[output('unix:///socket'), output('linux')])
        def fail():
            raise OSError('disk full')
        self.tools.checkpoint = fail
        with patch('eca.sandbox.shutil.which', return_value='docker'), self.assertRaisesRegex(OSError, 'disk full'):
            await run(self.tools, 'echo ok', 2, runner)
        self.assertEqual(runner.await_count, 2)
