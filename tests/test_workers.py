import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eca.agent import Agent
from eca.config import Settings
from eca.models import delegation_schemas, worker_settings
from eca.store import Store
from eca.tools import SCHEMAS
from test_runtime import FakeProvider, yes


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.tmp.name).resolve()
        self.settings = Settings(self.root, model='main-model', api_key='main-secret', project_memory=False)
        self.store = Store(self.root)
        self.state = self.store.create()
        self.agent = Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None, FakeProvider([]))

    async def asyncTearDown(self):
        await self.agent.close()
        self.store.close()
        self.tmp.cleanup()

    def configure(self):
        self.settings.model_profiles = {'local': dict(model='small-model', base_url='http://localhost:11434/v1',
            api_format='openai', api_key_env='ECA_TEST_WORKER_KEY', context_chars=12000, max_output_tokens=1024)}
        self.settings.worker_profiles = ['local']

    async def test_default_single_api_unchanged(self):
        self.assertIs(worker_settings(self.settings), self.settings)
        self.assertIs(delegation_schemas(SCHEMAS, self.settings), SCHEMAS)
        captured = []
        def provider(settings):
            captured.append(settings)
            return FakeProvider([{'role':'assistant', 'content':'done'}])
        with patch('eca.agent.Provider', provider):
            result = json.loads(await self.agent.delegate('Inspect files'))
        self.assertEqual(captured[0].model, 'main-model')
        self.assertEqual(captured[0].api_key, 'main-secret')
        self.assertEqual(result['model_profile'], '')

    async def test_selected_worker_separate_key_and_main_unchanged(self):
        self.configure()
        captured = []
        def provider(settings):
            captured.append(settings)
            return FakeProvider([{'role':'assistant', 'content':'done'}])
        with patch.dict(os.environ, {'ECA_TEST_WORKER_KEY':'local-secret'}), patch('eca.agent.Provider', provider):
            result = json.loads(await self.agent.tools.execute('delegate', {'task':'Inspect files','model_profile':'local'}))
        self.assertEqual(captured[0].model, 'small-model')
        self.assertEqual(captured[0].api_key, 'local-secret')
        self.assertEqual(captured[0].context_chars, 12000)
        self.assertEqual(self.agent.settings.api_key, 'main-secret')
        self.assertEqual(self.agent.settings.model, 'main-model')
        saved = self.store.peek(result['session'])
        self.assertEqual(saved['model_profile'], 'local')
        self.assertNotIn('local-secret', json.dumps(saved))
        self.assertNotIn('main-secret', json.dumps(saved))
        self.assertEqual(self.store.db.execute('SELECT model,root_id FROM usage_requests').fetchone(), ('small-model', self.state['id']))

    async def test_mixed_parallel_profiles_resolve_before_snapshot(self):
        self.configure()
        (self.root / '.env').write_text('ECA_TEST_WORKER_KEY=from-project-env\n')
        captured = []
        def provider(settings):
            captured.append(settings)
            return FakeProvider([{'role':'assistant', 'content':'done'}])
        with patch('eca.agent.Provider', provider):
            result = json.loads(await self.agent.parallel([{'task':'A','model_profile':'local'},{'task':'B'}]))
        by_model = {s.model:s for s in captured}
        self.assertEqual(by_model['small-model'].api_key, 'from-project-env')
        self.assertEqual(by_model['main-model'].api_key, 'main-secret')
        self.assertEqual([r['model_profile'] for r in result], ['local',''])
        self.assertFalse((Path(result[0]['workspace']) / '.env').exists())

    async def test_unlisted_profile_rejected_without_dispatch_or_child(self):
        self.configure()
        self.settings.worker_profiles = []
        with self.assertRaises(ValueError):
            await self.agent.delegate('A', model_profile='local')
        with self.assertRaises(ValueError):
            await self.agent.parallel([{'task':'A'},{'task':'B','model_profile':'local'}])
        self.assertEqual(self.agent.child_calls, 0)
        self.assertNotIn('children', self.state)

    def test_schema_opt_in_and_config_validation(self):
        self.configure()
        schemas = delegation_schemas(SCHEMAS, self.settings)
        delegated = next(s['function'] for s in schemas if s['function']['name']=='delegate')
        self.assertEqual(delegated['parameters']['properties']['model_profile']['enum'], ['local'])
        original = next(s['function'] for s in SCHEMAS if s['function']['name']=='delegate')
        self.assertNotIn('model_profile', original['parameters']['properties'])
        for value in ('local', ['missing'], ['local','local'], [1]):
            self.settings.worker_profiles=value
            with self.assertRaises(ValueError):
                self.settings.validate()

    def test_config_load_opt_in(self):
        (self.root / 'eca.toml').write_text('''[agent]
worker_profiles = ["local"]
[model_profiles.local]
model = "small-model"
base_url = "http://localhost:11434/v1"
api_format = "openai"
api_key_env = "ECA_TEST_WORKER_KEY"
''')
        settings = Settings.load(self.root)
        self.assertEqual(settings.worker_profiles, ['local'])
        self.assertNotEqual(settings.model, 'small-model')

    async def test_worker_failure_does_not_fallback(self):
        self.configure()
        captured = []
        def provider(settings):
            captured.append(settings.model)
            return FakeProvider([RuntimeError('unavailable')])
        with patch('eca.agent.Provider', provider):
            result = json.loads(await self.agent.delegate('Inspect files', model_profile='local'))
        self.assertEqual(captured, ['small-model'])
        self.assertEqual(result['status'], 'error')
        self.assertEqual(self.agent.settings.model, 'main-model')
