import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eca import skills


def make(base, name, description='', body='# body'):
    folder = Path(base) / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: {description}\n---\n{body}\n', encoding='utf-8')
    return folder


class Catalog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.project = root / 'project'
        self.codex = root / 'codex'
        self.claude = root / 'claude'
        self.buddy = root / 'buddy'
        self.eca = root / 'eca'
        self.env = patch.dict(os.environ, {
            'ECS_SKILLS_DIR': str(self.eca), 'ECA_CODEX_HOME': str(self.codex),
            'ECA_CLAUDE_HOME': str(self.claude), 'ECA_WORKBUDDY_HOME': str(self.buddy)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_reads_every_tool_folder(self):
        make(self.project / '.agents' / 'skills', 'proj-skill', 'from the project')
        make(self.codex / 'skills', 'codex-skill', 'from codex')
        make(self.claude / 'skills', 'claude-skill', 'from claude')
        make(self.buddy / 'skills', 'buddy-skill', 'from workbuddy')
        catalog = skills.Skills(self.project).catalog()
        self.assertEqual({row['source'] for row in catalog.values()},
                         {'project', 'codex', 'claude', 'workbuddy'})
        self.assertEqual(catalog['codex-skill']['description'], 'from codex')
        self.assertEqual(catalog['proj-skill']['scope'], 'project')
        self.assertEqual(catalog['claude-skill']['scope'], 'user')

    def test_project_wins_a_name_clash_then_eca(self):
        make(self.codex / 'skills', 'same', 'from codex')
        make(self.eca, 'same', 'from eca')
        self.assertEqual(skills.Skills(self.project).catalog()['same']['source'], 'eca')
        make(self.project / '.agents' / 'skills', 'same', 'from project')
        self.assertEqual(skills.Skills(self.project).catalog()['same']['source'], 'project')

    def test_works_without_an_open_project(self):
        make(self.codex / 'skills', 'codex-only', 'shared skill')
        self.assertIn('codex-only', skills.Skills(None).catalog())

    def test_rejects_unsafe_or_odd_entries(self):
        folder = self.codex / 'skills'
        make(folder, 'good', 'ok')
        (folder / 'no-skill-md').mkdir(parents=True)          # a folder without SKILL.md
        bad = folder / 'bad name'
        bad.mkdir(parents=True)
        (bad / 'SKILL.md').write_text('x', encoding='utf-8')  # name with a space
        big = folder / 'huge'
        big.mkdir(parents=True)
        (big / 'SKILL.md').write_text('x' * 40000, encoding='utf-8')
        catalog = skills.Skills(None).catalog()
        self.assertEqual(set(catalog), {'good'})

    def test_load_names_the_source_and_read_previews(self):
        make(self.claude / 'skills', 'claude-skill', 'from claude', 'BODY TEXT')
        library = skills.Skills(None)
        self.assertIn('installed for claude', library.load('claude-skill'))
        preview = library.read('claude-skill')
        self.assertEqual(preview['source'], 'claude')
        self.assertIn('BODY TEXT', preview['text'])
        self.assertFalse(preview['truncated'])

    def test_unknown_skill_raises(self):
        with self.assertRaises(ValueError):
            skills.Skills(None).load('nope')
        with self.assertRaises(ValueError):
            skills.Skills(None).read('nope')



class PromptBudget(unittest.TestCase):
    def test_catalog_in_the_prompt_is_bounded_by_characters(self):
        from eca.agent import SKILL_CATALOG_CHARS, Agent
        from eca.config import Settings
        from eca.store import Store
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                'ECS_SKILLS_DIR': str(Path(tmp) / 'eca'), 'ECA_CODEX_HOME': str(Path(tmp) / 'codex'),
                'ECA_CLAUDE_HOME': str(Path(tmp) / 'claude'), 'ECA_WORKBUDDY_HOME': str(Path(tmp) / 'buddy')}):
            root = Path(tmp) / 'project'
            root.mkdir()
            for index in range(40):
                make(root / '.agents' / 'skills', f'skill-{index}', 'd' * 300)
            store = Store(root)
            try:
                state = store.create()
                agent = Agent(Settings(root), store, state, lambda *_: True, lambda *_: True, lambda *_: None, None)
                prompt = agent.system_prompt()
            finally:
                store.close()
        self.assertIn('further name(s) are listed by skills()', prompt)
        listing = prompt.split('Available optional local workflows', 1)[1]
        self.assertLessEqual(len(listing), SKILL_CATALOG_CHARS + 200)
        self.assertIn('"skill-0"', prompt)

class CatalogCache(unittest.TestCase):
    """The catalog runs on every request, so it must not re-read the files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        root = Path(self.tmp.name)
        self.project = root / 'project'
        self.codex = root / 'codex'
        self.env = patch.dict(os.environ, {
            'ECS_SKILLS_DIR': str(root / 'eca'), 'ECA_CODEX_HOME': str(self.codex),
            'ECA_CLAUDE_HOME': str(root / 'none-claude'), 'ECA_WORKBUDDY_HOME': str(root / 'none-buddy')})
        self.env.start()
        skills._CACHE.clear()
        make(self.codex / 'skills', 'cached-skill', 'from codex')

    def tearDown(self):
        skills._CACHE.clear()
        self.env.stop()
        self.tmp.cleanup()

    def test_second_read_does_not_touch_the_files(self):
        original = Path.read_text
        reads = []

        def counting(path, *args, **kwargs):
            reads.append(path)
            return original(path, *args, **kwargs)

        with patch.object(Path, 'read_text', counting):
            first = skills.Skills(self.project).catalog()
            after_first = len(reads)
            second = skills.Skills(self.project).catalog()
            after_second = len(reads)
        self.assertEqual(after_first, 1)
        self.assertEqual(after_second, after_first, 'a cached catalog must not re-read SKILL.md')
        self.assertEqual(set(first), set(second))
        self.assertEqual(first['cached-skill']['description'], 'from codex')

    def test_a_new_skill_invalidates_the_cache(self):
        first = skills.Skills(self.project).catalog()
        self.assertNotIn('fresh-skill', first)
        make(self.codex / 'skills', 'fresh-skill', 'added later')
        self.assertIn('fresh-skill', skills.Skills(self.project).catalog())

    def test_a_project_skill_still_wins_after_caching(self):
        skills.Skills(self.project).catalog()
        make(self.project / '.agents' / 'skills', 'cached-skill', 'from project')
        self.assertEqual(skills.Skills(self.project).catalog()['cached-skill']['source'], 'project')


if __name__ == '__main__':
    unittest.main()
