import os
import tempfile
import unittest
from pathlib import Path

from eca.agent import Agent
from eca.config import Settings
from eca.store import Store
from eca.tools import Tools, allowed


async def yes(*_):
    return True


class FakeProvider:
    def __init__(self, responses=()):
        self.responses = iter(responses)

    async def complete(self, messages, tools, emit):
        return next(self.responses), {}

    async def close(self):
        pass


class RecordingProvider:
    """Keeps every message list it is handed, so guidance can be inspected."""

    def __init__(self, replies=()):
        self.replies = list(replies)
        self.seen = []

    async def complete(self, messages, tools, emit):
        self.seen.append(list(messages))
        reply = self.replies.pop(0) if self.replies else {'role': 'assistant', 'content': 'done'}
        return reply, {}

    async def close(self):
        pass


class ResearchMode(unittest.IsolatedAsyncioTestCase):
    """Research mode reads the project and the web, and never writes."""

    def setUp(self):
        base = Path(os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.tmp.name).resolve()
        self.settings = Settings(self.root, mode='research', auto_compact=False, project_memory=False)
        self.store = Store(self.root)
        self.state = self.store.create()
        self.notices = []
        self.asked = []

        async def approve(message, detail):
            self.asked.append(detail)
            return False

        self.tools = Tools(self.settings, self.state, approve, approve,
                           lambda event, data: self.notices.append((event, data)))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_the_tool_set_is_read_only(self):
        names = allowed('research')
        for name in ('web_fetch', 'web_search', 'read', 'grep', 'glob'):
            self.assertIn(name, names)
        for name in ('write', 'edit', 'edit_many', 'shell', 'delete'):
            self.assertNotIn(name, names)

    async def test_approve_web_accepts_a_call_without_a_detail(self):
        # Keyless search passes only a message; a required `detail` used to raise
        # TypeError deep inside the tool and surface as "Tool failed".
        self.assertIs(await self.tools.approve_web('Search the web?'), True)

    async def test_network_reads_are_pre_approved_by_the_mode(self):
        self.assertIs(await self.tools.approve_web('fetch?', 'https://example.com'), True)
        self.assertIs(await self.tools.approve_web('fetch?', 'https://example.org'), True)
        self.assertEqual(self.asked, [], 'research mode must not interrupt each page')
        notices = [data for event, data in self.notices if event == 'notice']
        self.assertEqual(len(notices), 1, 'say once, not per page')
        self.assertIn('网络调研', notices[0])

    async def test_other_modes_still_ask(self):
        self.tools.settings = Settings(self.root, mode='code', auto_compact=False, project_memory=False)
        self.assertIs(await self.tools.approve_web('fetch?', 'https://example.com'), False)
        self.assertEqual(self.asked, ['https://example.com'])
        self.assertEqual([data for event, data in self.notices if event == 'notice'], [])

    async def test_first_messages_of_a_run_ask_for_a_search_first(self):
        provider = RecordingProvider()
        agent = Agent(Settings(self.root, mode='research', auto_compact=False, project_memory=False, max_turns=3),
                      self.store, self.store.create(), yes, yes, lambda *_: None, provider)
        await agent.run('what is this thing')
        self.assertTrue(provider.seen, 'the run never reached the model')
        first = repr(provider.seen[0])
        self.assertIn('make your first action one web search', first)

    async def test_other_modes_get_no_such_instruction(self):
        provider = RecordingProvider()
        agent = Agent(Settings(self.root, mode='code', auto_compact=False, project_memory=False, max_turns=3),
                      self.store, self.store.create(), yes, yes, lambda *_: None, provider)
        await agent.run('hello')
        self.assertTrue(provider.seen)
        self.assertNotIn('make your first action one web search', repr(provider.seen[0]))

    def test_prompt_demands_several_sources(self):
        agent = Agent(Settings(self.root, mode='research', auto_compact=False, project_memory=False),
                      self.store, self.store.create(), yes, yes, lambda *_: None, FakeProvider([]))
        prompt = agent.system_prompt()
        self.assertIn('Research mode', prompt)
        self.assertIn('three or more separate sources', prompt)
        self.assertIn('cannot modify files', prompt)
        # Orientation comes first: find out what the thing actually is.
        self.assertIn('start with one web search that answers what the thing is', prompt)
        self.assertIn('Do not answer from memory', prompt)
        self.assertLess(prompt.index('start with one web search'), prompt.index('three or more separate sources'))

    def test_code_mode_keeps_its_own_prompt(self):
        agent = Agent(Settings(self.root, mode='code', auto_compact=False, project_memory=False),
                      self.store, self.store.create(), yes, yes, lambda *_: None, FakeProvider([]))
        self.assertNotIn('Research mode', agent.system_prompt())


if __name__ == '__main__':
    unittest.main()
