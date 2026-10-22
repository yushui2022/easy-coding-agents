import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from eca import usercontext
from eca.config import Settings
from eca.desktop_rpc import DesktopRPC


class UserContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.temp.name)
        self.profile = self.root / 'profile.json'
        self.agents = self.root / 'AGENTS.md'

    def tearDown(self):
        self.temp.cleanup()

    def env(self, profile=True, agents=True):
        values = {}
        if profile:
            values['ECA_USER_PROFILE'] = str(self.profile)
        if agents:
            values['ECA_GLOBAL_AGENTS'] = str(self.agents)
        return mock.patch.dict(os.environ, values, clear=False)

    def test_nothing_configured_produces_no_blocks(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(usercontext.blocks(), [])

    def test_profile_and_instructions_become_labelled_blocks(self):
        self.profile.write_text(json.dumps({'name': '小明', 'notes': '偏好中文回答'}), encoding='utf-8')
        self.agents.write_text('始终用中文回答。\n提交信息用英文。', encoding='utf-8')
        with self.env():
            blocks = usercontext.blocks()
        self.assertEqual(len(blocks), 2)
        self.assertIn('prefers to be called 小明', blocks[0])
        self.assertIn('偏好中文回答', blocks[0])
        self.assertIn('Global user instructions for every project', blocks[1])
        self.assertIn('提交信息用英文', blocks[1])

    def test_missing_corrupt_and_linked_files_are_ignored(self):
        with self.env():
            self.assertEqual(usercontext.blocks(), [])
        self.profile.write_text('{not json', encoding='utf-8')
        with self.env():
            self.assertEqual(usercontext.blocks(), [])
        self.profile.unlink()
        target = self.root / 'real.md'
        target.write_text('不该被读到', encoding='utf-8')
        try:
            self.agents.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')
        with self.env():
            self.assertEqual(usercontext.blocks(), [])

    def test_oversized_values_are_truncated(self):
        self.agents.write_text('x' * (usercontext.INSTRUCTIONS_LIMIT + 500), encoding='utf-8')
        self.profile.write_text(json.dumps({'name': 'y' * 200, 'notes': 'n' * 5000}), encoding='utf-8')
        with self.env():
            blocks = usercontext.blocks()
        self.assertLessEqual(len(blocks[1]), len('Global user instructions for every project (set by the user in the desktop):\n') + usercontext.INSTRUCTIONS_LIMIT)
        self.assertNotIn('y' * 81, blocks[0])
        self.assertLess(blocks[0].count('n'), 2100)

    def test_wrong_types_do_not_crash(self):
        self.profile.write_text(json.dumps({'name': 12, 'notes': ['a']}), encoding='utf-8')
        with self.env():
            self.assertEqual(usercontext.blocks(), [])


class PromptInjectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.temp.name)
        (self.root / 'eca.toml').write_text('[agent]\nproject_memory=false\nauto_compact=false\n')
        self.rpc = DesktopRPC(lambda _: None)
        await self.rpc.dispatch('initialize', {'protocol': 1})
        await self.rpc.dispatch('project.open', {'path': str(self.root), 'model': dict(
            model='m', base_url='http://localhost:1234/v1', api_format='openai', api_key='k')})

    async def asyncTearDown(self):
        await self.rpc.close()
        self.temp.cleanup()

    async def test_global_context_reaches_the_system_prompt(self):
        profile = self.root / 'profile.json'
        agents = self.root / 'global.md'
        profile.write_text(json.dumps({'name': '小明', 'notes': '偏好简洁'}), encoding='utf-8')
        agents.write_text('回答前先说结论。', encoding='utf-8')
        with mock.patch.dict(os.environ, {'ECA_USER_PROFILE': str(profile), 'ECA_GLOBAL_AGENTS': str(agents)}):
            prompt = self.rpc.runtime.agent.system_prompt()
        self.assertIn('prefers to be called 小明', prompt)
        self.assertIn('回答前先说结论', prompt)

    async def test_project_guidance_and_global_context_coexist(self):
        (self.root / 'AGENTS.md').write_text('项目规则：先跑测试。', encoding='utf-8')
        agents = self.root / 'global.md'
        agents.write_text('全局规则：用中文。', encoding='utf-8')
        with mock.patch.dict(os.environ, {'ECA_GLOBAL_AGENTS': str(agents)}):
            prompt = self.rpc.runtime.agent.system_prompt()
        self.assertIn('项目规则：先跑测试', prompt)
        self.assertIn('全局规则：用中文', prompt)
        self.assertLess(prompt.index('项目规则'), prompt.index('全局规则'))


if __name__ == '__main__':
    unittest.main()
