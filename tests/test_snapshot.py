import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from eca import snapshot
from eca.config import Settings
from eca.tools import Tools, SKIP


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name).resolve()
        self.tools = Tools(Settings(self.root), {}, None, None, lambda *_: None)

    def tearDown(self):
        self.tmp.cleanup()

    def fingerprint(self):
        return snapshot.fingerprint(self.root, self.tools.files, self.tools.path, SKIP)

    def test_large_file_and_total_bytes_are_fully_hashed(self):
        path = self.root/'large.bin'
        with path.open('wb') as stream:
            stream.truncate(52 * 1024 * 1024)
        first = self.fingerprint()
        self.assertIsNotNone(first)
        self.assertEqual(first, self.fingerprint())
        with path.open('r+b') as stream:
            stream.seek(-1, 2)
            stream.write(b'x')
        self.assertNotEqual(first, self.fingerprint())

    def test_budget_exhaustion_never_returns_partial_fingerprint(self):
        (self.root/'one').write_bytes(b'123456789')
        with patch.object(snapshot, 'MAX_BYTES', 8):
            self.assertIsNone(self.fingerprint())
        with patch.object(snapshot, 'MAX_FILES', 0):
            self.assertIsNone(self.fingerprint())
        with patch.object(snapshot, 'MAX_SECONDS', 0):
            self.assertIsNone(self.fingerprint())

    def test_change_to_previously_hashed_file_invalidates_snapshot(self):
        first, last = self.root/'a', self.root/'z'
        first.write_bytes(b'old')
        last.write_bytes(b'last')
        original = snapshot._hash_file
        def changing(path, expected, deadline):
            result = original(path, expected, deadline)
            if path == last:
                first.write_bytes(b'changed')
            return result
        with patch.object(snapshot, '_hash_file', side_effect=changing):
            self.assertIsNone(self.fingerprint())

    def test_new_file_during_read_invalidates_snapshot(self):
        (self.root/'a').write_bytes(b'a')
        original = snapshot._hash_file
        def changing(*args):
            result = original(*args)
            (self.root/'new').write_bytes(b'new')
            return result
        with patch.object(snapshot, '_hash_file', side_effect=changing):
            self.assertIsNone(self.fingerprint())

    def test_changed_file_before_open_is_rejected(self):
        path = self.root/'a'
        path.write_bytes(b'a')
        original = snapshot._hash_file
        def changing(path, expected, deadline):
            path.write_bytes(b'changed')
            return original(path, expected, deadline)
        with patch.object(snapshot, '_hash_file', side_effect=changing):
            self.assertIsNone(self.fingerprint())

    def test_git_delete_rename_untracked_and_secret_policy(self):
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        path = self.root/'a'
        path.write_bytes(b'a')
        subprocess.run(['git', 'add', 'a'], cwd=self.root, check=True)
        first = self.fingerprint()
        (self.root/'.env').write_bytes(b'private')
        self.assertEqual(first, self.fingerprint())
        path.rename(self.root/'b')
        renamed = self.fingerprint()
        self.assertIsNotNone(renamed)
        self.assertNotEqual(first, renamed)
        (self.root/'b').unlink()
        self.assertNotEqual(renamed, self.fingerprint())

    def test_read_failure_never_validates_evidence(self):
        (self.root/'a').write_bytes(b'a')
        with patch.object(snapshot, '_hash_file', side_effect=PermissionError):
            self.assertIsNone(self.fingerprint())

    def test_windows_command_extension_has_consistent_handle_metadata(self):
        (self.root/'run.cmd').write_bytes(b'@echo hello\r\n')
        self.assertIsNotNone(self.fingerprint())

    def test_non_git_snapshot_does_not_trust_truncated_navigation_iterator(self):
        path = self.root/'a'
        path.write_bytes(b'first')
        def limited():
            return iter(())
        first = snapshot.fingerprint(self.root, limited, self.tools.path, SKIP)
        path.write_bytes(b'second')
        self.assertNotEqual(first, snapshot.fingerprint(self.root, limited, self.tools.path, SKIP))
