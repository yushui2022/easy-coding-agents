from core.engine import AgentEngine
import pytest


def test_simple_answer_task_classification():
    engine = AgentEngine()
    assert engine._classify_task("请读取 requirements.txt，然后一句话总结") == "simple_answer"
    assert engine._classify_task("请读取 requirements.txt，然后用一句中文总结这个项目依赖。") == "simple_answer"
    assert engine._classify_task("requirements.txt") == "simple_answer"
    assert engine._classify_task("Explain this file briefly") == "simple_answer"
    assert engine._classify_task("请修复 memory 模块的 bug") == "coding_task"
    assert engine._classify_task("请修改 requirements.txt") == "coding_task"


def test_completion_boundary_tells_simple_tasks_to_stop_after_evidence():
    engine = AgentEngine()
    text = engine._render_completion_boundary(
        task_profile="simple_answer",
        tool_budget=3,
        tool_call_count=1,
        evidence_count=1,
        requested_files=["C:\\repo\\requirements.txt"],
    )
    assert "simple read/explain/summarize request" in text
    assert "Current-request direct evidence has already been collected" in text
    assert "Answer now" in text
    assert "one sentence" in text
    assert "plain text only" in text
    assert "requirements.txt" in text


def test_extract_requested_files_from_user_request():
    engine = AgentEngine()
    files = engine._extract_requested_files("请读取 requirements.txt，然后总结")
    assert files
    assert files[0].endswith("requirements.txt")


def test_one_sentence_request_detection():
    engine = AgentEngine()
    assert engine._is_one_sentence_request("请用一句中文总结")
    assert engine._is_one_sentence_request("Explain this briefly")
    assert not engine._is_one_sentence_request("请详细分析")


def test_one_sentence_contract_detects_markdown_table():
    engine = AgentEngine()
    answer = "标题\n\n| 包名 | 用途 |\n|---|---|\n| rich | 终端输出 |"
    assert engine._violates_one_sentence_contract(answer)
    assert not engine._violates_one_sentence_contract("这个项目依赖主要覆盖终端交互、异步文件处理、代码解析、环境变量加载和大模型 API 调用。")


def test_fallback_one_sentence_answer_removes_markdown():
    engine = AgentEngine()
    answer = "# 依赖说明\n\n| 包名 | 用途 |\n|---|---|\n总体来说，这是一个 AI 命令行编码助手项目。"
    rewritten = engine._fallback_one_sentence_answer(answer)
    assert "\n" not in rewritten
    assert "|" not in rewritten
    assert rewritten.endswith("。")


def test_quality_gate_repair_instruction_is_actionable():
    engine = AgentEngine()
    class Gate:
        violations = ["done_requires_verification"]
        blocked_reason = "done_requires_verification"
        required_actions = ["Run a relevant test/check."]

    text = engine._render_gate_repair_instruction(Gate())
    assert "QUALITY GATE BLOCKED" in text
    assert "done_requires_verification" in text
    assert "Run a relevant test/check" in text


@pytest.mark.asyncio
async def test_preload_requested_files_records_current_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "requirements.txt").write_text("openai>=1.3.0\n", encoding="utf-8")
    engine = AgentEngine()
    loaded = await engine._preload_requested_files([str(tmp_path / "requirements.txt")])
    assert loaded == 1
    messages = await engine.memory.get_context()
    rendered = "\n".join(message["content"] for message in messages)
    assert "openai>=1.3.0" in rendered
