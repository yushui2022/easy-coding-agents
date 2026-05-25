import asyncio
from pathlib import Path

from agent_memory_core import CodingMemory
from agent_memory_core.entities import extract_entities
from agent_memory_core.retrieval import Retriever
from benchmark.memory_eval.adapters import expand_records, normalize_record
from benchmark.memory_eval.download_datasets import DATASETS
from benchmark.memory_eval.run import load_cases, render_comparison_markdown, run_suite


def run(coro):
    return asyncio.run(coro)


def test_entity_extraction_covers_coding_signals():
    entities = extract_entities(
        "class Config:\n"
        "    def load_model(self): pass\n"
        "FAILED tests/test_config.py::test_model\n"
        "Traceback\n"
        "AttributeError: missing model\n"
        "pytest tests/test_config.py -q\n",
        args={"path": "core/config.py", "cmd": "pytest tests/test_config.py -q"},
        role="tool",
    )
    by_type = {}
    for entity in entities:
        by_type.setdefault(entity["entity_type"], set()).add(entity["normalized"])

    assert "core/config.py" in by_type["file"]
    assert "load_model" in by_type["function"]
    assert "config" in by_type["class"]
    assert any("test_model" in item for item in by_type["test"])
    assert "attributeerror" in by_type["error"]
    assert "pytest tests/test_config.py -q" in by_type["command"]


def test_append_only_memory_items_and_temporal_retrieval(tmp_path: Path):
    memory = CodingMemory(project_root=str(tmp_path))
    memory.storage.insert_memory_item(
        item_id="item_old",
        item_type="Project",
        content="Project cache backend is Redis.",
        source_refs=["evt_old"],
        entities=[],
        confidence=0.7,
        goal_version=1,
    )
    memory.storage.insert_memory_item(
        item_id="item_new",
        item_type="Project",
        content="Project cache backend is SQLite.",
        source_refs=["evt_new"],
        entities=[],
        confidence=0.7,
        goal_version=3,
    )

    items = memory.storage.get_memory_items(limit=5)
    assert [item["item_id"] for item in items[:2]] == ["item_new", "item_old"]

    results = memory.retriever.retrieve("latest cache backend", limit=3)
    assert results[0].source == "memory_item"
    assert results[0].source_id == "item_new"
    assert "temporal_latest" in results[0].metadata["signals"]
    memory.storage.close()


def test_unsupported_claim_is_not_injected_as_memory_item(tmp_path: Path):
    memory = CodingMemory(project_root=str(tmp_path))

    async def scenario():
        await memory.record_assistant_message("core/config.py file defines Config without evidence.")
        rows = memory.storage.conn.execute("SELECT * FROM memory_items").fetchall()
        assert rows
        unsupported = [row for row in rows if "core/config.py" in row["content"]]
        assert unsupported
        results = memory.retriever.retrieve("core/config.py Config evidence", limit=5)
        assert all(item.source != "memory_item" for item in results)

    run(scenario())
    memory.storage.close()


def test_memory_eval_fixtures_load_and_longmemeval_thresholds():
    fixture = Path("benchmark/memory_eval/fixtures/longmemeval_lite.jsonl")
    cases = load_cases(str(fixture), limit=10)
    assert len(cases) >= 5

    result = run(
        run_suite(
            suite="longmemeval",
            baseline="evidence_gated_memory",
            dataset=str(fixture),
            limit=10,
        )
    )
    assert result["retrieval_hit_rate"] >= 0.75
    assert result["fixture_retrieval_hit_rate"] >= 0.75
    assert result["evidence_source_term_coverage"] >= 0.75
    assert all(case["context_wipe"] for case in result["cases"])
    assert result["temporal_accuracy"] >= 0.70
    assert result["abstention_accuracy"] >= 0.80
    assert result["false_fact_rate"] <= 0.10


def test_beam_lite_10k_runs_with_fast_retrieval():
    result = run(run_suite(suite="beam_lite", baseline="evidence_gated_memory", beam_tokens=10_000))
    assert result["retrieval_hit_rate"] == 1
    assert result["latency_p50"] <= 1.5


def test_baseline_comparison_markdown_renders():
    no_memory = run(run_suite(suite="longmemeval", baseline="no_memory", limit=2))
    evidence = run(run_suite(suite="longmemeval", baseline="evidence_gated_memory", limit=2))
    rendered = render_comparison_markdown([no_memory, evidence])
    assert "| baseline |" in rendered
    assert "no_memory" in rendered
    assert "evidence_gated_memory" in rendered


def test_official_longmemeval_like_record_is_normalized():
    case = normalize_record(
        {
            "question_id": "q1",
            "question_type": "knowledge-update",
            "question": "What is the current database?",
            "answer": "SQLite",
            "answer_session_ids": ["s2"],
            "haystack_sessions": [
                {
                    "session_id": "s1",
                    "date": "2026-01-01",
                    "messages": [{"role": "user", "content": "The database was Redis."}],
                },
                {
                    "session_id": "s2",
                    "date": "2026-01-02",
                    "messages": [{"role": "user", "content": "The current database is SQLite."}],
                },
            ],
        },
        suite="longmemeval",
    )
    assert case["case_id"] == "q1"
    assert case["query"] == "What is the current database?"
    assert case["expected_answer_terms"] == ["SQLite"]
    assert case["expected_evidence_terms"] == ["s2"]
    assert case["temporal_mode"] == "latest"
    assert any("session:s2" in session["content"] for session in case["sessions"])


def test_locomo_group_record_expands_to_qa_cases():
    records = expand_records(
        [
            {
                "sample_id": "conv_test",
                "qa": [
                    {
                        "question": "When did Caroline go to the support group?",
                        "answer": "7 May 2023",
                        "evidence": ["D1:3"],
                    }
                ],
                "conversation": {
                    "session_1_date_time": "1:56 pm on 8 May, 2023",
                    "session_1": [
                        {"speaker": "Caroline", "dia_id": "D1:3", "text": "I went to a support group yesterday."}
                    ],
                },
            }
        ],
        suite="locomo",
        limit=1,
    )
    case = normalize_record(records[0], suite="locomo")
    assert case["case_id"] == "conv_test_0"
    assert case["expected_answer_terms"] == ["7 May 2023"]
    assert case["expected_evidence_terms"] == ["D1:3"]
    assert len(case["sessions"]) == 1
    assert "dia_id:D1:3" in case["sessions"][0]["content"]


def test_public_dataset_download_specs_are_registered():
    assert "longmemeval_s" in DATASETS
    assert DATASETS["longmemeval_s"]["path"].endswith(".json")
    assert "locomo10" in DATASETS


def test_query_snippet_prefers_meaningful_query_terms():
    text = (
        "I need something more digital. "
        + "filler " * 80
        + "I graduated with a degree in Business Administration."
    )
    snippet = Retriever._query_snippet(text, "What degree did I graduate with?", max_chars=180)
    assert "Business Administration" in snippet
    assert not snippet.startswith("I need something more digital")
