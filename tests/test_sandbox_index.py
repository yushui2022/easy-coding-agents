import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from eca.config import Settings
from eca.tools import Tools
from eca.sandbox import argv, run, snapshot
from eca.code_index import CodeIndex
from test_runtime import yes, no


def output(stdout='', code=0, **extra):
    return json.dumps(dict(stdout=stdout, stderr='', exit_code=code, timed_out=False, **extra))


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name).resolve()
        self.settings = Settings(self.root, sandbox='docker')
        self.tools = Tools(self.settings, {}, yes, yes, lambda *_: None)

    async def asyncTearDown(self):
        await self.tools.close()
        self.tmp.cleanup()

    async def test_no_backend_never_falls_back(self):
        with patch('eca.sandbox.shutil.which', return_value=None), patch('eca.tools.run_process', AsyncMock()) as process:
            result = await self.tools.execute('shell', {'command': 'echo hello'})
        self.assertIn('refusing host execution', result)
        process.assert_not_awaited()

    async def test_engine_and_remote_failure_no_command_dispatch(self):
        for values in ([output('tcp://remote:2375')], [output('unix:///socket'), output('', 1)]):
            runner = AsyncMock(side_effect=values)
            with patch('eca.sandbox.shutil.which', return_value='docker'), self.assertRaises(ValueError):
                await run(self.tools, 'echo hello', 1, runner)
            self.assertFalse(any('run' in c.args[0] for c in runner.call_args_list))

    async def test_flags_snapshot_and_cleanup(self):
        (self.root / 'code.py').write_text('print(1)')
        (self.root / '.env').write_text('secret')
        runner = AsyncMock(side_effect=[output('unix:///socket'), output('linux'), output('1'), output()])
        with patch('eca.sandbox.shutil.which', return_value='docker'):
            result = json.loads(await run(self.tools, 'python code.py', 2, runner))
        args = runner.call_args_list[2].args[0]
        for flag in ('--network=none', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                     '--user=65534:65534', '--pull=never', '--pids-limit=128', '--memory=512m'):
            self.assertIn(flag, args)
        self.assertEqual(args[-1], 'python code.py')
        self.assertEqual(result['sandbox']['writes'], 'discarded')
        self.assertIn('rm', runner.call_args_list[-1].args[0])
        self.assertEqual(list((self.root / '.eca' / 'sandbox').iterdir()), [])

    async def test_cancel_removes_container_without_replay(self):
        runner = AsyncMock(side_effect=[output('unix:///socket'), output('linux'), asyncio.CancelledError(), output()])
        with patch('eca.sandbox.shutil.which', return_value='docker'), self.assertRaises(asyncio.CancelledError):
            await run(self.tools, 'sleep 100', 2, runner)
        self.assertEqual(sum('run' in c.args[0] for c in runner.call_args_list), 1)
        self.assertIn('rm', runner.call_args_list[-1].args[0])

    async def test_cleanup_failure_cannot_report_success(self):
        runner = AsyncMock(side_effect=[output('unix:///socket'), output('linux'), output('ok'), output('', 1)])
        with patch('eca.sandbox.shutil.which', return_value='docker'), self.assertRaisesRegex(RuntimeError, 'cleanup unconfirmed'):
            await run(self.tools, 'echo ok', 2, runner)

    async def test_container_watchdog_is_not_repairable_failure(self):
        runner = AsyncMock(side_effect=[output('unix:///socket'), output('linux'), output('', 124), output()])
        with patch('eca.sandbox.shutil.which', return_value='docker'):
            result = json.loads(await run(self.tools, 'sleep 100', 2, runner))
        self.assertTrue(result['timed_out'])
        args = runner.call_args_list[2].args[0]
        self.assertIn('timeout -k 5 2', args[-3])

    async def test_policy_denies_host_extensions_and_unapproved_shell(self):
        for name in ('lsp', 'mcp_call', 'mcp_resources'):
            self.assertIn('Denied', await self.tools.execute(name, {}))
        self.tools.approve = no
        with patch('eca.sandbox.run', AsyncMock()) as sandbox:
            self.assertIn('Denied', await self.tools.execute('shell', {'command': 'echo hi'}))
            sandbox.assert_not_awaited()

    async def test_resume_preserves_explicit_docker_mode(self):
        from eca.cli import App, parser
        first = App(self.settings, parser().parse_args([]))
        await first.close()
        second = App(Settings(self.root), parser().parse_args(['--resume', 'latest']))
        try:
            self.assertEqual(second.agent.settings.sandbox, 'docker')
        finally:
            await second.close()

    async def test_index_tool_mode_policy(self):
        (self.root / 'sample.py').write_text('def invoice(): pass')
        self.settings.mode = 'plan'
        result = json.loads(await self.tools.execute('code_search', {'query': 'invoice'}))
        self.assertEqual(result['results'][0]['path'], 'sample.py')
        self.settings.mode = 'chat'
        self.assertIn('Denied', await self.tools.execute('repo_map', {}))

    def test_snapshot_excludes_secret_paths_and_known_key(self):
        for name in ('.env', '.npmrc', 'private.key'):
            (self.root / name).write_text('secret')
        (self.root / 'main.py').write_text('safe')
        dest = self.root / '.eca' / 'copy'
        dest.mkdir(parents=True)
        snapshot(self.tools, dest)
        self.assertEqual([p.name for p in dest.iterdir()], ['main.py'])
        self.settings.api_key = 'secret-credential'
        (self.root / 'main.py').write_text('secret-credential')
        with self.assertRaisesRegex(ValueError, 'credential'):
            snapshot(self.tools, dest)

    def test_config_and_command_injection_boundaries(self):
        for value in ('--privileged', 'image with spaces', 'x;evil'):
            self.settings.sandbox_image = value
            with self.assertRaises(ValueError):
                self.settings.validate()
        command = 'echo "$HOME"; touch /outside'
        args = argv('docker', 'eca-test', self.root, 'trusted:tag', command)
        self.assertEqual(args[-1], command)
        self.assertNotIn('--privileged', args)


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name).resolve()
        self.tools = Tools(Settings(self.root), {}, yes, yes, lambda *_: None)
        self.index = CodeIndex(self.tools)

    def tearDown(self):
        self.tmp.cleanup()

    def query(self, *args, **kwargs):
        return json.loads(self.index.query(*args, **kwargs))

    def test_incremental_change_delete_and_symbols(self):
        path = self.root / 'orders.py'
        path.write_text('import sqlite3\nclass Order:\n    def submit(self):\n        return 42\n')
        first = self.query('submit')
        self.assertEqual(first['results'][0]['matches'][0]['line'], 3)
        self.assertEqual(first['index']['updated'], 1)
        self.assertEqual(self.query('submit')['index']['updated'], 0)
        outline = self.query('Order', outline=True)['results'][0]
        self.assertEqual(outline['imports'], ['sqlite3'])
        self.assertTrue(any(s['name'] == 'submit' for s in outline['symbols']))
        path.write_text('def cancel():\n    return 1\n')
        self.assertEqual(self.query('submit')['results'], [])
        self.assertTrue(self.query('cancel')['results'])
        path.unlink()
        self.assertEqual(self.query('cancel')['results'], [])

    def test_git_ignored_files_are_removed(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)
        (self.root / 'hidden.py').write_text('unique_keyword=1')
        self.assertTrue(self.query('unique_keyword')['results'])
        (self.root / '.gitignore').write_text('hidden.py\n')
        self.assertEqual(self.query('unique_keyword')['results'], [])

    def test_secrets_binary_and_new_credential_scope(self):
        (self.root / '.env').write_text('unique_password=1')
        (self.root / 'binary').write_bytes(b'\x00unique_password')
        (self.root / 'config.py').write_text('unique_password=1')
        self.assertEqual(len(self.query('unique_password')['results']), 1)
        self.tools.settings.api_key = 'unique_password'
        self.assertEqual(self.query('unique_password')['results'], [])

    def test_large_fixture_bounded_results_and_reuse(self):
        for i in range(3000):
            (self.root / f'unit_{i}.py').write_text(f'def service_{i}():\n    return "billing"\n')
        first = self.query('billing', limit=5)
        self.assertEqual(first['index']['files'], 3000)
        self.assertEqual(len(first['results']), 5)
        self.assertFalse(first['index']['partial'])
        second = self.query('service_1499')
        self.assertEqual(second['index']['updated'], 0)
        self.assertEqual(second['results'][0]['path'], 'unit_1499.py')
        from eca.knowledge import Knowledge
        memory = Knowledge(self.tools.settings, self.tools.files, self.tools.path)
        try:
            self.assertIsNotNone(memory.fingerprint())
        finally:
            memory.close()

    def test_fts_syntax_is_data_and_filename_search(self):
        (self.root / 'payments.py').write_text('def invoice(): pass')
        self.assertTrue(self.query('payments')['results'])
        self.assertIsInstance(self.query('" OR NOT : * invoice')['results'], list)
        with self.assertRaises(ValueError):
            self.query('invoice', limit=100)


