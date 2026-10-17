import asyncio
from pathlib import Path

from benchmark.coding_memory.run import load_dataset, run_evidence_gated_memory


def test_swe_bench_fixture_loads():
    fixture = Path("benchmark/coding_memory/fixtures/swe_bench_mini.jsonl")
    tasks = load_dataset(str(fixture), limit=1)
    assert len(tasks) == 1
    assert tasks[0]["instance_id"] == "django__django-00001"
    assert "FAIL_TO_PASS" in tasks[0]


def test_swe_bench_memory_probe_runs_on_fixture():
    fixture = Path("benchmark/coding_memory/fixtures/swe_bench_mini.jsonl")
    tasks = load_dataset(str(fixture), limit=2)
    result = asyncio.run(run_evidence_gated_memory(tasks=tasks, suite="swe_bench_memory"))
    assert result["suite"] == "swe_bench_memory"
    assert result["task_count"] == 2
    assert result["false_done_rate"] == 0
    assert result["state_gate_block_rate"] == 1
    predictions = Path("benchmark/coding_memory/results/swe_bench_predictions.jsonl")
    assert predictions.exists()
