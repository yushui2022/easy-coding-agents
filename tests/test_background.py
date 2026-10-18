import asyncio
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
import urllib.request
from unittest.mock import patch
from types import SimpleNamespace

from eca.config import Settings
from eca.tools import Tools
from eca.cli import App


async def yes(*_):
    return True


class BackgroundTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        base = Path(os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.tmp.name)
        self.settings = Settings(self.root)
        self.tools = Tools(self.settings, {}, yes, yes, lambda *_: None)
        self.counter = 0

    async def asyncTearDown(self):
        await self.tools.close()
        self.tmp.cleanup()

    async def start(self, source, lifetime=20):
        self.counter += 1
        path = self.root / f'job{self.counter}.py'
        path.write_text(source, encoding='utf-8')
        quote = (lambda x: "'" + str(x).replace("'", "''") + "'") if os.name == 'nt' else shlex.quote
        command = ('& ' if os.name == 'nt' else '') + quote(sys.executable) + ' -u ' + quote(str(path))
        result = await self.tools.execute('process_start', {'command': command, 'lifetime': lifetime})
        return json.loads(result)['id']

    async def test_real_http_service_stop_and_port_release(self):
        ident = await self.start("from http.server import HTTPServer, BaseHTTPRequestHandler\n"
            "class Handler(BaseHTTPRequestHandler):\n"
            " def do_GET(self):\n  self.send_response(200)\n  self.end_headers()\n  self.wfile.write(b'background-ok')\n"
            "server = HTTPServer(('127.0.0.1', 0), Handler)\n"
            "print('READY:' + str(server.server_port), flush=True)\nserver.serve_forever()\n")
        ready = json.loads(await self.tools.process_wait(ident, 'READY:', 10))
        self.assertTrue(ready['matched'])
        logs = json.loads(await self.tools.process_logs(ident))
        port = int(logs['stdout'].split('READY:')[1].splitlines()[0])
        url = f'http://127.0.0.1:{port}'
        def fetch():
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url, timeout=2) as response:
                return response.read()
        self.assertEqual(await asyncio.to_thread(fetch), b'background-ok')
        stopped = json.loads(await self.tools.process_stop(ident))
        self.assertEqual(stopped['status'], 'exited')
        self.assertEqual(stopped['stop_reason'], 'requested')
        with self.assertRaises(OSError):
            await asyncio.to_thread(fetch)

    async def test_bounded_logs_exit_code_and_redaction(self):
        self.settings.api_key = 'test-secret-marker'
        ident = await self.start("import sys\nprint('x'*150000)\nprint('test-secret-marker DONE')\nprint('ERR', file=sys.stderr)\nsys.exit(7)\n")
        await asyncio.wait_for(self.tools.background().get(ident)['monitor'], 10)
        self.settings.output_limit = 2000
        raw = await self.tools.execute('process_logs', {'id': ident, 'max_chars': 20000})
        result = json.loads(raw)
        self.assertLessEqual(len(raw), 2000)
        self.assertEqual(result['exit_code'], 7)
        self.assertTrue(result['logs_truncated'])
        self.assertIn('[redacted] DONE', result['stdout'])
        self.assertNotIn('test-secret-marker', raw)
        self.assertIn('ERR', result['stderr'])
        self.assertLessEqual(len(self.tools.background().get(ident)['stdout']), 65536)

    async def test_lifetime_and_normal_close(self):
        ident = await self.start('import time\ntime.sleep(60)', lifetime=2)
        await asyncio.wait_for(self.tools.background().get(ident)['monitor'], 12)
        self.assertEqual(self.tools.background().get(ident)['reason'], 'lifetime_expired')
        ident = await self.start("import time\nprint('READY', flush=True)\ntime.sleep(60)")
        self.assertTrue(json.loads(await self.tools.process_wait(ident, 'READY', 10))['matched'])
        await self.tools.close()
        job = self.tools.background().get(ident)
        self.assertIsNotNone(job['process'].returncode)
        self.assertEqual(job['reason'], 'session_closed')

    async def test_denials_and_validation_do_not_spawn(self):
        with patch('asyncio.create_subprocess_exec') as spawn:
            async def no(*_):
                return False
            self.tools.approve = no
            self.assertIn('Denied', await self.tools.execute('process_start', {'command': 'echo hello'}))
            self.tools.approve = yes
            for mode in ('plan', 'chat'):
                self.settings.mode = mode
                self.assertIn('Denied', await self.tools.execute('process_start', {'command': 'echo hello'}))
            self.settings.mode = 'code'
            self.settings.sandbox = 'docker'
            self.assertIn('Denied', await self.tools.execute('process_start', {'command': 'echo hello'}))
            self.settings.sandbox = 'none'
            self.tools.mcp_disabled = True
            self.assertIn('Denied', await self.tools.execute('process_start', {'command': 'echo hello'}))
            self.tools.mcp_disabled = False
            self.assertIn('Error', await self.tools.execute('process_start', {'command': '', 'lifetime': 0}))
            self.assertIn('Error', await self.tools.execute('process_stop', {'id': str(os.getpid())}))
            spawn.assert_not_called()

    async def test_cli_dispatch_and_explicit_shell_approval(self):
        events = []
        app = SimpleNamespace(agent=SimpleNamespace(tools=self.tools),
                              emit=lambda *args: events.append(args))
        await App.command(app, '/jobs')
        self.assertEqual(json.loads(events[-1][1]), [])
        app.args = SimpleNamespace(prompt='task', allow_shell=True)
        self.assertTrue(await App.approve(app, 'Start background command with host permissions?', 'echo hello'))
        app.args.allow_shell = False
        self.assertFalse(await App.approve(app, 'Start background command with host permissions?', 'echo hello'))
        with self.assertRaises(ValueError):
            await App.command(app, '/run')

    async def test_limit_and_cancel_wait_preserves_job(self):
        with patch('eca.background.MAX_RUNNING', 1):
            ident = await self.start('import time\ntime.sleep(60)')
            result = await self.tools.execute('process_start', {'command': 'echo second'})
            self.assertIn('Error', result)
        waiting = asyncio.create_task(self.tools.process_wait(ident, 'never', 60))
        await asyncio.sleep(.1)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        self.assertIsNone(self.tools.background().get(ident)['process'].returncode)
        result = json.loads(await self.tools.process_wait(ident, 'never', 1))
        self.assertFalse(result['matched'])
        self.assertEqual(result['status'], 'running')


if __name__ == '__main__':
    unittest.main()
