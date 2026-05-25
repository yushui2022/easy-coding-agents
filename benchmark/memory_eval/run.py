import argparse
import asyncio
import json
import shutil
import sys
import time
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_memory_core import CodingMemory
from benchmark.memory_eval.adapters import normalize_record

RESULTS_DIR = Path(__file__).resolve().parent / "results"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

BASELINES = [
    "no_memory",
    "summary_memory",
    "rag_fts_memory",
    "entity_temporal_memory",
    "evidence_gated_memory",
]
SUITES = ["longmemeval", "locomo_lite", "beam_lite"]


async def run_suite(
    suite: str,
    baseline: str,
    dataset: Optional[str] = None,
    limit: int = 20,
    beam_tokens: int = 100_000,
) -> Dict[str, Any]:
    if suite == "beam_lite":
        return await run_beam_lite(baseline=baseline, beam_tokens=beam_tokens)

    cases = load_cases(dataset or default_fixture(suite), limit=limit)
    workspace_name = f".agent_memory_eval_{suite}_{baseline}"
    reset_dir(ROOT / workspace_name)
    case_results = []
    for index, case in enumerate(cases):
        case_results.append(await run_case(case, baseline, workspace_name, index))
    return summarize_results(suite, baseline, case_results)


async def run_case(
    case: Dict[str, Any],
    baseline: str,
    workspace_name: str,
    index: int,
) -> Dict[str, Any]:
    memory: Optional[CodingMemory] = None
    workspace = f"{workspace_name}/case_{index}"
    if baseline in {"rag_fts_memory", "entity_temporal_memory", "evidence_gated_memory"}:
        memory = CodingMemory(
            project_root=str(ROOT),
            workspace=workspace,
            offload_threshold_chars=500,
            recent_dialogue_limit=6,
        )
        await ingest_case(memory, case)
        memory.storage.close()
        memory = CodingMemory(
            project_root=str(ROOT),
            workspace=workspace,
            offload_threshold_chars=500,
            recent_dialogue_limit=0,
        )

    query = str(case.get("query") or "")
    started = time.perf_counter()
    if baseline == "no_memory":
        prompt = query
        retrieved: List[Dict[str, Any]] = []
    elif baseline == "summary_memory":
        prompt = render_summary_prompt(case)
        retrieved = []
    elif baseline == "rag_fts_memory":
        assert memory is not None
        rows = memory.storage.search(query, limit=8)
        retrieved = [normalize_retrieved_row(row) for row in rows]
        prompt = render_rows_prompt("FTS Memory Results", retrieved)
    elif baseline == "entity_temporal_memory":
        assert memory is not None
        rows = memory.retriever.retrieve(query, limit=8)
        retrieved = [item.__dict__ for item in rows]
        prompt = render_rows_prompt("Entity Temporal Memory Results", retrieved)
    else:
        assert memory is not None
        messages = await memory.build_prompt_context(query)
        prompt = "\n".join(str(message.get("content") or "") for message in messages)
        retrieved = last_selected_results(memory)
    latency = time.perf_counter() - started

    if memory is not None:
        memory.storage.close()

    expected_answer_terms = [str(item) for item in case.get("expected_answer_terms") or []]
    expected_evidence_terms = [str(item) for item in case.get("expected_evidence_terms") or []]
    expected_entities = [str(item) for item in case.get("expected_entities") or []]
    should_abstain = bool(case.get("should_abstain"))
    answer_hit = term_coverage(prompt, expected_answer_terms)
    evidence_hit = term_coverage(prompt, expected_evidence_terms)
    entity_hit = term_coverage(prompt, expected_entities)
    has_false_fact = should_abstain and any_term(prompt, expected_answer_terms)

    return {
        "case_id": case.get("case_id") or f"case_{index}",
        "retrieval_hit": 0 if has_false_fact else answer_hit,
        "term_recall": 0 if has_false_fact else answer_hit,
        "evidence_precision": evidence_hit,
        "expected_evidence_term_coverage": evidence_hit,
        "temporal_accuracy": answer_hit if case.get("temporal_mode") != "none" else None,
        "entity_link_hit": entity_hit,
        "abstention_accuracy": int(not has_false_fact) if should_abstain else 1,
        "source_coverage": source_coverage(retrieved, should_abstain=should_abstain),
        "source_ref_coverage": source_coverage(retrieved, should_abstain=should_abstain),
        "input_tokens": estimate_tokens(prompt),
        "latency": latency,
        "false_fact": int(has_false_fact),
        "retrieved_count": len(retrieved),
        "context_wipe": baseline in {"rag_fts_memory", "entity_temporal_memory", "evidence_gated_memory"},
        "retrieved_results": compact_retrieved(retrieved),
    }


