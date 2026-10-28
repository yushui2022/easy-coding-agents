"""Business feasibility mode: the gates are read from the artifacts, not trusted."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from eca import modes, tools, venture
from eca.config import Settings

ANSWER = {"verdict": "validate", "confidence": "medium", "summary": "值得花两周验证，不是直接开发。",
          "why_buy": "现有工具要人工导表，这个能一次出结果。",
          "why_return": "每月都有一次同类整理。",
          "why_stay": "模板和口径积累在本地，换工具要重做。",
          "margin": "单次 80 元，成本 20 分钟。",
          "falsifier": "如果十个目标用户里没有一个愿意先付定金，这个假设不成立。",
          "risks": ["平台条款可能禁止自动化"], "next_steps": ["两周内找 10 人试用，收 3 笔定金"]}


class VentureCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name)
        self.settings = Settings(self.root)
        self.settings.mode = 'venture'
        self.events = []

        async def approve(*_args, **_kwargs):
            return True

        self.tools = tools.Tools(self.settings, {}, approve, approve,
                                 lambda *event: self.events.append(event[-1]))

    def tearDown(self):
        self.tmp.cleanup()

    async def call(self, tool, **args):
        value = await self.tools.execute(tool, args)
        # Tools report refusals as "Error: …" strings, exactly like the model sees them.
        if isinstance(value, str) and value.startswith('Error: '):
            raise ValueError(value[len('Error: '):])
        return json.loads(value)

    async def doc(self, name, text='正文' * 20):
        return await self.call('business_doc', name=name, content=text)

    async def source(self, ident, kind='competitor'):
        return await self.call('business_source', id=ident, kind=kind,
                               url=f'https://example.com/{ident}', title=f'来源 {ident}')

    async def claim(self, ident, status='verified', sources=None):
        return await self.call('business_claim', id=ident, claim=f'断言 {ident}', status=status,
                               sources=sources if sources is not None else ['a1'])

    async def ready(self):
        """Everything the verdict gate demands, one piece at a time."""
        await self.doc('brief.md')
        for ident, kind in (('a1', 'competitor'), ('a2', 'community'), ('a3', 'pricing')):
            await self.source(ident, kind)
        await self.doc('competitors.md')
        for ident in ('c1', 'c2', 'c3'):
            await self.claim(ident)
        await self.call('business_stage', stage='market')
        await self.call('business_stage', stage='competition')
        await self.call('business_stage', stage='economics')
        await self.doc('unit.md')
        await self.call('business_stage', stage='diligence')
        await self.doc('diligence.md')
        return await self.call('business_stage', stage='verdict')

    async def test_mode_is_readonly_but_carries_the_workflow_tools(self):
        self.assertTrue(modes.reading('venture'))
        self.assertFalse(modes.working('venture'))
        allowed = tools.allowed('venture')
        for name in ('business_stage', 'business_source', 'business_claim', 'business_doc', 'business_verdict'):
            self.assertIn(name, allowed)
        for name in ('write', 'edit', 'shell', 'delete'):
            self.assertNotIn(name, allowed)
        self.assertIn('web_fetch', allowed)

    async def test_first_stage_needs_nothing_and_second_needs_the_brief(self):
        first = await self.call('business_stage', stage='brief')
        self.assertEqual(first['label'], '定题')
        with self.assertRaises(ValueError) as caught:
            await self.call('business_stage', stage='market')
        self.assertIn('brief', str(caught.exception))

    async def test_market_sweep_needs_three_registered_sources(self):
        await self.doc('brief.md')
        with self.assertRaises(ValueError) as caught:
            await self.call('business_stage', stage='competition')
        self.assertIn('sources', str(caught.exception))
        await self.source('a1')
        await self.source('a2')
        with self.assertRaises(ValueError):
            await self.call('business_stage', stage='competition')
        await self.source('a3', 'pricing')
        entered = await self.call('business_stage', stage='competition')
        self.assertEqual(entered['stage'], 'competition')

    async def test_claim_cannot_cite_a_page_nobody_registered(self):
        with self.assertRaises(ValueError) as caught:
            await self.claim('c1', sources=['nope'])
        self.assertIn('Unknown source id', str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            await self.claim('c2', status='verified', sources=[])
        self.assertIn('registered source', str(caught.exception))

    async def test_source_url_must_be_https_and_kind_known(self):
        with self.assertRaises(ValueError):
            await self.call('business_source', id='x1', kind='competitor', url='http://example.com', title='t')
        with self.assertRaises(ValueError):
            await self.call('business_source', id='x2', kind='rumour', url='https://example.com', title='t')

    async def test_documents_are_an_allowlist(self):
        await self.doc('evidence.md')
        with self.assertRaises(ValueError) as caught:
            await self.doc('verdict.md')
        self.assertIn('business_verdict', str(caught.exception))

    async def test_backward_move_must_explain_itself(self):
        await self.ready()
        with self.assertRaises(ValueError) as caught:
            await self.call('business_stage', stage='market')
        self.assertIn('note', str(caught.exception))
        moved = await self.call('business_stage', stage='market', note='竞品降价，需求要重估')
        self.assertEqual(moved['stage'], 'market')

    async def test_verdict_is_refused_while_a_claim_is_only_asserted(self):
        await self.ready()
        await self.claim('c4', status='asserted')
        with self.assertRaises(ValueError) as caught:
            await self.call('business_verdict', **ANSWER)
        self.assertIn('asserted', str(caught.exception))


    async def test_verdict_needs_the_four_questions_risks_and_falsifier(self):
        await self.ready()
        labels = {'why_buy': '第一次为什么买', 'why_return': '第二次为什么回来',
                  'why_stay': '被复制后为什么留下', 'margin': '每次交付赚多少', 'falsifier': 'falsifier'}
        for field, label in labels.items():
            payload = dict(ANSWER)
            payload[field] = ''
            with self.assertRaises(ValueError) as caught:
                await self.call('business_verdict', **payload)
            self.assertIn(label, str(caught.exception))
        for field in ('risks', 'next_steps'):
            payload = dict(ANSWER)
            payload[field] = []
            with self.assertRaises(ValueError):
                await self.call('business_verdict', **payload)

    async def test_verdict_enums_are_closed(self):
        await self.ready()
        payload = dict(ANSWER, verdict='yes')
        with self.assertRaises(ValueError) as caught:
            await self.call('business_verdict', **payload)
        self.assertIn('validate', str(caught.exception))
        payload = dict(ANSWER, confidence='certain')
        with self.assertRaises(ValueError):
            await self.call('business_verdict', **payload)

    async def test_verdict_writes_the_file_and_keeps_the_answers(self):
        await self.ready()
        result = await self.call('business_verdict', **ANSWER)
        self.assertEqual(result['verdict']['label'], '值得验证')
        body = (venture.base(self.root) / 'verdict.md').read_text('utf-8')
        for text in ('值得验证', '第一次为什么买', '第二次为什么回来', '被复制后为什么留下',
                     '每次交付赚多少', '什么会翻案', ANSWER['falsifier']):
            self.assertIn(text, body)
        stored = json.loads((venture.base(self.root) / 'verdict.json').read_text('utf-8'))
        self.assertEqual(stored['confidence'], 'medium')
        self.assertEqual(stored['sources'], 3)

    async def test_public_state_reports_counts_and_verdict(self):
        state = await self.ready()
        self.assertEqual(state['next'], [])
        value = self.tools.business_public()
        self.assertEqual(value['stage'], 'verdict')
        self.assertEqual(value['counts']['sources'], 3)
        self.assertEqual(value['counts']['claims'], 3)
        self.assertIsNone(value['verdict'])
        await self.call('business_verdict', **ANSWER)
        self.assertEqual(self.tools.business_public()['verdict']['label'], '值得验证')

    async def test_prompt_names_the_current_stage_and_the_four_questions(self):
        text = venture.prompt({'stage': 'economics'}, self.root)
        self.assertIn('economics', text)
        self.assertIn('第一次为什么买', text)
        self.assertIn('unit.md', text)
        self.assertNotIn('business_verdict', venture.prompt({'stage': 'brief'}, self.root).split('Now:')[1])
