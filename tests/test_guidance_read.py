import unittest

import test_runtime as fixtures
from test_runtime import FakeProvider, call, yes
from eca.agent import Agent


class GuidanceReadTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.RuntimeTests.setUp
    tearDown = fixtures.RuntimeTests.tearDown

    async def test_full_read_is_acknowledged_only_after_model_observes_result(self):
        (self.root/'AGENTS.md').write_bytes(b'Use concise code.\r\nPreserve tests.\r\n')
        await self.tools.execute('read', {'path':'AGENTS.md'})
        self.assertTrue(self.tools.guidance_pending)
        self.assertFalse(self.tools.guidance_seen)
        self.assertIn('File unchanged', await self.tools.execute('write', {'path':'code.py','content':'pass'}))
        self.tools.guidance_seen.update(self.tools.guidance_pending)
        self.assertIn('Saved', await self.tools.execute('write', {'path':'code.py','content':'pass'}))

    async def test_partial_and_truncated_reads_do_not_acknowledge_rules(self):
        (self.root/'AGENTS.md').write_text('First rule\nSecond rule\n',encoding='utf-8')
        await self.tools.execute('read', {'path':'AGENTS.md','limit':1})
        await self.tools.execute('read', {'path':'AGENTS.md','offset':2})
        self.settings.output_limit=10
        await self.tools.execute('read', {'path':'AGENTS.md'})
        self.assertFalse(self.tools.guidance_pending)

    async def test_changed_rules_and_unread_parent_still_block(self):
        (self.root/'src').mkdir()
        (self.root/'AGENTS.md').write_text('Root rules',encoding='utf-8')
        nested=self.root/'src'/'AGENTS.md'
        nested.write_text('Scoped rules',encoding='utf-8')
        await self.tools.read('src/AGENTS.md')
        self.tools.guidance_seen.update(self.tools.guidance_pending)
        self.assertIn('[AGENTS.md]',await self.tools.write('src/code.py','pass'))
        await self.tools.read('AGENTS.md')
        self.tools.guidance_seen.update(self.tools.guidance_pending)
        nested.write_text('New scoped rules',encoding='utf-8')
        self.assertIn('New scoped rules',await self.tools.write('src/code.py','pass'))

    async def test_agent_read_then_write_does_not_repeat_guidance(self):
        (self.root/'AGENTS.md').write_text('Preserve tests.',encoding='utf-8')
        self.settings.project_memory=False
        provider=FakeProvider([call('read',{'path':'AGENTS.md'},'read'),
            call('write',{'path':'done.py','content':'pass'},'write'),{'role':'assistant','content':'done'}])
        agent=Agent(self.settings,self.store,self.state,yes,yes,lambda *_:None,provider)
        try:
            await agent.run('Create done.py after reading rules')
            self.assertEqual((self.root/'done.py').read_text(),'pass')
            results=[m['content'] for m in self.state['messages'] if m['role']=='tool']
            self.assertFalse(any('File unchanged' in result for result in results))
        finally:
            await agent.close()
