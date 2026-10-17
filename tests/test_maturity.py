import asyncio
import json
import os
from pathlib import Path
import tempfile
import shutil
import subprocess
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from eca.agent import Agent
from eca.config import Settings
from eca.provider import Provider
from eca.store import Store
from test_runtime import FakeProvider, call, yes


class MaturityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        base = Path(os.environ.get("ECA_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.tmp.name).resolve()
        self.store = Store(self.root)
        self.state = self.store.create()
        self.settings = Settings(self.root, permission="accept-edits")
        self.agent = Agent(self.settings, self.store, self.state, yes, yes, lambda *_: None, FakeProvider([]))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    async def test_undo_restores_original_uncommitted_bytes(self):
        path = self.root / "code.py"
        original = b"# user changes\r\nx = 1\r\n"
        path.write_bytes(original)
        await self.agent.tools.edit("code.py", "x = 1", "x = 2")
        changes = self.agent.changes.list()
        ident = changes[0]["id"]
        self.assertIn("+x = 2", self.agent.changes.diff(ident))
        self.agent.changes.accept(ident)
        self.agent.changes.undo(ident)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.agent.changes.list()[0]["status"], "undone")

    @unittest.skipUnless(shutil.which("git"), "Git unavailable")
    async def test_undo_leaves_staged_git_content_unchanged(self):
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.DEVNULL)
        git("init")
        (self.root / "a").write_bytes(b"staged content\n")
        git("add", "a")
        index = git("ls-files", "--stage")
        (self.root / "a").write_bytes(b"user unstaged content\n")
        await self.agent.tools.write("a", "agent content\n")
        self.agent.changes.undo(self.agent.changes.list()[0]["id"])
        self.assertEqual((self.root / "a").read_bytes(), b"user unstaged content\n")
        self.assertEqual(git("ls-files", "--stage"), index)

    async def test_undo_refuses_newer_user_edits(self):
        await self.agent.tools.write("a", "agent")
        ident = self.agent.changes.list()[0]["id"]
        (self.root / "a").write_text("user", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "refusing"):
            self.agent.changes.undo(ident)
        self.assertEqual((self.root / "a").read_text(), "user")
        with self.assertRaises(ValueError):
            self.agent.changes.accept(ident)

    async def test_new_files_and_sequential_edits_undo_in_reverse(self):
        await self.agent.tools.write("new", "first")
        await self.agent.tools.write("new", "second")
        latest, first = [r["id"] for r in self.agent.changes.list()]
        with self.assertRaises(ValueError):
            self.agent.changes.undo(first)
        self.agent.changes.undo(latest)
        self.agent.changes.undo(first)
        self.assertFalse((self.root / "new").exists())

    async def test_snapshot_survives_restart(self):
        await self.agent.tools.write("a", "agent")
        ident = self.agent.changes.list()[0]["id"]
        self.store.close()
        self.store = Store(self.root)
        state = self.store.load(self.state["id"])
        agent = Agent(self.settings, self.store, state, yes, yes, lambda *_: None, FakeProvider([]))
        agent.changes.undo(ident)
        self.assertFalse((self.root / "a").exists())

    async def test_snapshot_is_saved_before_disk_mutation(self):
        with patch("eca.tools.atomic_write", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                await self.agent.tools.write("a", "after")
        row = self.agent.changes.list()[0]
        self.assertEqual(row["status"], "prepared")
        self.agent.changes.undo(row["id"])
        self.assertFalse((self.root / "a").exists())

    async def test_crash_after_write_before_mark_is_recoverable(self):
        ident = self.agent.changes.prepare("a", b"original", b"agent")
        (self.root / "a").write_bytes(b"agent")
        self.agent.changes.undo(ident)
        self.assertEqual((self.root / "a").read_bytes(), b"original")

    async def test_crash_during_undo_is_idempotent(self):
        ident = self.agent.changes.prepare("a", b"original", b"agent")
        self.agent.changes.mark(ident, "undoing")
        (self.root / "a").write_bytes(b"original")
        self.agent.changes.undo(ident)
        self.assertEqual(self.agent.changes.get(ident)[4], "undone")

    async def test_changes_cannot_cross_session(self):
        await self.agent.tools.write("a", "agent")
        ident = self.agent.changes.list()[0]["id"]
        other = Agent(self.settings, self.store, self.store.create(), yes, yes, lambda *_: None, FakeProvider([]))
        with self.assertRaises(ValueError):
            other.changes.undo(ident)

    async def test_auto_compact_preserves_recent_tool_group_and_archive(self):
        self.settings.context_chars = 5000
        history = [{"role": "user", "content": "Fix the bug, keep my edits"},
                   call("read", {"path": "a"}, "old"), {"role": "tool", "tool_call_id": "old", "content": "x" * 4000},
                   call("read", {"path": "b"}, "recent"), {"role": "tool", "tool_call_id": "recent", "content": "last result"}]
        self.state["messages"] = history.copy()
        provider = self.agent.provider = FakeProvider([{"role": "assistant", "content": "Goal: fix bug, keep user edits. Read a; no tests yet."}])
        await self.agent._compact(automatic=True)
        context = self.agent.context()
        self.assertEqual(self.state["messages"], history)
        self.assertEqual(self.state["context_start"], 3)
        self.assertEqual([m["role"] for m in context], ["system", "user", "assistant", "tool"])
        self.assertEqual(context[1]["content"], history[0]["content"])
        self.assertEqual(context[-1]["tool_call_id"], "recent")
        self.assertEqual(provider.contexts[0][1], [])

    async def test_run_auto_compacts_before_request(self):
        self.settings.context_chars = 5000
        self.state["messages"] = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "x" * 4000}]
        self.agent.provider = FakeProvider([{"role": "assistant", "content": "Previous work summary"},
                                            {"role": "assistant", "content": "done"}])
        await self.agent.run("continue")
        self.assertEqual(self.state["status"], "idle")
        self.assertEqual(self.state["context_start"], 2)
        self.assertEqual(len(self.state["messages"]), 4)

    async def test_failed_summary_does_not_discard_history(self):
        self.state["messages"] = [{"role": "user", "content": "goal"}]
        self.agent.provider = FakeProvider([RuntimeError("summary failed")])
        with self.assertRaises(RuntimeError):
            await self.agent.compact()
        self.assertNotIn("context_start", self.state)
        self.assertEqual(len(self.state["messages"]), 1)

    async def test_error_reason_is_persisted_without_error_body(self):
        self.agent.provider = FakeProvider([RuntimeError("secret-sensitive-error-body")])
        with self.assertRaises(RuntimeError):
            await self.agent.run("task")
        saved = self.store.load(self.state["id"])
        self.assertIn("/continue", saved["stop_reason"])
        self.assertNotIn("secret-sensitive", json.dumps(saved))


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_failure_retries_without_duplicate_tool_execution(self):
        provider = Provider(Settings(Path.cwd()))
        response = (call("write", {"path": "a", "content": "a"}), {})
        provider._complete = AsyncMock(side_effect=[httpx.ConnectError("offline"), response])
        notices = []
        with patch("eca.provider.asyncio.sleep", new_callable=AsyncMock) as wait:
            result = await provider.complete([], [], lambda *e: notices.append(e))
        self.assertEqual(result, response)
        self.assertEqual(provider._complete.await_count, 2)
        wait.assert_awaited_once_with(1)
        self.assertIn("Retry 1/2", notices[0][1])

    async def test_partial_text_is_not_automatically_replayed(self):
        provider = Provider(Settings(Path.cwd()))
        async def partial(messages, tools, emit):
            emit("text", "partial")
            raise httpx.ReadError("disconnected")
        provider._complete = AsyncMock(side_effect=partial)
        with self.assertRaises(httpx.ReadError):
            await provider.complete([], [], lambda *_: None)
        self.assertEqual(provider._complete.await_count, 1)

    async def test_retry_limit_and_permanent_failure(self):
        provider = Provider(Settings(Path.cwd(), network_retries=1))
        provider._complete = AsyncMock(side_effect=httpx.ConnectError("offline"))
        with patch("eca.provider.asyncio.sleep", new_callable=AsyncMock), self.assertRaises(httpx.ConnectError):
            await provider.complete([], [], lambda *_: None)
        self.assertEqual(provider._complete.await_count, 2)
        provider._complete = AsyncMock(side_effect=ValueError("invalid key"))
        with self.assertRaises(ValueError):
            await provider.complete([], [], lambda *_: None)
        self.assertEqual(provider._complete.await_count, 1)

    async def test_backoff_can_be_cancelled(self):
        provider = Provider(Settings(Path.cwd()))
        provider._complete = AsyncMock(side_effect=httpx.ConnectError("offline"))
        started = asyncio.Event()
        task = asyncio.create_task(provider.complete([], [], lambda *_: started.set()))
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(provider._complete.await_count, 1)
