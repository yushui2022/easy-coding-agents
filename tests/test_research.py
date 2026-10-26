import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from eca import research
from eca.config import Settings
from eca.tools import Tools


class ResearchCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name)
        self.settings = Settings(self.root)
        self.settings.mode = 'scholar'
        self.events = []
        self.approve = AsyncMock(return_value=True)
        self.tools = Tools(self.settings, {}, self.approve, self.approve,
                           lambda *event: self.events.append(event[-1]))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text='x' * 20):
        path = research.base(self.root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, 'utf-8')
        return path

    async def stage(self, target, note=''):
        return json.loads(await self.tools.execute('research_stage', {'stage': target, 'note': note}))

    async def source(self, ident='paper-one', verified=True, kind='doi'):
        return await self.tools.execute('research_source', {
            'id': ident, 'kind': kind, 'url': f'https://doi.org/10.1/{ident}',
            'title': 'A paper', 'verify': False}) if not verified else research.add_source(
            self.root, {'id': ident, 'kind': kind, 'url': f'https://doi.org/10.1/{ident}',
                        'title': 'A paper', 'verified': True})


class Stages(ResearchCase):
    async def test_forward_move_needs_the_previous_artifact(self):
        result = await self.tools.execute('research_stage', {'stage': 'search'})
        self.assertTrue(result.startswith('Error:'), result)
        self.assertIn('proposal', result)
        self.write('proposal.md', 'Research question: does X improve Y?')
        moved = await self.stage('search')
        self.assertEqual(moved['stage'], 'search')
        self.assertEqual(self.tools.state['research']['stage'], 'search')
        self.assertTrue(self.events[-1]['stage'], 'the UI event must carry the new stage')
        self.assertTrue(any(event.get('stage') == 'search' for event in self.events))

    async def test_reading_needs_a_registered_source(self):
        self.write('proposal.md')
        await self.stage('search')
        refused = await self.tools.execute('research_stage', {'stage': 'reading'})
        self.assertIn('sources', refused)
        research.add_source(self.root, {'id': 'p1', 'kind': 'doi', 'url': 'https://doi.org/10.1/p1',
                                        'title': 'T', 'verified': True})
        self.assertEqual((await self.stage('reading'))['stage'], 'reading')

    async def test_moving_back_requires_a_reason_and_is_recorded(self):
        self.write('proposal.md')
        await self.stage('search')
        refused = await self.tools.execute('research_stage', {'stage': 'proposal'})
        self.assertIn('note', refused)
        moved = await self.stage('proposal', 'the review narrowed the topic')
        self.assertEqual(moved['stage'], 'proposal')
        history = self.tools.state['research']['history']
        self.assertEqual(history[-1]['note'], 'the review narrowed the topic')

    async def test_unknown_stage_is_refused(self):
        refused = await self.tools.execute('research_stage', {'stage': 'publish'})
        self.assertIn('proposal', refused)


class Evidence(ResearchCase):
    async def test_verified_claim_needs_evidence(self):
        refused = await self.tools.execute('research_claim', {'id': 'c1', 'claim': 'X improves Y',
                                                              'status': 'verified'})
        self.assertIn('source id or run id', refused)
        accepted = await self.tools.execute('research_claim', {'id': 'c1', 'claim': 'X improves Y'})
        self.assertIn('asserted', accepted)

    async def test_claim_cannot_cite_an_unregistered_source(self):
        refused = await self.tools.execute('research_claim', {'id': 'c1', 'claim': 'X', 'status': 'verified',
                                                              'sources': ['ghost']})
        self.assertIn('Unregistered', refused)

    async def test_unchecked_source_cannot_back_a_verified_claim(self):
        research.add_source(self.root, {'id': 'p1', 'kind': 'url', 'url': 'https://example.com/a',
                                        'title': 'Blog post', 'verified': False})
        refused = await self.tools.execute('research_claim', {'id': 'c1', 'claim': 'X', 'status': 'verified',
                                                              'sources': ['p1']})
        self.assertIn('without an online check', refused)

    async def test_checked_source_or_a_run_allows_verification(self):
        await self.source('p1', verified=True)
        accepted = await self.tools.execute('research_claim', {'id': 'c1', 'claim': 'X', 'status': 'verified',
                                                               'sources': ['p1']})
        self.assertIn('verified', accepted)
        run = await self.tools.execute('research_run', {'id': 'r1', 'label': 'split A', 'command': 'python a.py',
                                                        'outcome': 'partial', 'matches_paper': True})
        self.assertIn('r1', run)

    async def test_a_mismatch_needs_a_note(self):
        refused = await self.tools.execute('research_run', {'id': 'r1', 'label': 'x', 'command': 'python a.py',
                                                            'outcome': 'partial', 'matches_paper': False})
        self.assertIn('note', refused)