async def ingest_case(memory: CodingMemory, case: Dict[str, Any]) -> None:
    for session in case.get("sessions") or []:
        role = str(session.get("role") or "user")
        content = str(session.get("content") or "")
        metadata = session.get("metadata") or {}
        if role == "user":
            await memory.record_user_message(content)
        elif role == "assistant":
            await memory.record_assistant_message(content, tool_calls=metadata.get("tool_calls"))
        elif role == "tool":
            await memory.record_tool_result(
                metadata.get("name") or "bash",
                metadata.get("args") or {},
                content,
            )


async def run_beam_lite(baseline: str, beam_tokens: int = 100_000) -> Dict[str, Any]:
    query = "latest BEAM target anchor beam_fact_42"
    expected = ["beam_fact_42", "final chunk keeps the target memory"]
    workspace_name = f".agent_memory_eval_beam_lite_{baseline}"
    reset_dir(ROOT / workspace_name)

    if baseline == "no_memory":
        prompt = query
        return summarize_results(
            "beam_lite",
            baseline,
            [single_beam_result(prompt, expected, latency=0.0, retrieved=[])],
        )
    if baseline == "summary_memory":
        prompt = "Summary: a long synthetic memory stream was processed."
        return summarize_results(
            "beam_lite",
            baseline,
            [single_beam_result(prompt, expected, latency=0.0, retrieved=[])],
        )

    memory = CodingMemory(
        project_root=str(ROOT),
        workspace=workspace_name,
        offload_threshold_chars=700,
        recent_dialogue_limit=4,
    )
    await memory.record_user_message("Run BEAM-lite synthetic scale memory test.")
    chunk_tokens = 1_000
    chunks = max(1, beam_tokens // chunk_tokens)
    filler_line = "beam filler token stream for retrieval stress and latency tracking\n"
    for index in range(chunks):
        target = ""
        if index == chunks - 1:
            target = "beam_fact_42: final chunk keeps the target memory for latest retrieval.\n"
        body = target + (filler_line * 70)
        await memory.record_tool_result(
            "read",
            {"path": f"beam/chunk_{index:05d}.md"},
            body,
        )
    memory.storage.close()
    memory = CodingMemory(
        project_root=str(ROOT),
        workspace=workspace_name,
        offload_threshold_chars=700,
        recent_dialogue_limit=0,
    )

    prompts = []
    latencies = []
    retrieved_rows: List[Dict[str, Any]] = []
    for _ in range(5):
        started = time.perf_counter()
        if baseline == "rag_fts_memory":
            rows = memory.storage.search(query, limit=8)
            retrieved_rows = [normalize_retrieved_row(row) for row in rows]
            prompt = render_rows_prompt("FTS Memory Results", retrieved_rows)
        elif baseline == "entity_temporal_memory":
            rows = memory.retriever.retrieve(query, limit=8)
            retrieved_rows = [item.__dict__ for item in rows]
            prompt = render_rows_prompt("Entity Temporal Memory Results", retrieved_rows)
        else:
            messages = await memory.build_prompt_context(query)
            prompt = "\n".join(str(message.get("content") or "") for message in messages)
            retrieved_rows = last_selected_results(memory)
        latencies.append(time.perf_counter() - started)
        prompts.append(prompt)
    memory.storage.close()

    result = single_beam_result(
        "\n".join(prompts[-1:]),
        expected,
        latency=median(latencies),
        retrieved=retrieved_rows,
    )
    result["input_tokens"] = estimate_tokens(prompts[-1])
    result["beam_tokens"] = beam_tokens
    result["latency_samples"] = latencies
    return summarize_results("beam_lite", baseline, [result])


def single_beam_result(
    prompt: str,
    expected_terms: List[str],
    latency: float,
    retrieved: List[Dict[str, Any]],
) -> Dict[str, Any]:
    hit = term_coverage(prompt, expected_terms)
    return {
        "case_id": "beam_lite_synthetic",
        "retrieval_hit": hit,
        "term_recall": hit,
        "evidence_precision": hit,
        "expected_evidence_term_coverage": hit,
        "temporal_accuracy": hit,
        "entity_link_hit": 1,
        "abstention_accuracy": 1,
        "source_coverage": source_coverage(retrieved),
        "source_ref_coverage": source_coverage(retrieved),
        "input_tokens": estimate_tokens(prompt),
        "latency": latency,
        "false_fact": 0 if hit else 1,
        "retrieved_count": len(retrieved),
        "context_wipe": True,
        "retrieved_results": compact_retrieved(retrieved),
    }


def summarize_results(suite: str, baseline: str, case_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    temporal_values = [item["temporal_accuracy"] for item in case_results if item["temporal_accuracy"] is not None]
    latencies = [float(item["latency"]) for item in case_results]
    result = {
        "suite": suite,
        "baseline": baseline,
        "task_count": len(case_results),
        "fixture_retrieval_hit_rate": rounded_mean(item["retrieval_hit"] for item in case_results),
        "term_recall_rate": rounded_mean(item["term_recall"] for item in case_results),
        "retrieval_hit_rate": rounded_mean(item["retrieval_hit"] for item in case_results),
        "expected_evidence_term_coverage": rounded_mean(
            item["expected_evidence_term_coverage"] for item in case_results
        ),
        "evidence_precision": rounded_mean(item["evidence_precision"] for item in case_results),
        "temporal_accuracy": rounded_mean(temporal_values) if temporal_values else 1.0,
        "entity_link_hit_rate": rounded_mean(item["entity_link_hit"] for item in case_results),
        "abstention_accuracy": rounded_mean(item["abstention_accuracy"] for item in case_results),
        "source_ref_coverage": rounded_mean(item["source_ref_coverage"] for item in case_results),
        "source_coverage": rounded_mean(item["source_coverage"] for item in case_results),
        "input_tokens": int(sum(int(item["input_tokens"]) for item in case_results)),
        "latency_p50": round(median(latencies), 4) if latencies else 0.0,
        "false_fact_rate": rounded_mean(item["false_fact"] for item in case_results),
        "cases": case_results,
    }
    return result


def render_summary_prompt(case: Dict[str, Any]) -> str:
    sessions = case.get("sessions") or []
    snippets = [str(item.get("content") or "").strip() for item in sessions[-2:]]
    return "Summary Memory:\n" + "\n".join(snippet[:220] for snippet in snippets if snippet)


def render_rows_prompt(title: str, rows: List[Dict[str, Any]]) -> str:
    lines = [title]
    if not rows:
        lines.append("- No retrieved evidence.")
    for row in rows:
        source = row.get("source") or "unknown"
        source_id = row.get("source_id") or row.get("id") or ""
        summary = row.get("summary") or row.get("content") or ""
        lines.append(f"- [{source}:{source_id}] {summary}")
    return "\n".join(lines)


def normalize_retrieved_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source": row.get("source"),
        "source_id": row.get("source_id"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "score": row.get("score"),
        "metadata": row.get("metadata") or {},
    }


def compact_retrieved(rows: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    compact = []
    for row in rows[:limit]:
        metadata = row.get("metadata") or {}
        compact.append(
            {
                "source": row.get("source"),
                "source_id": row.get("source_id"),
                "title": row.get("title"),
                "summary": str(row.get("summary") or "")[:500],
                "score": row.get("score"),
                "signals": metadata.get("signals") or {},
                "source_refs": metadata.get("source_refs") or [],
            }
        )
    return compact


def last_selected_results(memory: CodingMemory) -> List[Dict[str, Any]]:
    row = memory.storage.conn.execute(
        "SELECT selected_results FROM retrieval_logs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return []
    try:
        return json.loads(row["selected_results"])
    except Exception:
        return []


def source_coverage(rows: List[Dict[str, Any]], should_abstain: bool = False) -> float:
    if not rows:
        return 1.0 if should_abstain else 0.0
    supported = 0
    for row in rows:
        source = str(row.get("source") or "")
        source_id = str(row.get("source_id") or "")
        metadata = row.get("metadata") or {}
        if source in {"ref", "event"}:
            supported += 1
        elif source_id.startswith(("refs/ref_", "evt_")):
            supported += 1
        elif metadata.get("source_refs"):
            supported += 1
    return supported / len(rows)


def term_coverage(text: str, terms: List[str]) -> int:
    if not terms:
        return 1
    lowered = text.lower()
    return int(all(term.lower() in lowered for term in terms))


def any_term(text: str, terms: List[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def estimate_tokens(text: str) -> int:
    return max(1, len(str(text or "")) // 4)


def rounded_mean(values: Any) -> float:
    items = [float(item) for item in values]
    return round(mean(items), 3) if items else 0.0


def load_cases(path: str, limit: int = 20) -> List[Dict[str, Any]]:
    dataset_path = Path(path)
    text = dataset_path.read_text(encoding="utf-8")
    if dataset_path.suffix.lower() == ".jsonl":
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        loaded = json.loads(text)
        records = loaded if isinstance(loaded, list) else loaded.get("cases", [])
    return [normalize_record(record, suite=dataset_path.stem, index=index) for index, record in enumerate(records[:limit])]


def default_fixture(suite: str) -> str:
    if suite == "longmemeval":
        return str(FIXTURES_DIR / "longmemeval_lite.jsonl")
    if suite == "locomo_lite":
        return str(FIXTURES_DIR / "locomo_lite.jsonl")
    raise ValueError(f"No fixture for suite: {suite}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [f"# Memory Eval: {result['suite']} / {result['baseline']}", ""]
    for key, value in result.items():
        if key == "cases":
            continue
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    lines.append("## Cases")
    for case in result.get("cases") or []:
        lines.append(
            f"- `{case['case_id']}`: hit={case['retrieval_hit']} "
            f"evidence={case['evidence_precision']} temporal={case['temporal_accuracy']} "
            f"tokens={case['input_tokens']} latency={case['latency']:.4f}s"
        )
    lines.append("")
    return "\n".join(lines)


def write_artifacts(result: Dict[str, Any], name: str, args: argparse.Namespace) -> None:
    artifact_dir = RESULTS_DIR / name
    artifact_dir.mkdir(parents=True, exist_ok=True)
    cases = result.get("cases") or []
    (artifact_dir / "metrics.json").write_text(
        json.dumps({key: value for key, value in result.items() if key != "cases"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (artifact_dir / "cases.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in cases) + ("\n" if cases else ""),
        encoding="utf-8",
    )
    (artifact_dir / "predictions.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "case_id": item["case_id"],
                    "hypothesis": "",
                    "memory_only": True,
                    "term_recall": item.get("term_recall"),
                    "retrieval_hit": item.get("retrieval_hit"),
                    "source_ref_coverage": item.get("source_ref_coverage"),
                    "input_tokens": item.get("input_tokens"),
                },
                ensure_ascii=False,
            )
            for item in cases
        )
        + ("\n" if cases else ""),
        encoding="utf-8",
    )
    (artifact_dir / "retrieval_logs.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "case_id": item["case_id"],
                    "retrieved_count": item.get("retrieved_count"),
                    "retrieved_results": item.get("retrieved_results") or [],
                },
                ensure_ascii=False,
            )
            for item in cases
        )
        + ("\n" if cases else ""),
        encoding="utf-8",
    )
    failures = [
        item
        for item in cases
        if not item.get("retrieval_hit")
        or not item.get("evidence_precision")
        or item.get("false_fact")
        or item.get("abstention_accuracy") == 0
    ]
    (artifact_dir / "failures.md").write_text(render_failures(failures), encoding="utf-8")
    (artifact_dir / "run_config.json").write_text(
        json.dumps(vars(args), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def render_failures(failures: List[Dict[str, Any]]) -> str:
    lines = ["# Memory Eval Failures", ""]
    if not failures:
        lines.append("No failures under the current term-level regression checks.")
        lines.append("")
        return "\n".join(lines)
    for item in failures:
        lines.append(f"## {item['case_id']}")
        lines.append(f"- retrieval_hit: {item.get('retrieval_hit')}")
        lines.append(f"- evidence_precision: {item.get('evidence_precision')}")
        lines.append(f"- abstention_accuracy: {item.get('abstention_accuracy')}")
        lines.append(f"- false_fact: {item.get('false_fact')}")
        lines.append("")
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=SUITES, default="longmemeval")
    parser.add_argument("--baseline", choices=BASELINES, default="evidence_gated_memory")
    parser.add_argument("--dataset", help="Path to a memory_eval JSONL/JSON dataset.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--beam-tokens", type=int, default=100_000)
    args = parser.parse_args()

    result = await run_suite(
        suite=args.suite,
        baseline=args.baseline,
        dataset=args.dataset,
        limit=args.limit,
        beam_tokens=args.beam_tokens,
    )
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{args.suite}_{args.baseline}"
    json_path = RESULTS_DIR / f"{name}_result.json"
    md_path = RESULTS_DIR / f"{name}_result.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    write_artifacts(result, name, args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
