import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from eca import web


def fake_tools(config=None, approved=True):
    async def approve(message, detail=None):
        return approved
    return SimpleNamespace(settings=SimpleNamespace(web=config or {}, root=Path('.'), ),
                           approve=approve, approve_web=approve)


SAMPLE = '''
<html><body>
<div class="result results_links">
  <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs&amp;rut=abc">Example docs</a>
  <a class="result__snippet" href="#">The   official
      documentation</a>
  <a class="result__a" href="https://plain.example.org/page">Plain result</a>
  <a class="result__snippet" href="#">Second snippet</a>
  <a class="result__a" href="http://insecure.example.com/x">Not https</a>
  <a class="result__a" href="https://localhost/admin">Local host</a>
</div>
</body></html>
'''


class SearchParsing(unittest.TestCase):
    def test_decodes_wrapped_links_and_keeps_titles_and_snippets(self):
        results = web.parse_search_page(SAMPLE, count=5)
        self.assertEqual([item['url'] for item in results],
                         ['https://example.com/docs', 'https://plain.example.org/page'])
        self.assertEqual(results[0]['title'], 'Example docs')
        self.assertEqual(results[0]['snippet'], 'The official documentation')
        self.assertEqual(results[1]['snippet'], 'Second snippet')

    def test_drops_non_https_and_private_destinations(self):
        urls = [item['url'] for item in web.parse_search_page(SAMPLE, count=10)]
        self.assertNotIn('http://insecure.example.com/x', urls)
        self.assertNotIn('https://localhost/admin', urls)

    def test_respects_the_result_count(self):
        self.assertEqual(len(web.parse_search_page(SAMPLE, count=1)), 1)

    def test_a_blocked_or_empty_page_yields_nothing(self):
        self.assertEqual(web.parse_search_page('<html><body>no results</body></html>'), [])


class ProviderChoice(unittest.IsolatedAsyncioTestCase):
    async def test_no_configuration_means_keyless_search(self):
        with patch.object(web, 'keyless_search', AsyncMock(return_value='keyless-ok')) as keyless:
            result = await web.search(fake_tools({}), 'what is this')
        self.assertEqual(result, 'keyless-ok')
        keyless.assert_awaited_once()

    async def test_explicit_brave_without_a_key_explains_the_alternative(self):
        result = await web.search(fake_tools({'search_provider': 'brave'}), 'what is this')
        self.assertIn('duckduckgo', result)
        self.assertIn('web_fetch', result)

    async def test_unknown_provider_is_named(self):
        result = await web.search(fake_tools({'search_provider': 'altavista'}), 'what is this')
        self.assertIn('altavista', result)
        self.assertIn('duckduckgo', result)

    async def test_a_denied_keyless_search_sends_nothing(self):
        tools = fake_tools({}, approved=False)
        result = await web.search(tools, 'what is this')
        self.assertIn('Denied', result)


if __name__ == '__main__':
    unittest.main()
