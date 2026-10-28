"""Scanning mode: breadth quotas and the rejection list are enforced on disk."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from eca import modes, scout, tools
from eca.config import Settings

CATEGORIES = ("制造", "零售", "医疗", "物流", "教育", "农业", "建筑")
CATEGORIES = ("制造", "零售", "医疗", "物流", "教育", "农业", "建筑", "餐饮")

class ScoutCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name)
        self.settings = Settings(self.root)
        self.settings.mode = 'scout'
        self.events = []

        async def approve(*_args, **_kwargs):
            return True

        self.tools = tools.Tools(self.settings, {}, approve, approve,
                                 lambda *event: self.events.append(event[-1]))

    def tearDown(self):
        self.tmp.cleanup()

    async def call(self, tool, **args):
        value = await self.tools.execute(tool, args)
        if isinstance(value, str) and value.startswith('Error: '):
            raise ValueError(value[len('Error: '):])
        return json.loads(value)

    async def doc(self, name, text='正文' * 20):
        return await self.call('scout_doc', name=name, content=text)

    async def source(self, ident):
        return await self.call('scout_source', id=ident, kind='product',
                               url=f'https://example.com/{ident}', title=f'页面 {ident}')

    async def candidate(self, ident, category, **extra):
        await self.source(f'src-{ident}')
        payload = dict(id=ident, name=f'产品 {ident}', company='某中小公司', category=category,
                       what='替门店做一件重复的事', buyer='门店老板', price='¥99/月',
                       replicable='一个人两周能搭出来', effort='weeks', moat='线下关系与话术',
                       risk='平台改规则就断供', why_not_obvious='不是第一反应会想到的那个',
                       sources=[f'src-{ident}'])
        payload.update(extra)
        return await self.call('scout_candidate', **payload)

    async def ready(self):
        await self.doc('criteria.md')
        for index, category in enumerate(CATEGORIES):
            for position in range(3):
                await self.candidate(f'c{index}{position}', category)
        for index in range(5):
            await self.call('scout_exclude', idea=f'惯性想法{index}', why='人人都做，没有差异')
        await self.call('scout_stage', stage='sweep')
        await self.call('scout_stage', stage='screen')
        return await self.call('scout_stage', stage='shortlist')

    async def test_mode_is_readonly_but_carries_the_scan_tools(self):
        self.assertTrue(modes.reading('scout'))
        self.assertFalse(modes.working('scout'))
        allowed = tools.allowed('scout')
        for name in ('scout_stage', 'scout_doc', 'scout_source', 'scout_candidate',
                     'scout_exclude', 'scout_shortlist'):
            self.assertIn(name, allowed)
        for name in ('write', 'edit', 'shell', 'delete'):
            self.assertNotIn(name, allowed)
        self.assertIn('web_search', allowed)

    async def test_sweep_needs_the_criteria_file_first(self):
        await self.call('scout_stage', stage='criteria')
        with self.assertRaises(ValueError) as caught:
            await self.call('scout_stage', stage='sweep')
        self.assertIn('criteria', str(caught.exception))

    async def test_candidate_needs_a_registered_page_and_known_source(self):
        with self.assertRaises(ValueError) as caught:
            await self.call('scout_candidate', id='x1', name='产品', company='公司', category='零售',
                            what='做一件事', buyer='老板', price='¥10', replicable='能', effort='weeks',
                            moat='关系', risk='平台', why_not_obvious='不显眼', sources=['missing'])
        self.assertIn('Unknown source id', str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            await self.call('scout_candidate', id='x2', name='产品', company='公司', category='零售',
                            what='做一件事', buyer='老板', price='¥10', replicable='能', effort='weeks',
                            moat='关系', risk='平台', why_not_obvious='不显眼', sources=[])
        self.assertIn('registered source', str(caught.exception))

    async def test_third_variant_of_one_category_blocks_the_fourth(self):
        for index in range(3):
            await self.candidate(f'r{index}', '零售')
        with self.assertRaises(ValueError) as caught:
            await self.candidate('r3', '零售')
        message = str(caught.exception)
        self.assertIn('already has 3 candidates', message)
        self.assertIn('leave the obvious pool', message)
        # Another category is always open: the quota asks for breadth, not less work.
        await self.candidate('m0', '制造')
        self.assertEqual(self.tools.scout_public()['counts']['categories'], 2)

    async def test_effort_enum_is_closed(self):
        await self.source('src-e1')
        with self.assertRaises(ValueError) as caught:
            await self.call('scout_candidate', id='e1', name='产品', company='公司', category='零售',
                            what='做一件事', buyer='老板', price='¥10', replicable='能', effort='years',
                            moat='关系', risk='平台', why_not_obvious='不显眼', sources=['src-e1'])
        self.assertIn('effort', str(caught.exception))

    async def test_screen_needs_twelve_candidates(self):
        await self.doc('criteria.md')
        for index in range(11):
            await self.candidate(f's{index}', CATEGORIES[index % len(CATEGORIES)])
        with self.assertRaises(ValueError) as caught:
            await self.call('scout_stage', stage='screen')
        self.assertIn('12', str(caught.exception))

    async def test_shortlist_is_refused_until_the_pool_and_the_rejection_list_exist(self):
        await self.doc('criteria.md')
        with self.assertRaises(ValueError) as caught:
            await self.call('scout_shortlist', picks=[
                {'id': 'c00', 'why': '强', 'first_experiment': '问十家'}])
        message = str(caught.exception)
        self.assertIn('candidates', message)
        self.assertIn('excluded', message)
        for index, category in enumerate(CATEGORIES):
            for position in range(3):
                await self.candidate(f'c{index}{position}', category)
        with self.assertRaises(ValueError) as caught:
            await self.call('scout_shortlist', picks=[
                {'id': 'c00', 'why': '强', 'first_experiment': '问十家'}])
        self.assertIn('excluded', str(caught.exception))

    async def test_shortlist_size_and_membership(self):
        await self.ready()
        too_few = [{'id': 'c00', 'why': '强', 'first_experiment': '问十家'}] * 2
        with self.assertRaises(ValueError) as caught:
            await self.call('scout_shortlist', picks=too_few)
        self.assertIn('3..7', str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            await self.call('scout_shortlist', picks=[
                {'id': 'nope', 'why': '强', 'first_experiment': '问十家'},
                {'id': 'c00', 'why': '强', 'first_experiment': '问十家'},
                {'id': 'c10', 'why': '强', 'first_experiment': '问十家'}])
        self.assertIn('Unknown candidate', str(caught.exception))

    async def test_shortlist_writes_files_and_public_state(self):
        state = await self.ready()
        self.assertEqual(state['counts']['candidates'], 24)
        self.assertEqual(state['counts']['categories'], 8)
        self.assertEqual(state['counts']['excluded'], 5)
        picks = [{'id': 'c00', 'why': '付费已经发生，复刻成本低', 'first_experiment': '两周内问 10 家门店'},
                 {'id': 'c10', 'why': '同一套流程换个行业', 'first_experiment': '做一个落地页收定金'},
                 {'id': 'c20', 'why': '客户自己在群里找同类', 'first_experiment': '在群里发一版报价'}]
        await self.call('scout_shortlist', picks=picks)
        body = (scout.base(self.root) / 'shortlist.md').read_text('utf-8')
        self.assertIn('候选池：24 个', body)
        self.assertIn('排除的惯性想法：5 条', body)
        self.assertIn('两周内问 10 家门店', body)
        stored = json.loads((scout.base(self.root) / 'shortlist.json').read_text('utf-8'))
        self.assertEqual([row['id'] for row in stored['picks']], ['c00', 'c10', 'c20'])
        value = self.tools.scout_public()
        self.assertEqual(value['counts']['shortlist'], True)
        self.assertEqual(len(value['picks']), 3)

    async def test_rejection_list_is_written_for_a_human(self):
        await self.call('scout_exclude', idea='AI 套壳聊天', why='没有付费理由', category='ai')
        await self.call('scout_exclude', idea='AI 套壳聊天', why='确认没有付费理由', category='ai')
        listed = (scout.base(self.root) / 'excluded.md').read_text('utf-8')
        self.assertIn('AI 套壳聊天', listed)
        self.assertEqual(listed.count('AI 套壳聊天'), 1, 'the same idea must not appear twice')
        self.assertIn('确认没有付费理由', listed)

    async def test_prompt_carries_the_quota_and_the_rejection_rule(self):
        text = scout.prompt({'stage': 'sweep'}, self.root)
        self.assertIn('最多 3 个候选', text)
        self.assertIn('至少 20 个候选', text)
        self.assertIn('scout_exclude', text)
        self.assertIn('why_not_obvious', text)
