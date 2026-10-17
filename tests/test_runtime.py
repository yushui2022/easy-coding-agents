import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI

from eca.agent import Agent
from eca.config import Settings
from eca.provider import Provider
from eca.store import Store
from eca.tools import Tools, run_process


async def yes(*_):
    return True


async def no(*_):
    return False


def call(name, args, ident="call1"):
    return {"role": "assistant", "content": None, "tool_calls": [{"id": ident, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


class FakeProvider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.contexts = []

    async def complete(self, messages, tools, emit):
        self.contexts.append((messages, tools))
        value = next(self.responses)
        if isinstance(value, BaseException):
            raise value
        return value, {}

    async def close(self):
        pass


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        base = Path(os.environ.get("ECA_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.tmp.name).resolve()
        self.settings = Settings(self.root)
        self.store = Store(self.root)
        self.state = self.store.create()
        self.tools = Tools(self.settings, self.state, yes, yes, lambda *_: None)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    async def test_reject_ambiguous_edit(self):
        path = self.root / "code.py"
        path.write_text("a = 1\nb = 1\n", encoding="utf-8")
        result = await self.tools.execute("edit", {"path": "code.py", "old": "1", "new": "2"})
        self.assertIn("exactly once", result)
        self.assertEqual(path.read_text(), "a = 1\nb = 1\n")

    async def test_permission_denied_does_not_write(self):
        self.tools.approve = no
        result = await self.tools.execute("write", {"path": "new.txt", "content": "no"})
        self.assertIn("Denied", result)
        self.assertFalse((self.root / "new.txt").exists())

    async def test_permission_error_string_is_not_approval(self):
        async def broken(*_):
            return "Error: input unavailable"
        self.tools.approve = broken
        result = await self.tools.execute("write", {"path": "new.txt", "content": "no"})
        self.assertIn("Denied", result)
        self.assertFalse((self.root / "new.txt").exists())

    async def test_project_lock_rejects_second_writer(self):
        with self.assertRaisesRegex(ValueError, "Another ECA"):
            Store(self.root)

    async def test_file_changed_during_approval(self):
        path = self.root / "code.py"
        path.write_text("before", encoding="utf-8")
        async def race(*_):
            path.write_text("user change", encoding="utf-8")
            return True
        self.tools.approve = race
        result = await self.tools.execute("write", {"path": "code.py", "content": "agent change"})
        self.assertIn("changed while", result)
        self.assertEqual(path.read_text(), "user change")

    async def test_mode_enforced_at_execution(self):
        self.settings.mode = "plan"
        for name, args in [("write", {"path": "bad", "content": "bad"}), ("shell", {"command": "echo bad"})]:
            self.assertIn("Denied", await self.tools.execute(name, args))
        self.settings.mode = "chat"
        self.assertIn("Denied", await self.tools.execute("read", {"path": "a"}))

    async def test_paths_and_secrets(self):
        for value in ("../escape", ".env", ".ENV", ".env.local", ".git/config", ".eca/sessions.sqlite3", "secret.pem"):
            self.assertIn("Error", await self.tools.execute("read", {"path": value}))
        self.assertEqual(self.tools.path(".env.example"), self.root / ".env.example")

    async def test_symlink_escape(self):
        try:
            (self.root / "escape").symlink_to(self.root.parent, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink privilege unavailable")
        self.assertIn("outside", await self.tools.execute("write", {"path": "escape/escaped.txt", "content": "bad"}))

    async def test_exact_edit_preserves_crlf(self):
        path = self.root / "a.py"
        path.write_bytes(b"a = 1\r\nb = 2\r\n")
        await self.tools.execute("edit", {"path": "a.py", "old": "a = 1", "new": "a = 3"})
        self.assertEqual(path.read_bytes(), b"a = 3\r\nb = 2\r\n")

    async def test_history_roundtrip_preserves_markdown_and_tools(self):
        self.state["messages"] = [{"role": "user", "content": "## Details\n---\nKeep this"}, call("read", {"path": "a"}),
                                  {"role": "tool", "tool_call_id": "call1", "content": "value"},
                                  {"role": "assistant", "content": "done"}]
        self.store.save(self.state)
        loaded = self.store.load(self.state["id"][:10])
        self.assertEqual(self.state["messages"], loaded["messages"])

    async def test_crash_after_completed_tool_uses_journal(self):
        self.state["messages"] = [call("write", {"path": "a", "content": "x"})]
        self.state["status"] = "running"
        self.store.save(self.state)
        action = self.store.begin(self.state["id"], "call1", "write", {})
        self.store.finish(action, "Saved a")
        loaded = self.store.load("latest")
        self.assertEqual(loaded["messages"][-1]["content"], "Saved a")
        self.assertEqual(loaded["status"], "interrupted")

    async def test_unknown_side_effect_not_replayed(self):
        self.state["messages"] = [call("shell", {"command": "unknown"})]
        self.store.save(self.state)
        self.store.begin(self.state["id"], "call1", "shell", {})
        loaded = self.store.load("latest")
        self.assertIn("outcome unknown", loaded["messages"][-1]["content"])

    async def test_reused_call_id_does_not_recover_an_old_result(self):
        self.state["messages"] = [call("write", {"path": "a", "content": "a"})]
        self.store.save(self.state)
        action = self.store.begin(self.state["id"], "call1", "write", {})
        self.store.finish(action, "old result")
        self.state["messages"].extend([{"role": "tool", "tool_call_id": "call1", "content": "old result"},
                                      call("write", {"path": "b", "content": "b"})])
        self.store.save(self.state)
        self.assertIn("outcome unknown", self.store.load("latest")["messages"][-1]["content"])

    async def test_full_tool_turn_then_final_answer_is_saved(self):
        provider = FakeProvider([call("write", {"path": "hello.py", "content": "print('hello')\n"}), {"role": "assistant", "content": "Created hello.py"}])
        agent = Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None, provider)
        await agent.run("Create hello.py")
        loaded = self.store.load(self.state["id"])
        self.assertEqual((self.root / "hello.py").read_text(), "print('hello')\n")
        self.assertEqual(loaded["messages"][-1]["content"], "Created hello.py")
        self.assertEqual([m["role"] for m in loaded["messages"]], ["user", "assistant", "tool", "assistant"])

    async def test_cancel_approval_closes_tool_exchange(self):
        started = asyncio.Event()
        async def wait(*_):
            started.set()
            await asyncio.Event().wait()
        provider = FakeProvider([call("write", {"path": "a", "content": "a"})])
        agent = Agent(self.settings, self.store, self.state, wait, yes, lambda *_: None, provider)
        task = asyncio.create_task(agent.run("write"))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse((self.root / "a").exists())
        self.assertEqual(self.state["messages"][-1]["role"], "tool")
        self.assertEqual(self.state["status"], "interrupted")

    async def test_repetition_guard_stops(self):
        provider = FakeProvider([call("glob", {"pattern": "*"}, f"c{i}") for i in range(3)])
        agent = Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None, provider)
        await agent.run("look")
        self.assertEqual(self.state["status"], "blocked")

    async def test_context_trimming_preserves_full_turns(self):
        self.settings.context_chars = 2400
        self.state["messages"] = [{"role": "user", "content": "old" + "x" * 1000}, call("read", {"path": "a"}),
                                 {"role": "tool", "tool_call_id": "call1", "content": "y" * 1000},
                                 {"role": "user", "content": "new"}]
        agent = Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None, FakeProvider([]))
        context = agent.context()
        self.assertEqual(context[-1]["content"], "new")
        self.assertFalse(any(m["role"] == "tool" for m in context))
        self.assertEqual(len(self.state["messages"]), 4)

    async def test_compact_retains_archive(self):
        self.state["messages"] = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "answer"}]
        agent = Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None,
                      FakeProvider([{"role": "assistant", "content": "Summary"}]))
        await agent.compact()
        self.assertEqual(len(self.state["messages"]), 2)
        self.assertEqual(self.state["context_start"], 2)
        self.assertIn("Summary", agent.context()[0]["content"])

    async def test_shell_exit_code_and_output_limit(self):
        result = json.loads(await run_process([sys.executable, "-c", "import sys; print('x'*10000); sys.exit(7)"], self.root, limit=100))
        self.assertEqual(result["exit_code"], 7)
        self.assertIn("truncated", result["stdout"])
        self.assertLess(len(result["stdout"]), 150)

    async def test_timeout_kills_process(self):
        result = json.loads(await run_process([sys.executable, "-c", "import time; time.sleep(20)"], self.root, timeout=0.2))
        self.assertTrue(result["timed_out"])

    async def test_cancel_kills_process_before_delayed_write(self):
        task = asyncio.create_task(run_process([sys.executable, "-c", "import time,pathlib; time.sleep(2); pathlib.Path('late').write_text('bad')"], self.root))
        await asyncio.sleep(0.2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.sleep(2.1)
        self.assertFalse((self.root / "late").exists())

    async def test_config_precedence_and_validation(self):
        (self.root / "eca.toml").write_text('[agent]\nmodel="config"\nbase_url="http://localhost:1234/v1"\n', encoding="utf-8")
        with patch.dict(os.environ, {"ECA_MODEL": "environment"}, clear=True):
            self.assertEqual(Settings.load(self.root).model, "environment")
            self.assertEqual(Settings.load(self.root, model="flag").model, "flag")
        with self.assertRaises(ValueError):
            Settings.load(self.root, max_turns=0)


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def make(self, chunks):
        events = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
        async def handler(request):
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=events)
        provider = Provider(Settings(Path.cwd(), api_key="test"))
        provider.client = AsyncOpenAI(api_key="test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        return provider

    async def test_truncated_stream_is_rejected(self):
        provider = await self.make([{"choices": [{"index": 0, "delta": {"content": "partial"}, "finish_reason": None}]}])
        try:
            with self.assertRaisesRegex(RuntimeError, "Incomplete"):
                await provider.complete([], [], lambda *_: None)
        finally:
            await provider.close()

    async def test_stream_assembles_fragmented_tool_arguments(self):
        chunks = [
            {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "t1", "type": "function", "function": {"name": "read", "arguments": '{"path":'}}]}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"a.py"}'}}]}, "finish_reason": "tool_calls"}]},
        ]
        provider = await self.make(chunks)
        try:
            response, _ = await provider.complete([], [], lambda *_: None)
            self.assertEqual(json.loads(response["tool_calls"][0]["function"]["arguments"]), {"path": "a.py"})
        finally:
            await provider.close()


if __name__ == "__main__":
    unittest.main()
