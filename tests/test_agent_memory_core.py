import asyncio
from pathlib import Path

from agent_memory_core import CodingMemory


def run(coro):
    return asyncio.run(coro)


def test_tool_result_is_offloaded_and_retrievable(tmp_path: Path):
    memory = CodingMemory(project_root=str(tmp_path), offload_threshold_chars=80)

    async def scenario():
        await memory.record_user_message("Fix the memory module bug in memory/__init__.py")
        result = await memory.record_tool_result(
            "bash",
            {"cmd": "pytest tests/test_memory.py"},
            "FAILED tests/test_memory.py::test_au2\nTraceback\nAttributeError: 'str' object has no attribute 'get'\n"
            + ("extra log\n" * 30),
            tool_call_id="call_1",
        )
        assert result["result_ref"].startswith("refs/ref_")
        assert (tmp_path / ".agent_memory" / result["result_ref"]).exists()
        context = await memory.build_prompt_context("AttributeError au2_data get")
        rendered = "\n".join(msg["content"] for msg in context)
        assert "[Offloaded Tool Result]" in rendered
        assert result["result_ref"] in rendered
        assert "AttributeError" in rendered

    run(scenario())


def test_quality_gate_rejects_unsupported_claim_and_false_done(tmp_path: Path):
    memory = CodingMemory(project_root=str(tmp_path))

    async def scenario():
        unsupported = await memory.check_quality_gate(
            {
                "claims": [
                    {
                        "text": "memory/__init__.py calls au2_data.get",
                        "type": "file_content",
                        "evidence_refs": [],
                    }
                ]
            }
        )
        assert not unsupported.accepted
        assert "file_claim_requires_read" in unsupported.violations

        false_done = await memory.check_quality_gate({"to": "DONE", "evidence_refs": []})
        assert not false_done.accepted
        assert "done_requires_verification" in false_done.violations

        allowed = await memory.check_quality_gate(
            {
                "to": "DONE",
                "evidence_refs": ["refs/ref_test_passed.md"],
                "claims": [
                    {
                        "text": "Tests passed",
                        "type": "test_failure",
                        "evidence_refs": ["refs/ref_test_passed.md"],
                    }
                ],
            }
        )
        assert allowed.accepted

    run(scenario())


def test_task_map_and_session_snapshot(tmp_path: Path):
    memory = CodingMemory(project_root=str(tmp_path))

    async def scenario():
        await memory.record_user_message("Implement evidence gated memory")
        await memory.record_tool_result("read", {"path": "memory/__init__.py"}, "1| class MemoryManager:\n")
        await memory.record_tool_result("edit", {"path": "memory/__init__.py"}, "Successfully edited file.")
        nodes = memory.storage.get_task_nodes(limit=5)
        assert nodes[-2]["node_type"] == "evidence"
        assert nodes[-1]["node_type"] == "change"
        assert nodes[-1]["is_current_focus"]
        path = await memory.save_session()
        session = Path(path)
        assert session.exists()
        text = session.read_text(encoding="utf-8")
        assert "Evidence-Gated Memory Session" in text
        assert "flowchart TD" in text
        assert "memory/__init__.py" in text

    run(scenario())


def test_assistant_claims_are_extracted_with_recent_evidence(tmp_path: Path):
    memory = CodingMemory(project_root=str(tmp_path))

    async def scenario():
        tool = await memory.record_tool_result(
            "read",
            {"path": "core/config.py"},
            "1| class Config:\n2|     LLM_PROVIDER = 'deepseek'\n",
        )
        await memory.record_assistant_message("core/config.py 文件中 Config 类负责读取模型提供商配置。")
        rows = memory.storage.conn.execute("SELECT * FROM claims").fetchall()
        assert rows
        row = dict(rows[0])
        assert row["claim_type"] == "file_content"
        assert tool["result_ref"] in row["evidence_refs"]

    run(scenario())


def test_final_answer_gate_blocks_false_done_without_verification(tmp_path: Path):
    memory = CodingMemory(project_root=str(tmp_path))

    async def scenario():
        await memory.record_tool_result("edit", {"path": "core/config.py"}, "Successfully edited file.")
        gate = memory.validate_final_answer("已完成修复，测试通过。", task_profile="coding_task")
        assert not gate.accepted
        assert "done_requires_verification" in gate.violations

        gate = memory.validate_final_answer("已完成修改，但没有运行测试，原因是用户只要求静态调整。", task_profile="coding_task")
        assert gate.accepted

    run(scenario())


def test_test_success_allows_done_gate(tmp_path: Path):
    memory = CodingMemory(project_root=str(tmp_path))

    async def scenario():
        await memory.record_tool_result("bash", {"cmd": "pytest tests -q"}, "12 passed in 2.5s")
        gate = memory.validate_final_answer("已完成修复，测试通过。", task_profile="coding_task")
        assert gate.accepted

    run(scenario())


def test_state_transition_requires_evidence(tmp_path: Path):
    memory = CodingMemory(project_root=str(tmp_path))

    async def scenario():
        blocked = await memory.propose_state_transition(
            {
                "to": "DEBUGGING",
                "reason": "pytest failed",
                "evidence_refs": [],
            }
        )
        assert not blocked.accepted
        assert "state_transition_requires_evidence" in blocked.violations

        tool = await memory.record_tool_result("bash", {"cmd": "pytest"}, "FAILED test_x\nTraceback\nAssertionError")
        allowed = await memory.propose_state_transition(
            {
                "to": "DEBUGGING",
                "reason": "pytest failed",
                "evidence_refs": [tool["result_ref"]],
            }
        )
        assert allowed.accepted
        state = memory.storage.get_task_state()
        assert state["state"] == "DEBUGGING"
        state_events = memory.storage.get_recent_events(limit=10, roles=["system"])
        assert any(event["kind"] == "state" for event in state_events)

    run(scenario())


def test_retriever_prioritizes_focus_and_failure_refs(tmp_path: Path):
    memory = CodingMemory(project_root=str(tmp_path))

    async def scenario():
        file_ref = await memory.record_tool_result(
            "read",
            {"path": "core/config.py"},
            "class Config:\n    MODEL_NAME = 'deepseek-v4-flash'\n",
        )
        failure_ref = await memory.record_tool_result(
            "bash",
            {"cmd": "pytest tests/test_config.py"},
            "FAILED tests/test_config.py\nTraceback\nAssertionError: model mismatch\n",
        )
        results = memory.retriever.retrieve("pytest failed model mismatch core/config.py", limit=5)
        ids = [item.source_id for item in results]
        assert failure_ref["result_ref"] in ids[:2]
        assert file_ref["result_ref"] in ids
        assert results[0].score >= results[-1].score

    run(scenario())
