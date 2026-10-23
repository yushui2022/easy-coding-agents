import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from eca.config import Settings
from eca.tools import Tools
from eca import web


class WebTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name)
        self.settings = Settings(self.root)
        self.approve = AsyncMock(return_value=True)
        self.tools = Tools(self.settings, {}, self.approve, self.approve, lambda *_: None)
        self.requests = []

    def tearDown(self):
        self.tmp.cleanup()

    def client(self, handler):
        actual = httpx.AsyncClient
        def create(**kwargs):
            self.assertFalse(kwargs['follow_redirects'])
            self.assertFalse(kwargs['trust_env'])
            def record(request):
                self.requests.append(request)
                return handler(request)
            return actual(transport=httpx.MockTransport(record), **kwargs)
        return patch('eca.web.httpx.AsyncClient', side_effect=create)

    async def test_html_and_pinned_tls_hostname(self):
        with self.client(lambda _: httpx.Response(200, headers={'content-type':'text/html'}, text='<h1>Title</h1><script>SECRET</script><p>Body &amp; text</p>')), patch('eca.web.public_url', AsyncMock(return_value='93.184.215.14')):
            result = await self.tools.execute('web_fetch', {'url':'https://example.com'})
        self.assertIn('Body & text', result)
        self.assertNotIn('SECRET', result)
        self.assertIn('Untrusted', result)
        self.assertEqual(self.requests[0].url.host, '93.184.215.14')
        self.assertEqual(self.requests[0].headers['host'], 'example.com')
        self.assertEqual(self.requests[0].extensions['sni_hostname'], 'example.com')

    async def test_denial_makes_no_request(self):
        self.approve.return_value = False
        with self.client(lambda _: self.fail('network request')):
            self.assertIn('Denied', await self.tools.execute('web_fetch', {'url':'https://example.com'}))

    async def test_redirect_requires_new_approval_and_blocks_private_address(self):
        with self.client(lambda _: httpx.Response(302, headers={'location':'https://127.0.0.1/'})), patch('eca.web.public_url', AsyncMock(side_effect=['93.184.215.14', ValueError('private address')])):
            result = await self.tools.execute('web_fetch', {'url':'https://example.com'})
        self.assertIn('private address', result)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.approve.await_count, 2)

    async def test_dns_rejects_private_and_mixed_answers(self):
        with patch.object(asyncio.get_running_loop(), 'getaddrinfo', AsyncMock(return_value=[(2,1,6,'',('127.0.0.1',443))])):
            with self.assertRaises(ValueError):
                await web.public_url('https://example.com')

    async def test_fake_ip_resolves_public_ip_and_pins_dns_tls(self):
        rows = [(2, 1, 6, '', ('198.18.0.66', 443))]
        payload = {'Status': 0, 'Answer': [{'type': 5, 'data': 'cdn.example.com'},
                                         {'type': 1, 'data': '93.184.215.14'}]}
        with patch.object(asyncio.get_running_loop(), 'getaddrinfo', AsyncMock(return_value=rows)), self.client(lambda _: httpx.Response(200, json=payload)):
            self.assertEqual(await web.public_url('https://example.com'), '93.184.215.14')
        request = self.requests[0]
        self.assertEqual(request.url.host, '1.1.1.1')
        self.assertEqual(request.url.params['name'], 'example.com')
        self.assertEqual(request.headers['host'], 'cloudflare-dns.com')
        self.assertEqual(request.extensions['sni_hostname'], 'cloudflare-dns.com')

    async def test_fake_ip_never_allows_private_mixed_or_literal_targets(self):
        for url, ips in [('https://198.18.0.66', ['198.18.0.66']),
                         ('https://example.com', ['198.18.0.66', '127.0.0.1']),
                         ('https://example.com', ['93.184.215.14', '10.0.0.1'])]:
            rows = [(2, 1, 6, '', (ip, 443)) for ip in ips]
            with patch.object(asyncio.get_running_loop(), 'getaddrinfo', AsyncMock(return_value=rows)), patch('eca.web.resolve_fake_ip', AsyncMock()) as resolver:
                with self.assertRaisesRegex(ValueError, 'non-public'):
                    await web.public_url(url)
                resolver.assert_not_awaited()

    async def test_fake_ip_dns_invalid_results_fail_closed(self):
        for payload in ({'Status': 3}, {'Status': 0, 'Answer': []},
                        {'Status': 0, 'Answer': [{'type': 1, 'data': '127.0.0.1'}]},
                        {'Status': 0, 'Answer': [{'type': 1, 'data': '198.18.0.1'}]}):
            with self.client(lambda _, p=payload: httpx.Response(200, json=p)):
                with self.assertRaisesRegex(ValueError, 'Fake-IP DNS detected'):
                    await web.resolve_fake_ip('example.com')

    async def test_fake_ip_dns_cancellation_propagates(self):
        with patch('eca.web.httpx.AsyncClient', side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await web.resolve_fake_ip('example.com')

    async def test_limits_content_type_and_errors(self):
        for response, expected in [
            (httpx.Response(200, headers={'content-type':'application/pdf'}, content=b'pdf'), 'Unsupported'),
            (httpx.Response(200, headers={'content-type':'text/plain'}, content=b'x'*(web.MAX_BYTES+1)), 'exceeds'),
            (httpx.Response(403, text='private response body'), 'HTTP 403')]:
            with self.client(lambda _, r=response:r), patch('eca.web.public_url', AsyncMock(return_value='93.184.215.14')):
                result = await self.tools.execute('web_fetch', {'url':'https://example.com'})
            self.assertIn(expected, result)
            self.assertNotIn('private response body', result)

    async def test_search_configuration_and_credential_redaction(self):
        # No configuration means the keyless default; patch it so the suite never
        # depends on the public search endpoint being reachable.
        with patch('eca.web.keyless_search', AsyncMock(return_value='keyless results')):
            self.assertIn('keyless results', await self.tools.execute('web_search', {'query': 'python'}))
        self.settings.web = {'search_provider':'brave','search_api_key_env':'ECA_TEST_SEARCH_KEY'}
        payload = {'web':{'results':[{'title':'Docs','url':'https://example.com','description':'test-private-key'}]}}
        with patch.dict(os.environ, {'ECA_TEST_SEARCH_KEY':'test-private-key'}), self.client(lambda _:httpx.Response(200,json=payload)):
            result = await self.tools.execute('web_search', {'query':'python docs'})
        self.assertIn('https://example.com', result)
        self.assertNotIn('test-private-key', result)
        self.assertEqual(self.requests[0].headers['X-Subscription-Token'], 'test-private-key')
        self.assertEqual(self.requests[0].url.params['q'], 'python docs')

    async def test_search_auth_failure_does_not_echo_body_or_retry(self):
        self.settings.web = {'search_provider':'brave'}
        with patch.dict(os.environ, {'BRAVE_SEARCH_API_KEY':'private-key'}), self.client(lambda _:httpx.Response(401,text='private-key')):
            result = await self.tools.execute('web_search', {'query':'test'})
        self.assertIn('401', result)
        self.assertNotIn('private-key', result)
        self.assertEqual(len(self.requests), 1)

    async def test_network_disabled_in_docker_and_isolated_children(self):
        for sandbox, state in [('docker', {}), ('none', {'isolated':True})]:
            self.settings.sandbox = sandbox
            self.tools.state = state
            for name, args in [('web_fetch', {'url':'https://example.com'}), ('web_search', {'query':'x'})]:
                self.assertIn('Denied', await self.tools.execute(name, args))
        self.approve.assert_not_awaited()

    async def test_config_loading_and_secret_literals_rejected(self):
        (self.root/'eca.toml').write_text('[web]\nsearch_provider="brave"\nsearch_api_key_env="SEARCH_KEY"\n')
        self.assertEqual(Settings.load(self.root).web['search_api_key_env'], 'SEARCH_KEY')
        for config in ({'api_key':'secret'}, {'search_provider':'invalid'}, {'search_api_key_env':'bad name'}):
            with self.assertRaises(ValueError):
                Settings(self.root, web=config).validate()

    async def test_invalid_urls(self):
        for url in ['file:///etc/passwd','http://example.com','https://user:password@example.com','https://example.com:8443']:
            self.assertIn('Error:', await self.tools.execute('web_fetch', {'url':url}))

    async def test_compressed_body_is_rejected_before_decoding(self):
        response = httpx.Response(200, headers={'content-encoding':'gzip'}, stream=httpx.ByteStream(b'not-gzip'))
        with self.assertRaisesRegex(ValueError, 'Compressed'):
            await web.read_response(response)

    async def test_network_error_omits_exception_and_cancellation_propagates(self):
        def fail(_):
            raise httpx.ConnectError('credential-in-exception')
        with self.client(fail), patch('eca.web.public_url', AsyncMock(return_value='93.184.215.14')):
            result = await self.tools.execute('web_fetch', {'url':'https://example.com'})
        self.assertIn('failed', result)
        self.assertNotIn('credential-in-exception', result)
        with patch('eca.web.public_url', AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await self.tools.execute('web_fetch', {'url':'https://example.com'})

    async def test_agent_schema_respects_network_mode(self):
        from eca.agent import Agent
        from eca.store import Store
        from test_runtime import FakeProvider, call
        store = Store(self.root)
        provider = FakeProvider([call('web_fetch', {'url':'https://example.com'}), {'role':'assistant','content':'done'}])
        agent = Agent(self.settings, store, store.create(), self.approve, self.approve, lambda *_:None, provider)
        try:
            for mode in ['code','plan']:
                self.settings.mode = mode
                self.assertIn('web_fetch', [s['function']['name'] for s in agent.tool_schemas()])
            self.settings.sandbox = 'docker'
            self.assertNotIn('web_fetch', [s['function']['name'] for s in agent.tool_schemas()])
            self.settings.sandbox = 'none'
            self.settings.mode = 'code'
            self.settings.project_memory = False
            with self.client(lambda _:httpx.Response(200,headers={'content-type':'text/plain'},text='reference')), patch('eca.web.public_url', AsyncMock(return_value='93.184.215.14')):
                await agent.run('Read the reference')
            self.assertTrue(any(m['role']=='tool' and 'reference' in m['content'] for m in agent.state['messages']))
        finally:
            await agent.close()
            store.close()
