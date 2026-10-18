import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import httpx
from eca.cli import async_main, parser
from eca.config import Settings
from eca.connectivity import check_api
from eca.onboarding import configure


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.messages = []

    def setup_project(self, key='', confirmation='y'):
        answers = iter(['openai', 'https://example.invalid/v1', 'test-model', 'ECA_TEST_KEY', confirmation])
        return configure(self.root, ask=lambda _: next(answers), secret=lambda _: key, emit=self.messages.append)

    def test_create_roundtrip_hidden_key_and_preserve_config(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(self.setup_project("synthetic-'key\\value"))
            settings = Settings.load(self.root)
        self.assertEqual(settings.api_key, "synthetic-'key\\value")
        self.assertEqual(settings.model, 'test-model')
        self.assertNotIn(settings.api_key, '\n'.join(self.messages))
        self.assertNotIn(settings.api_key, (self.root/'eca.toml').read_text())
        original = (self.root/'eca.toml').read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.setup_project()
        self.assertEqual((self.root/'eca.toml').read_bytes(), original)
        self.assertIn('.env', (self.root/'.gitignore').read_text())

    def test_cancel_and_existing_env_are_preserved(self):
        self.assertFalse(self.setup_project(confirmation='n'))
        self.assertEqual(list(self.root.iterdir()), [])
        (self.root/'.env').write_text('KEEP=original\n')
        self.setup_project(key='must-not-be-used')
        self.assertEqual((self.root/'.env').read_text(), 'KEEP=original\n')

    def test_tracked_deleted_env_cannot_receive_secret(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)
        (self.root/'.env').write_text('old')
        subprocess.run(['git', 'add', '.env'], cwd=self.root, check=True, capture_output=True)
        (self.root/'.env').unlink()
        with self.assertRaisesRegex(ValueError, 'tracked'):
            self.setup_project(key='synthetic-secret')
        self.assertFalse((self.root/'eca.toml').exists())
        self.assertFalse((self.root/'.env').exists())

    def test_conflicting_actions_fail_before_network(self):
        for argv in (['--check-api'], ['--configure', '--doctor'], ['--doctor', '-p', 'hi']):
            with self.assertRaises(ValueError):
                asyncio.run(async_main(parser().parse_args(argv)))


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_protocols_one_small_request_without_project_content(self):
        for protocol, route, reply in (
            ('openai', '/chat/completions', {'choices': [{'message': {'content': 'OK'}}]}),
            ('responses', '/responses', {'status': 'completed', 'output': []}),
            ('anthropic', '/messages', {'type': 'message', 'content': []}),
        ):
            calls = []
            def handle(request):
                calls.append(request)
                self.assertEqual(request.url.path, '/v1' + route)
                data = json.loads(request.content)
                self.assertNotIn('tools', data)
                self.assertIn('Reply OK.', request.content.decode())
                return httpx.Response(200, json={**reply, 'usage': {'input_tokens': 3, 'output_tokens': 1, 'secret': 'hidden'}})
            result = await check_api(Settings(Path('.'), api_key='synthetic-key', api_format=protocol, base_url='https://fixture.invalid/v1'), httpx.MockTransport(handle))
            self.assertEqual(result['status'], 'ok', result)
            self.assertEqual(len(calls), 1)
            self.assertNotIn('hidden', json.dumps(result))

    async def test_failures_are_redacted_no_redirect_or_retry(self):
        for status in (302, 401, 403, 404, 429, 500):
            calls = []
            def handle(request):
                calls.append(request)
                return httpx.Response(status, headers={'location': 'https://other.invalid'}, text='synthetic-key private diagnostic')
            result = await check_api(Settings(Path('.'), api_key='synthetic-key'), httpx.MockTransport(handle))
            self.assertEqual(result['status'], 'error')
            self.assertEqual(len(calls), 1)
            self.assertNotIn('synthetic-key', json.dumps(result))

    async def test_invalid_large_and_timeout_responses_fail(self):
        for response in (httpx.Response(200, text='not-json'), httpx.Response(200, json={}), httpx.Response(200, text='x'*65537)):
            result = await check_api(Settings(Path('.'), api_key='synthetic-key'), httpx.MockTransport(lambda _: response))
            self.assertEqual(result['status'], 'error')
        def timeout(_):
            raise httpx.ReadTimeout('synthetic-key')
        result = await check_api(Settings(Path('.'), api_key='synthetic-key'), httpx.MockTransport(timeout))
        self.assertIn('timed out', result['message'])
        self.assertNotIn('synthetic-key', json.dumps(result))
        with patch('eca.connectivity.httpx.AsyncClient', side_effect=ImportError('synthetic-key')):
            result = await check_api(Settings(Path('.'), api_key='synthetic-key'))
        self.assertIn('Proxy support', result['message'])
        self.assertNotIn('synthetic-key', json.dumps(result))