class ReportGate(ResearchCase):
    def prepare(self, body, *claim_status):
        self.write('proposal.md')
        research.add_source(self.root, {'id': 'p1', 'kind': 'doi', 'url': 'https://doi.org/10.1/p1',
                                        'title': 'T', 'verified': True})
        for index, status in enumerate(claim_status, start=1):
            research.add_claim(self.root, {'id': f'c{index}', 'claim': f'claim {index}', 'status': status,
                                           'sources': ['p1'], 'runs': []})
        self.write('report.md', body)

    async def test_unregistered_citation_is_refused(self):
        self.prepare('We show X improves Y [src:ghost].', 'verified')
        refused = await self.tools.execute('research_report', {})
        self.assertIn('Unregistered', refused)
        self.assertIn('ghost', refused)

    async def test_registered_citation_passes(self):
        self.prepare('We show X improves Y [src:p1].', 'verified')
        result = json.loads(await self.tools.execute('research_report', {}))
        self.assertTrue(result['ok'])
        self.assertEqual(result['citations'], ['p1'])

    async def test_asserted_claim_blocks_the_report(self):
        self.prepare('X improves Y [src:p1].', 'asserted')
        refused = await self.tools.execute('research_report', {})
        self.assertIn('asserted', refused)

    async def test_missing_deviations_blocks_the_report(self):
        self.prepare('X improves Y [src:p1].', 'verified')
        research.add_run(self.root, {'id': 'r1', 'label': 'split A', 'command': 'python a.py',
                                     'outcome': 'partial', 'matches_paper': False, 'note': 'lower by 2 points'})
        refused = await self.tools.execute('research_report', {})
        self.assertIn('deviations', refused)
        self.write('deviations.md', 'r1: accuracy 78.1 vs 80.0 reported')
        result = json.loads(await self.tools.execute('research_report', {}))
        self.assertTrue(result['ok'])

    async def test_a_missing_report_is_not_invented(self):
        refused = await self.tools.execute('research_report', {})
        self.assertIn('report.md', refused)


    async def test_the_stage_is_mirrored_into_the_artifact_folder(self):
        self.write('proposal.md')
        await self.stage('search')
        mirror = json.loads((research.base(self.root) / 'stage.json').read_text('utf-8'))
        self.assertEqual(mirror['stage'], 'search')
        self.assertEqual(mirror['history'][-1]['to'], 'search')


class Documents(ResearchCase):
    async def test_only_named_artifacts_are_writable(self):
        accepted = await self.tools.execute('research_doc', {'name': 'proposal.md', 'content': '# P'})
        self.assertIn('proposal.md', accepted)
        self.assertIn('# P', (research.base(self.root) / 'proposal.md').read_text('utf-8'))
        for name in ('../../escape.md', 'store.db', 'reading/unknown.md', 'notes.txt'):
            refused = await self.tools.execute('research_doc', {'name': name, 'content': 'x'})
            self.assertTrue(refused.startswith('Error:'), f'{name} should be refused: {refused}')

    async def test_a_reading_card_needs_a_registered_source(self):
        refused = await self.tools.execute('research_doc', {'name': 'reading/p1.md', 'content': 'card'})
        self.assertIn('unregistered source', refused)
        research.add_source(self.root, {'id': 'p1', 'kind': 'doi', 'url': 'https://doi.org/10.1/p1',
                                        'title': 'T', 'verified': True})
        accepted = await self.tools.execute('research_doc', {'name': 'reading/p1.md', 'content': 'card'})
        self.assertIn('reading/p1.md', accepted)
        self.assertTrue((research.base(self.root) / 'reading' / 'p1.md').is_file())

    async def test_append_keeps_earlier_lines(self):
        await self.tools.execute('research_doc', {'name': 'search-log.jsonl', 'content': '{"q":"a"}'})
        await self.tools.execute('research_doc', {'name': 'search-log.jsonl', 'content': '{"q":"b"}', 'append': True})
        body = (research.base(self.root) / 'search-log.jsonl').read_text('utf-8')
        self.assertIn('"a"', body)
        self.assertIn('"b"', body)


class Presentation(ResearchCase):
    async def test_public_view_reports_stage_counts_and_artifact_names(self):
        research.add_source(self.root, {'id': 'p1', 'kind': 'doi', 'url': 'https://doi.org/10.1/p1',
                                        'title': 'T', 'verified': True})
        view = research.public({'stage': 'reading'}, self.root)
        self.assertEqual(view['stage'], 'reading')
        self.assertEqual(view['counts']['sources'], 1)
        self.assertEqual(view['counts']['verified_sources'], 1)
        names = [item['name'] for item in view['artifacts']]
        self.assertIn('sources.jsonl', names)
        self.assertEqual(len(view['stages']), 7)


if __name__ == '__main__':
    unittest.main()
