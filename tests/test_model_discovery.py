from pathlib import Path
import unittest
import httpx
from eca.config import Settings
from eca.connectivity import list_models


class ModelDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_protocol_headers_catalogue_and_partial(self):
        for protocol in ('openai', 'responses', 'anthropic'):
            def handle(request):
                self.assertEqual(request.method, 'GET')
                self.assertEqual(request.url.path, '/v1/models')
                if protocol == 'anthropic':
                    self.assertEqual(request.headers['x-api-key'], 'secret')
                    self.assertEqual(request.headers['anthropic-version'], '2023-06-01')
                else:
                    self.assertEqual(request.headers['authorization'], 'Bearer secret')
                return httpx.Response(200, json={'data': [{'id': 'b'}, {'id': 'a'}, {'id': 'a'}, {'id': 42}], 'has_more': True})
            result = await list_models(Settings(root=Path.cwd(), api_format=protocol, api_key='secret', base_url='https://example.com/v1'), httpx.MockTransport(handle))
            self.assertEqual(result['models'], ['a', 'b'])
            self.assertTrue(result['partial'])

    async def test_redirect_errors_bad_json_and_large_response(self):
        for response in (httpx.Response(302, headers={'location': 'https://other.example/models'}),
                         httpx.Response(401), httpx.Response(404), httpx.Response(200, text='not JSON'),
                         httpx.Response(200, content=b' ' * (1024*1024+1))):
            calls = []
            def handle(request):
                calls.append(request)
                return response
            result = await list_models(Settings(root=Path.cwd(), api_key='secret'), httpx.MockTransport(handle))
            self.assertEqual(result['status'], 'error')
            self.assertEqual(len(calls), 1)
            self.assertNotIn('secret', str(result))