@unittest.skipUnless(os.environ.get('ECA_SANDBOX_TEST_IMAGE'), 'Opt in with a trusted local Linux image; requires running Docker')
class DockerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    setUp = BoundaryTests.setUp
    asyncTearDown = BoundaryTests.asyncTearDown
    async def test_real_container_boundary(self):
        self.settings.sandbox_image = os.environ['ECA_SANDBOX_TEST_IMAGE']
        (self.root / '.env').write_text('PRIVATE_TOKEN=hidden')
        (self.root / 'source.txt').write_text('original')
        (self.root / 'probe.py').write_text(
            "from pathlib import Path\n"
            "routes=Path('/proc/net/route').read_text().splitlines()[1:]\n"
            "assert not any(r.split()[1]=='00000000' for r in routes)\n"
            "status=Path('/proc/self/status').read_text()\n"
            "assert int(next(l.split()[1] for l in status.splitlines() if l.startswith('CapEff:')),16)==0\n")
        command = ('test ! -e /input/.env && test ! -e /var/run/docker.sock && '
                   'test "$(id -u)" = 65534 && test -z "$ECA_API_KEY" && '
                   '! touch /root/escape && ! touch /input/escape && '
                   'echo changed > source.txt && python probe.py && echo isolated')
        result = json.loads(await self.tools.execute('shell', {'command': command, 'timeout': 30}))
        self.assertEqual(result['exit_code'], 0, result)
        self.assertIn('isolated', result['stdout'])
        self.assertEqual((self.root / 'source.txt').read_text(), 'original')
