"""Filesystem failures must reach the user as a sentence, not as an errno."""
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eca import attachments, fsguard, tools
from eca.config import Settings


def failing(code):
    return OSError(code, os.strerror(code), 'G:\\Projects\\demo\\.eca')


class Messages(unittest.TestCase):
    def test_a_full_disk_names_space_not_the_path(self):
        text = fsguard.describe(failing(errno.ENOSPC), '写入文件')
        self.assertIn('磁盘空间不足', text)
        self.assertIn('G:\\Projects\\demo\\.eca', text)
        self.assertIn('释放', text)
        self.assertNotIn('Errno 28', text)

    def test_permission_and_read_only_are_distinct(self):
        self.assertIn('没有权限', fsguard.describe(failing(errno.EACCES)))
        self.assertIn('只读', fsguard.describe(failing(errno.EROFS)))
        self.assertIn('路径不存在', fsguard.describe(failing(errno.ENOENT)))

    def test_an_unknown_error_still_says_it_is_not_the_task(self):
        text = fsguard.describe(OSError(errno.EIO, 'device error'))
        self.assertIn('不是模型或任务的问题', text)

    def test_an_explicit_target_wins_over_the_exception_path(self):
        self.assertIn('目标文件.txt', fsguard.describe(failing(errno.ENOSPC), '写入', '目标文件.txt'))


class Writes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_atomic_write_explains_a_full_disk(self):
        with patch('os.replace', side_effect=failing(errno.ENOSPC)):
            with self.assertRaisesRegex(ValueError, '磁盘空间不足'):
                tools.atomic_write(self.root / 'a.txt', 'x')

    def test_an_image_attachment_says_the_disk_is_full(self):
        import base64
        raw = b'\x89PNG\r\n\x1a\n' + b'0' * 32
        values = [{'name': 'shot.png', 'mime': 'image/png', 'data': base64.b64encode(raw).decode()}]
        with patch.object(Path, 'write_bytes', side_effect=failing(errno.ENOSPC)):
            with self.assertRaisesRegex(ValueError, '磁盘空间不足'):
                attachments.prepare(self.root, values)

    def test_a_tool_failure_reaches_the_model_as_a_sentence(self):
        settings = Settings(self.root)
        settings.mode = 'code'
        async def boom(path):
            raise failing(errno.EACCES)
        harness = tools.Tools(settings, {}, None, None, lambda *_: None)
        harness.read = boom
        import asyncio
        result = asyncio.run(harness.execute('read', {'path': 'x.txt'}))
        self.assertTrue(result.startswith('Error: 读取失败') or result.startswith('Error: 写入失败'), result)
        self.assertIn('没有权限', result)

    def test_opening_a_project_on_a_full_disk_is_explained(self):
        from eca import store
        with patch('sqlite3.connect', side_effect=failing(errno.ENOSPC)):
            with self.assertRaisesRegex(ValueError, '磁盘空间不足'):
                store.Store(self.root)


if __name__ == '__main__':
    unittest.main()
