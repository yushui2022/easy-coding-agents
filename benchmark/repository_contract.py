"""Dependency-light behavioral contract for the pinned DeerFlow acceptance task.

Load the real message and identity modules; bypass package initializers that
pull in the full Gateway. Repository/store boundaries use AsyncMock.
"""
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock

ROOT = Path.cwd()
for name, relative in [('app', 'backend/app'), ('app.channels', 'backend/app/channels')]:
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT / relative)]
    sys.modules[name] = package

from app.channels.message_bus import InboundMessage
from app.channels import connection_identity


class Contract(unittest.IsolatedAsyncioTestCase):
    def message(self, connected=True):
        return InboundMessage(channel_name='slack', chat_id='chat', user_id='user',
                              text='hi', topic_id='topic', connection_id='conn' if connected else None)

    async def test_public_interface(self):
        self.assertTrue(callable(getattr(connection_identity, 'resolve_thread_id', None)))
        self.assertFalse(hasattr(connection_identity, 'lookup_thread_id'))

    async def test_bound_message_without_repository_never_uses_global_store(self):
        store = AsyncMock()
        result = await connection_identity.resolve_thread_id(self.message(), repo=None, store=store)
        self.assertIsNone(result)
        store.get_thread_id.assert_not_awaited()

    async def test_bound_message_uses_repository(self):
        repo, store = AsyncMock(), AsyncMock()
        repo.get_thread_id.return_value = 'bound-thread'
        self.assertEqual(await connection_identity.resolve_thread_id(self.message(), repo=repo, store=store), 'bound-thread')
        repo.get_thread_id.assert_awaited_once_with('conn', 'chat', 'topic')
        store.get_thread_id.assert_not_awaited()

    async def test_missing_bound_mapping_never_falls_back(self):
        repo, store = AsyncMock(), AsyncMock()
        repo.get_thread_id.return_value = None
        self.assertIsNone(await connection_identity.resolve_thread_id(self.message(), repo=repo, store=store))
        store.get_thread_id.assert_not_awaited()

    async def test_unbound_message_uses_store(self):
        repo, store = AsyncMock(), AsyncMock()
        store.get_thread_id.return_value = 'global-thread'
        self.assertEqual(await connection_identity.resolve_thread_id(self.message(False), repo=repo, store=store), 'global-thread')
        store.get_thread_id.assert_awaited_once_with('slack', 'chat', topic_id='topic')
        repo.get_thread_id.assert_not_awaited()

    async def test_unbound_message_without_store(self):
        self.assertIsNone(await connection_identity.resolve_thread_id(self.message(False), repo=None, store=None))

    async def test_repository_errors_propagate(self):
        repo, store = AsyncMock(), AsyncMock()
        repo.get_thread_id.side_effect = RuntimeError('unavailable')
        with self.assertRaises(RuntimeError):
            await connection_identity.resolve_thread_id(self.message(), repo=repo, store=store)
        store.get_thread_id.assert_not_awaited()


if __name__ == '__main__':
    unittest.main(verbosity=2)
