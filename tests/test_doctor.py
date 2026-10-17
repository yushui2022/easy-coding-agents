import asyncio
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from eca.agent import Agent
from eca.cli import async_main, parser
from eca.config import Settings
from eca.doctor import diagnose
from eca.store import Store
from test_runtime import FakeProvider, yes


class DoctorTests(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get("ECA_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = asyncio.run(async_main(parser().parse_args(["--cwd", str(self.root), "--json", *args])))
        return code, json.loads(output.getvalue())

    def test_missing_key_reports_failure_without_state_creation(self):
        with patch.dict(os.environ, {}, clear=True):
            code, report = self.invoke("--doctor")
        self.assertEqual(code, 1)
        self.assertFalse(report["ready"])
        self.assertFalse(report["network_checked"])
        self.assertFalse((self.root / ".eca").exists())
        self.assertTrue(any(c["name"] == "api_key" and c["status"] == "error" for c in report["checks"]))

    def test_valid_config_never_displays_key_or_endpoint_path(self):
        with patch.dict(os.environ, {"ECA_API_KEY": "super-private", "ECA_BASE_URL": "https://example.com/private-route/v1"}, clear=True):
            code, report = self.invoke("--doctor")
        self.assertEqual(code, 0)
        self.assertEqual(report["endpoint_origin"], "https://example.com")
        self.assertNotIn("super-private", json.dumps(report))
        self.assertNotIn("private-route", json.dumps(report))

    def test_invalid_toml_is_a_diagnostic_not_a_traceback(self):
        (self.root / "eca.toml").write_text('[agent]\napi_key = "sensitive', encoding="utf-8")
        code, report = self.invoke("--doctor")
        self.assertEqual(code, 1)
        self.assertNotIn("sensitive", json.dumps(report))
        self.assertTrue(any(c["name"] == "configuration" for c in report["checks"]))

    def test_invalid_project_and_state_path(self):
        self.assertFalse(diagnose(self.root / "missing")["ready"])
        (self.root / ".eca").write_text("not a directory", encoding="utf-8")
        with patch.dict(os.environ, {"ECA_API_KEY": "fixture"}, clear=True):
            report = diagnose(self.root)
        self.assertFalse(report["ready"])
        self.assertTrue(any(c["name"] == "state_directory" and c["status"] == "error" for c in report["checks"]))

    def test_empty_session_listing_does_not_initialize_project(self):
        (self.root / "eca.toml").write_text("broken [", encoding="utf-8")
        code, rows = self.invoke("--list-sessions")
        self.assertEqual((code, rows), (0, []))
        self.assertFalse((self.root / ".eca").exists())

    def test_undo_and_session_listing_work_with_broken_configuration(self):
        store = Store(self.root)
        try:
            state = store.create()
            agent = Agent(Settings(self.root, permission="accept-edits"), store, state, yes, yes, lambda *_: None, FakeProvider([]))
            asyncio.run(agent.tools.write("new.txt", "recover me"))
            ident = agent.changes.list()[0]["id"]
        finally:
            store.close()
        (self.root / "eca.toml").write_text("broken [", encoding="utf-8")
        code, rows = self.invoke("--list-sessions")
        self.assertEqual(code, 0)
        self.assertEqual(rows[0]["id"], state["id"])
        code, event = self.invoke("--undo", str(ident))
        self.assertEqual(code, 0)
        self.assertIn("undone", event["data"])
        self.assertFalse((self.root / "new.txt").exists())

    def test_config_typos_and_invalid_types_are_rejected(self):
        for text in ('[agent]\nmax_truns=10', 'agent="bad"', '[agent]\napi_key_env=123', '[agent]\nbase_url=12'):
            with self.subTest(text=text), patch.dict(os.environ, {}, clear=True):
                (self.root / "eca.toml").write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    Settings.load(self.root)
        for url in ("https://example.com?key=secret", "https://example.com/#secret", "https://example.com:99999"):
            with self.assertRaises(ValueError):
                Settings(self.root, base_url=url).validate()

    @unittest.skipUnless(shutil.which("git"), "Git unavailable")
    def test_git_privacy_diagnostics_are_read_only(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text(".env\n.eca/\n", encoding="utf-8")
        before = subprocess.check_output(["git", "status", "--porcelain"], cwd=self.root)
        report = diagnose(self.root)
        privacy = [c for c in report["checks"] if c["name"].startswith("git_privacy")]
        self.assertEqual(len(privacy), 2)
        self.assertTrue(all(c["status"] == "ok" for c in privacy))
        self.assertEqual(subprocess.check_output(["git", "status", "--porcelain"], cwd=self.root), before)
        subprocess.run(["git", "add", "-f", ".gitignore"], cwd=self.root, check=True)
        (self.root / ".env").write_text("ECA_API_KEY=fixture", encoding="utf-8")
        subprocess.run(["git", "add", "-f", ".env"], cwd=self.root, check=True)
        report = diagnose(self.root)
        self.assertTrue(any(c["name"] == "git_privacy_.env" and c["status"] == "warning" for c in report["checks"]))
