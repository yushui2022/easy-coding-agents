"""The first message must not pay for one-time SDK setup."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eca.config import Settings
from eca.provider import Provider, prepare_imports


def settings_for(root, **overrides):
    base = dict(model='fixture', base_url='http://127.0.0.1:9/v1', api_format='openai',
                api_key='fixture-key', network_retries=0)
    base.update(overrides)
    return Settings(Path(root), **base)


class Warmup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def test_warm_builds_the_client_without_sending_anything(self):
        provider = Provider(settings_for(self.root))
        self.assertIsNone(provider.client)
        client = asyncio.run(provider.warm())
        # Port 9 is closed: building the client must not connect, let alone send.
        self.assertIsNotNone(client)
        self.assertIs(provider.client, client)
        self.assertTrue(provider.prepared)
        again = asyncio.run(provider.warm())
        self.assertIs(again, client, 'a warm provider must reuse its client')

    def test_warm_does_not_replace_an_existing_client(self):
        provider = Provider(settings_for(self.root))
        existing = object()
        provider.client = existing
        self.assertIs(asyncio.run(provider.warm()), existing)

    def test_warm_is_skipped_without_an_api_key(self):
        provider = Provider(settings_for(self.root, api_key=''))
        self.assertIsNone(asyncio.run(provider.warm()))
        self.assertIsNone(provider.client)

    def test_prepare_pulls_the_chat_resource_in(self):
        import sys
        for name in ('openai.resources.chat.completions',):
            sys.modules.pop(name, None)
        provider = Provider(settings_for(self.root))
        provider.prepare()
        self.assertIn('openai.resources.chat.completions', sys.modules)

    def test_prepare_is_idempotent_and_never_raises(self):
        prepare_imports('openai')
        prepare_imports('responses')
        provider = Provider(settings_for(self.root))
        provider.prepare()
        provider.prepare()
        self.assertTrue(provider.prepared)

    def test_a_broken_sdk_import_does_not_break_the_provider(self):
        provider = Provider(settings_for(self.root))
        with patch.dict('sys.modules', {'openai.resources.chat.completions': None}):
            provider.prepare()
        self.assertTrue(provider.prepared)


class RequestReuse(unittest.TestCase):
    def test_complete_uses_the_warmed_client(self):
        """The request path must not construct a second client behind our back."""
        from eca import provider as module
        with tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir())) as tmp:
            instance = module.Provider(settings_for(tmp))
            asyncio.run(instance.warm())
            warmed = instance.client
            built = []
            original = instance._build_client
            instance._build_client = lambda: built.append(1) or original()
            try:
                asyncio.run(instance.complete([{'role': 'user', 'content': 'hi'}], [], lambda *_: None))
            except Exception:
                pass  # Port 9 refuses the connection; we only care about construction.
            self.assertEqual(built, [], 'the warmed client must be reused, not rebuilt')
            self.assertIs(instance.client, warmed)


if __name__ == '__main__':
    unittest.main()
