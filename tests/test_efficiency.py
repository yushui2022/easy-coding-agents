import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from eca.agent import Agent
from eca.config import Settings
from eca.store import Store
from eca.verification import no_tests_found
from test_runtime import FakeProvider, call, yes


class EfficiencyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        base = Path(os.environ.get("ECA_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root)
        self.settings = Settings(self.root, max_turns=3, auto_compact=False, project_memory=False)
        self.provider = FakeProvider([])
        self.agent = Agent(self.settings, self.store, self.store.create(), yes, yes, lambda *_: None, self.provider)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    async def test_budget_counts_down_without_extra_requests_or_unpaired_tools(self):
        self.provider.responses = iter([call("glob", {"pattern": "*.py"}, str(i)) for i in range(3)])
        await self.agent.run("Inspect")
        self.assertEqual(len(self.provider.contexts), 3)
        for index, (messages, _) in enumerate(self.provider.contexts):
            self.assertIn(f"{3-index} model response(s) remaining", messages[-1]["content"])
        self.assertIn("last response", self.provider.contexts[-1][0][-1]["content"])
        self.assertEqual(self.provider.contexts[0][0][0], self.provider.contexts[2][0][0])
        self.assertFalse(any('[Runtime guidance]' in (m.get('content') or '') for m in self.agent.state['messages']))
        self.assertEqual(self.agent.state["status"], "blocked")
        self.assertEqual(len([m for m in self.agent.state['messages'] if m['role']=='tool']), 3)

    async def test_repeat_hint_preserves_json_and_reexecutes_shell(self):
        response = json.dumps({"exit_code": 0, "timed_out": False, "stdout": "ok", "stderr": ""})
        self.provider.responses = iter([call("shell", {"command": "echo ok"}, str(i)) for i in range(2)] + [{"role":"assistant", "content":"done"}])
        with patch("eca.tools.run_process", new_callable=AsyncMock, return_value=response) as process:
            await self.agent.run("Check")
        self.assertEqual(process.await_count, 2)
        self.assertIn("Repeated observation", self.provider.contexts[2][0][-1]["content"])
        for message in self.agent.state['messages']:
            if message['role']=='tool':
                self.assertEqual(json.loads(message['content'])['stdout'], 'ok')

    async def test_changed_observation_does_not_trigger_repeat_hint(self):
        self.provider.responses = iter([call("shell", {"command": "echo ok"}, str(i)) for i in range(2)] + [{"role":"assistant", "content":"done"}])
        results = [json.dumps({"exit_code":0,"timed_out":False,"stdout":v}) for v in ['old','new']]
        with patch("eca.tools.run_process", new_callable=AsyncMock, side_effect=results):
            await self.agent.run("Check")
        self.assertNotIn("Repeated observation", self.provider.contexts[2][0][-1]["content"])
        self.assertEqual(json.loads(self.agent.state['messages'][-2]['content'])['stdout'], 'new')

    async def test_zero_tests_warns_and_never_enters_success_memory(self):
        self.settings.project_memory = True
        self.provider.responses = iter([call("shell", {"command":"python -B -m unittest discover -q"}), {"role":"assistant","content":"No tests found"}])
        raw = json.dumps({"exit_code":0,"timed_out":False,"stdout":"","stderr":"Ran 0 tests in 0.000s\n\nOK\n"})
        with patch("eca.tools.run_process", new_callable=AsyncMock, return_value=raw):
            await self.agent.run("Run tests")
        output = json.loads(self.agent.state['messages'][2]['content'])
        self.assertEqual(output['exit_code'], 0)
        self.assertEqual(output['test_status'], 'no_tests')
        self.assertEqual(self.agent.memory().items(), [])

    def test_runner_detection_is_conservative(self):
        self.assertTrue(no_tests_found('pytest -q', {'stdout':'no tests ran in 0.01s'}))
        self.assertTrue(no_tests_found('python -m pytest', {'stdout':'=== no tests collected in 0.01s ==='}))
        self.assertFalse(no_tests_found('echo example', {'stdout':'Ran 0 tests in 0.01s'}))
        self.assertFalse(no_tests_found('pytest', {'stdout':'10 passed in 1s'}))
        self.assertFalse(no_tests_found('pytest', {'stdout':'test message: no tests ran in 0.01s'}))
