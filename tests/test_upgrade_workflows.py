import asyncio
import json
import os
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock

from eca.agent import Agent
from eca.budget import SharedBudget
from eca.config import Settings
from eca.refactor import edits, offset
from eca.skills import Skills
from eca.store import Store
from test_runtime import FakeProvider, yes


def replacement(start, end, text):
    return {'range': {'start': {'line': 0, 'character': start}, 'end': {'line': 0, 'character': end}}, 'newText': text}


class UpgradeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        base = Path(os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.tmp.name).resolve()
        self.store = Store(self.root)
        self.settings = Settings(self.root, project_memory=False)
        self.state = self.store.create()
        self.agent = Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None,
                           provider=FakeProvider([]))

    async def asyncTearDown(self):
        await self.agent.close()
        self.store.close()
        self.tmp.cleanup()

    async def test_skills_precedence_activation_and_permissions(self):
        user = self.root / 'user-skills'
        for folder, body in [(user, 'user body'), (self.root/'.agents'/'skills', 'project body')]:
            path = folder/'review'/'SKILL.md'
            path.parent.mkdir(parents=True)
            path.write_text('---\ndescription: Review changes\n---\n'+body, encoding='utf-8')
        with patch.dict(os.environ, ECS_SKILLS_DIR=str(user)):
            library = Skills(self.root)
            self.assertEqual(library.catalog()['review']['scope'], 'project')
            result = await self.agent.tools.execute('skills', {'name': 'review'})
            self.assertIn('project body', result)
            self.assertIn('project body', self.agent.system_prompt())
            self.settings.mode = 'plan'
            self.assertIn('Denied', await self.agent.tools.execute('shell', {'command': 'echo forbidden'}))
            self.assertIn('project body', await self.agent.tools.execute('skills', {'name': 'review'}))
            with self.assertRaises(ValueError):
                library.load('../review')

    def test_utf16_and_overlapping_edits(self):
        self.assertEqual(offset('😀old\r\n', {'line': 0, 'character': 2}), 1)
        self.assertEqual(edits('😀old\r\n', [replacement(2, 5, 'new')]), '😀new\r\n')
        with self.assertRaises(ValueError):
            offset('😀old', {'line': 0, 'character': 1})
        with self.assertRaises(ValueError):
            edits('old', [replacement(0, 2, 'x'), replacement(1, 3, 'y')])

    def fake_lsp(self):
        for name in ('a.py', 'b.py'):
            (self.root/name).write_text('old = 1\n', encoding='utf-8')
        async def query(server, operation, *args):
            if operation == 'rename':
                result = {'changes': {(self.root/name).as_uri(): [replacement(0, 3, 'new')] for name in ('a.py', 'b.py')}}
            else:
                result = {'status': 'reported', 'items': []}
            return json.dumps({'result': result})
        self.agent.tools.language_servers = SimpleNamespace(query=query, clients={}, close=AsyncMock())

    async def preview(self):
        return json.loads(await self.agent.tools.execute('lsp_rename', {'server': 'test', 'path': 'a.py', 'new_name': 'new'}))['preview_id']

    async def test_rename_preview_apply_diagnostics_and_journal(self):
        self.fake_lsp()
        ident = await self.preview()
        self.assertTrue((self.root/'a.py').read_text().startswith('old'))
        result = json.loads(await self.agent.tools.execute('lsp_apply', {'preview_id': ident}))
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(len(result['diagnostics']), 2)
        self.assertTrue((self.root/'b.py').read_text().startswith('new'))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM file_changes').fetchone()[0], 2)
        self.assertIn('Error', await self.agent.tools.execute('lsp_apply', {'preview_id': ident}))

    async def test_real_stdio_rename_roundtrip(self):
        from test_v08 import LSP_FIXTURE
        source = LSP_FIXTURE.replace("elif method=='shutdown': result=None",
            "elif method=='textDocument/rename':\n  result={'changes':{m['params']['textDocument']['uri']:[{'range':{'start':{'line':0,'character':0},'end':{'line':0,'character':3}},'newText':m['params']['newName']}]}}\n elif method=='shutdown': result=None")
        script = self.root/'server.py'
        script.write_text(source, encoding='utf-8')
        (self.root/'a.py').write_text('old = 1\n')
        self.settings.lsp_servers = {'test': {'command': sys.executable, 'args': ['-B', str(script), 'pull'], 'timeout': 8}}
        ident = await self.preview()
        result = json.loads(await self.agent.tools.execute('lsp_apply', {'preview_id': ident}))
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(result['diagnostics']['a.py']['result']['status'], 'reported')
        self.assertEqual((self.root/'a.py').read_text(), 'new = 1\n')

    async def test_stale_second_file_rejects_entire_rename(self):
        self.fake_lsp()
        ident = await self.preview()
        (self.root/'b.py').write_text('user work\n')
        result = await self.agent.tools.execute('lsp_apply', {'preview_id': ident})
        self.assertIn('changed since', result)
        self.assertTrue((self.root/'a.py').read_text().startswith('old'))

    async def test_approval_race_and_mode_guards(self):
        self.fake_lsp()
        ident = await self.preview()
        async def race(*_):
            (self.root/'b.py').write_text('concurrent work')
            return True
        self.agent.tools.approve = race
        self.assertIn('changed since', await self.agent.tools.execute('lsp_apply', {'preview_id': ident}))
        self.assertTrue((self.root/'a.py').read_text().startswith('old'))
        self.settings.mode = 'plan'
        self.assertIn('Denied', await self.agent.tools.execute('lsp_apply', {'preview_id': ident}))
        self.settings.sandbox = 'docker'
        self.assertIn('Denied', await self.agent.tools.execute('lsp_rename', {'server': 'test', 'path': 'a.py', 'new_name': 'new'}))

    async def test_shared_budget_parallel_and_resume(self):
        root = SharedBudget(self.store, self.state, 2)
        child = self.store.create()
        child['billing_root'] = self.state['id']
        other = SharedBudget(self.store, child, 2)
        async def reserve(budget, ident):
            budget.reserve(ident)
        results = await asyncio.gather(reserve(root, 'a'), reserve(other, 'b'), reserve(root, 'c'), return_exceptions=True)
        self.assertEqual(sum(isinstance(r, ValueError) for r in results), 1)
        resumed = SharedBudget(self.store, self.state, 2)
        self.assertEqual(resumed.status()['remaining'], 0)
        with self.assertRaises(ValueError):
            resumed.reserve('d')

    async def test_budget_stops_provider_and_counts_retries(self):
        self.agent.budget = SharedBudget(self.store, self.state, 2)
        class Retrying:
            async def complete(self, messages, tools, emit):
                for ident in ('one', 'two', 'three'):
                    emit('request_start', {'id': ident})
                    emit('request_end', {'id': ident, 'usage': {}, 'status': 'failed'})
            async def close(self):
                pass
        self.agent.provider = Retrying()
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            await self.agent.model_complete([], [], lambda *_: None)
        self.assertEqual(self.agent.budget.status()['requests'], 2)
        with self.assertRaises(ValueError):
            await self.agent.model_complete([], [], lambda *_: None)

    async def test_acceptance_evidence_and_denied_check(self):
        from eca.acceptance import check, validate_commands
        child = self.store.create()
        with patch.object(self.agent, 'memory', return_value=SimpleNamespace(fingerprint=lambda: 'stable')):
            with patch.object(self.agent.tools, 'execute', AsyncMock(return_value=json.dumps({'exit_code': 0, 'timed_out': False}))):
                result = await check(self.agent, child, ['python -m unittest'])
                self.assertEqual(result['status'], 'passed')
            with patch.object(self.agent.tools, 'execute', AsyncMock(return_value='Denied by user')):
                result = await check(self.agent, child, ['python -m unittest'])
                self.assertEqual(result['status'], 'failed')
            with patch.object(self.agent.tools, 'execute', AsyncMock(side_effect=asyncio.CancelledError)):
                with self.assertRaises(asyncio.CancelledError):
                    await check(self.agent, child, ['python -m unittest'])
                self.assertEqual(child['acceptance']['status'], 'interrupted')
        with self.assertRaises(ValueError):
            validate_commands([''])

    def test_config_shared_limit_load(self):
        (self.root/'eca.toml').write_text('[agent]\nshared_request_limit = 12\n')
        self.assertEqual(Settings.load(self.root).shared_request_limit, 12)
        with self.assertRaises(ValueError):
            Settings(self.root, shared_request_limit=-1).validate()

    async def test_comparison_runner_uses_identical_cases_and_separate_arms(self):
        from benchmark import compare_workers
        calls = []
        async def run(args, key):
            calls.append((args.worker_model, list(args.cases), args.repeats))
            folder = self.root / ('worker' if args.worker_model else 'single')
            folder.mkdir()
            (folder/'report.json').write_text(json.dumps({'summary': {'passed': 1, 'planned': 1}}))
            return folder
        args = SimpleNamespace(worker_model='small', verify=True, api_key_env='EVAL_MAIN_KEY',
                               worker_api_key_env='EVAL_WORKER_KEY', cases=['api'], repeats=2)
        with patch.dict(os.environ, EVAL_MAIN_KEY='fixture', EVAL_WORKER_KEY='fixture'), patch.object(compare_workers, 'main', run):
            output = await compare_workers.compare(args)
        self.assertEqual(calls, [(None, ['api'], 2), ('small', ['api'], 2)])
        self.assertEqual(json.loads(output.read_text())['worker_first']['summary']['passed'], 1)
