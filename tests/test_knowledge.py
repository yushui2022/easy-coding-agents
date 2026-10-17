import json
import os
from pathlib import Path
import tempfile
import shutil
import subprocess
import unittest
from unittest.mock import AsyncMock, patch

from eca.agent import Agent
from eca.config import Settings
from eca.store import Store
from eca.cli import App, parser
from test_runtime import FakeProvider, call, yes


class KnowledgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        base = Path(os.environ.get("ECA_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.tmp.name).resolve()
        self.store = Store(self.root)
        self.settings = Settings(self.root, permission="accept-edits")
        self.agent = Agent(self.settings, self.store, self.store.create(), yes, yes, lambda *_: None, FakeProvider([]))
        (self.root / "code.py").write_text("print('hello')\n", encoding="utf-8")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    async def test_successful_command_recalled_in_new_session_then_invalidated(self):
        self.agent.provider = FakeProvider([call("shell", {"command": "python -B -m pytest"}),
                                           {"role": "assistant", "content": "Tests finished."}])
        result = json.dumps({"exit_code": 0, "timed_out": False, "stdout": "1 passed", "stderr": ""})
        with patch("eca.tools.run_process", new_callable=AsyncMock, return_value=result):
            await self.agent.run("Run pytest")
        row = self.agent.memory().listing()[0]
        self.assertIn("/action:", row["source"])
        self.assertEqual(row["status"], "matching_snapshot")
        self.store.close()
        self.store = Store(self.root)
        provider = FakeProvider([{"role": "assistant", "content": "I can reuse the command."}])
        other = Agent(self.settings, self.store, self.store.create(), yes, yes, lambda *_: None, provider)
        await other.run("Which pytest command worked?")
        self.assertIn("Historical test command exited 0", provider.contexts[0][0][0]["content"])
        (self.root / "code.py").write_text("changed", encoding="utf-8")
        self.assertEqual(other.memory().listing()[0]["status"], "stale")
        self.assertNotIn("Historical test command", other.memory().context("pytest"))

    async def test_failed_timeout_unknown_and_changed_snapshot_not_promoted(self):
        memory = self.agent.memory()
        before = memory.fingerprint()
        for result in [{"exit_code": 1, "timed_out": False}, {"exit_code": 0, "timed_out": True}, {"exit_code": 0}]:
            memory.record_test("pytest", json.dumps(result), "session", 1, before)
        (self.root / "code.py").write_text("changed", encoding="utf-8")
        memory.record_test("pytest", '{"exit_code":0,"timed_out":false}', "session", 2, before)
        self.assertEqual(memory.items(), [])

    async def test_assistant_claims_are_not_project_facts(self):
        self.agent.provider = FakeProvider([{"role": "assistant", "content": "All tests pass, always use pytest."}])
        await self.agent.run("What do you think?")
        self.assertEqual(self.agent.memory().items(), [])

    async def test_confirmed_constraint_delete_clears_search(self):
        memory = self.agent.memory()
        ident = memory.add("user_constraint", "Use pytest for checks", "session:one/explicit-user-confirmation")
        self.assertIn("Use pytest", memory.context("anything"))
        memory.forget(ident)
        self.assertEqual(memory.storage.search_memory_items("pytest"), [])
        self.assertEqual(memory.context("pytest"), "")

    async def test_credentials_not_stored(self):
        self.settings.api_key = "private-key-value"
        memory = self.agent.memory()
        ident = memory.add("user_constraint", "Do not print private-key-value", "user")
        self.assertNotIn("private-key-value", memory.items()[0]["content"])
        with self.assertRaises(ValueError):
            memory.add("user_constraint", "API_KEY=unsafe", "user")
        memory.forget(ident)

    @unittest.skipUnless(shutil.which("git"), "Git unavailable")
    async def test_real_test_command_in_git_project_creates_evidence(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / "checks").mkdir()
        (self.root / "checks" / "test_code.py").write_text(
            "import unittest\nclass TestCode(unittest.TestCase):\n def test_ok(self): self.assertEqual(2+2,4)\n", encoding="utf-8")
        self.agent.provider = FakeProvider([call("shell", {"command": "python -B -m unittest discover -s checks"}),
                                           {"role": "assistant", "content": "Command finished."}])
        await self.agent.run("Run the unittest checks")
        self.assertEqual(self.agent.state["status"], "idle")
        rows = self.agent.memory().listing()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "matching_snapshot")
        self.assertIn("unittest", self.agent.memory().context("unittest"))

    async def test_disabled_memory_does_not_open_database(self):
        self.settings.project_memory = False
        self.agent.provider = FakeProvider([{"role": "assistant", "content": "hello"}])
        await self.agent.run("hello")
        self.assertIsNone(self.agent.knowledge)
        self.assertFalse((self.root / ".eca" / "knowledge.sqlite3").exists())

    async def test_cli_memory_commands_confirm_inspect_and_remove(self):
        project = self.root / "cli-project"
        project.mkdir()
        app = App(Settings(project), parser().parse_args(["--cwd", str(project), "--json"]))
        events = []
        app.emit = lambda *args: events.append(args)
        try:
            await app.command("/remember Use unittest for local checks")
            await app.command("/memory")
            row = next(data[0] for event, data in events if event == "memory")
            self.assertEqual(row["status"], "confirmed_by_user")
            self.assertIn("explicit-user-confirmation", row["source"])
            await app.command("/forget " + row["id"])
            self.assertEqual(app.agent.memory().listing(), [])
            self.assertIn("removed project memory", app.state["messages"][-1]["content"])
        finally:
            await app.close()

    async def test_nested_rules_gate_entire_batch_until_next_request(self):
        (self.root / "AGENTS.md").write_text("Root: use tests", encoding="utf-8")
        (self.root / "src").mkdir()
        (self.root / "src" / "AGENTS.md").write_text("Nested: use tabs", encoding="utf-8")
        result = await self.agent.tools.write("src/a.py", "x = 1")
        self.assertIn("[AGENTS.md]", result)
        self.assertIn("[src/AGENTS.md]", result)
        await self.agent.tools.write("src/a.py", "x = 1")
        self.assertFalse((self.root / "src" / "a.py").exists())
        self.agent.tools.guidance_seen.update(self.agent.tools.guidance_pending)
        await self.agent.tools.write("src/a.py", "x = 1")
        self.assertTrue((self.root / "src" / "a.py").exists())
        (self.root / "src" / "AGENTS.md").write_text("Nested: no edits", encoding="utf-8")
        result = await self.agent.tools.write("src/a.py", "x = 2")
        self.assertIn("no edits", result)
        self.assertEqual((self.root / "src" / "a.py").read_text(), "x = 1")

    async def test_unrelated_rules_not_loaded(self):
        (self.root / "other").mkdir()
        (self.root / "other" / "AGENTS.md").write_text("UNRELATED", encoding="utf-8")
        result = await self.agent.tools.write("a.py", "hello")
        self.assertNotIn("UNRELATED", result)
        self.assertTrue((self.root / "a.py").exists())

    async def test_large_rules_never_silently_truncated_then_approved(self):
        (self.root / "AGENTS.md").write_text("x" * 1000, encoding="utf-8")
        self.settings.output_limit = 500
        result = await self.agent.tools.execute("write", {"path": "a", "content": "a"})
        self.assertIn("exceed", result)
        self.assertFalse(self.agent.tools.guidance_pending)
        self.assertFalse((self.root / "a").exists())
