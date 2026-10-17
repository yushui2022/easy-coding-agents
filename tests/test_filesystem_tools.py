from pathlib import Path

import pytest

from tools.filesystem import read_file


@pytest.mark.asyncio
async def test_read_file_falls_back_to_cwd_basename(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "requirements.txt").write_text("openai>=1.3.0\n", encoding="utf-8")
    result = await read_file(r"C:\wrong\place\requirements.txt")
    assert "openai>=1.3.0" in result

