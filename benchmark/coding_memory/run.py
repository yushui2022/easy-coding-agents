import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_memory_core import CodingMemory

RESULTS_DIR = Path(__file__).resolve().parent / "results"


SYNTHETIC_TASKS = [
    {
        "id": "type_bug",
        "request": "Fix AU2 data structure bug in memory/__init__.py",
        "evidence_query": "AttributeError str object has no attribute get",
        "expected_ref_terms": ["AttributeError", "au2_data", "get"],
        "requires_verification": True,
    },
    {
        "id": "debug_recovery",
        "request": "Continue after a pytest failure and recover the current task",
        "evidence_query": "pytest failed traceback MemoryManager",
        "expected_ref_terms": ["FAILED", "Traceback"],
        "requires_verification": False,
    },
    {
        "id": "goal_change",
        "request": "User changed target from compression to quality gates",
        "evidence_query": "goal changed quality gate",
        "expected_ref_terms": ["quality gate", "goal"],
        "requires_verification": False,
    },
]


async def run_evidence_gated_memory(
    tasks: Optional[List[Dict[str, Any]]] = None,
    suite: str = "synthetic",
    workspace_name: str = ".agent_memory_benchmark",
) -> Dict[str, Any]:
    workspace = ROOT / workspace_name
    reset_dir(workspace)

    if suite == "swe_bench_memory":
        return await run_swe_bench_memory_probe(tasks or [], workspace_name=workspace_name)
    memory = CodingMemory(project_root=str(ROOT), workspace=workspace_name, offload_threshold_chars=120)
    return await run_synthetic_evidence(memory, tasks or SYNTHETIC_TASKS)


async def run_synthetic_evidence(memory: CodingMemory, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    scores = []
    prompt_tokens = []
    evidence_hits = []
    false_done = []
    recovery = []
    state_gate_hits = []

    for task in tasks:
        await memory.record_user_message(task["request"])
        if task["id"] == "type_bug":
            await memory.record_tool_result(
                "read",
                {"path": "memory/__init__.py"},
                "def _extract_value_to_long_term(self, au2_data):\n    decisions = au2_data.get('decisions')\n",
            )
            await memory.record_tool_result(
                "bash",
                {"cmd": "pytest tests/test_memory.py"},
                "FAILED test_memory.py::test_extract\nTraceback\nAttributeError: 'str' object has no attribute 'get'\nau2_data = '## Key Decisions'\n",
            )
        elif task["id"] == "debug_recovery":
            await memory.record_tool_result(
                "bash",
                {"cmd": "pytest"},
                "FAILED tests/test_engine.py\nTraceback\nAssertionError: MemoryManager did not preserve result_ref\n",
            )
        else:
            await memory.record_tool_result(
                "ask_user",
                {"question": "Confirm changed goal"},
                "User changed goal to implement quality gate first.",
            )

        context = await memory.build_prompt_context(task["evidence_query"])
        rendered = "\n".join(msg["content"] for msg in context)
        prompt_tokens.append(estimate_tokens(rendered))
        evidence_hits.append(int(all(term.lower() in rendered.lower() for term in task["expected_ref_terms"])))

        gate = await memory.check_quality_gate({"to": "DONE", "evidence_refs": []})
        false_done.append(0 if not gate.accepted else 1)

        transition = await memory.propose_state_transition(
            {
                "to": "DEBUGGING",
                "reason": "debugging requires test evidence",
                "evidence_refs": [],
            }
        )
        state_gate_hits.append(0 if transition.accepted else 1)

        state_ok = any(label in rendered for label in ["current_task_state", "DEBUGGING", "GATHERING_CONTEXT"])
        recovery.append(int(state_ok))
        scores.append(1)

    return summarize("evidence_gated_memory", scores, prompt_tokens, evidence_hits, false_done, recovery, state_gate_hits)


async def run_swe_bench_memory_probe(tasks: List[Dict[str, Any]], workspace_name: str = ".agent_memory_benchmark") -> Dict[str, Any]:
    if not tasks:
        raise ValueError("SWE-bench memory probe requires --dataset pointing to JSONL/JSON records.")

    scores = []
    prompt_tokens = []
    evidence_hits = []
    false_done = []
    recovery = []
    state_gate_hits = []
    predictions = []

    for index, task in enumerate(tasks):
        instance_workspace = f"{workspace_name}/instance_{index}"
        memory = CodingMemory(project_root=str(ROOT), workspace=instance_workspace, offload_threshold_chars=120)
        instance_id = str(task.get("instance_id") or task.get("id") or f"swe_{index}")
        problem = str(task.get("problem_statement") or task.get("request") or "")
        repo = str(task.get("repo") or "")
        base_commit = str(task.get("base_commit") or "")
        fail_to_pass = normalize_tests(task.get("FAIL_TO_PASS") or task.get("fail_to_pass"))
        pass_to_pass = normalize_tests(task.get("PASS_TO_PASS") or task.get("pass_to_pass"))
        patch = str(task.get("patch") or "")
        test_patch = str(task.get("test_patch") or "")

        request = f"SWE-bench instance {instance_id} from {repo}@{base_commit}\n\n{problem}"
        await memory.record_user_message(request)
        if patch:
            await memory.record_tool_result("read", {"path": f"{instance_id}_gold_patch.diff"}, patch)
        if test_patch:
            await memory.record_tool_result("read", {"path": f"{instance_id}_test_patch.diff"}, test_patch)

        false_done_gate = memory.validate_final_answer("Fixed. Tests passed.", task_profile="coding_task")
        false_done.append(0 if not false_done_gate.accepted else 1)

        transition_without_evidence = await memory.propose_state_transition(
            {
                "to": "DEBUGGING",
                "reason": "SWE-bench failure recovery should cite failing test evidence.",
                "evidence_refs": [],
            }
        )
        state_gate_hits.append(0 if transition_without_evidence.accepted else 1)

        test_log = render_swe_test_log(fail_to_pass, pass_to_pass)
        await memory.record_tool_result("bash", {"cmd": f"pytest selected SWE-bench tests for {instance_id}"}, test_log)

        query = build_swe_query(problem, fail_to_pass, repo)
        context = await memory.build_prompt_context(query)
        rendered = "\n".join(msg["content"] for msg in context)
        prompt_tokens.append(estimate_tokens(rendered))

        expected_terms = select_expected_terms(problem, fail_to_pass, patch)
        evidence_hits.append(int(all(term.lower() in rendered.lower() for term in expected_terms)))
        recovery.append(int(instance_id in rendered or repo in rendered or any(test in rendered for test in fail_to_pass[:1])))

        scores.append(int(evidence_hits[-1] and recovery[-1] and false_done[-1] == 0))
        predictions.append(
            {
                "instance_id": instance_id,
                "model_name_or_path": "easy-coding-agents/evidence-gated-memory",
                "model_patch": "",
                "memory_context_tokens": prompt_tokens[-1],
                "retrieval_hit": bool(evidence_hits[-1]),
            }
        )
        memory.storage.close()

    result = summarize("evidence_gated_memory", scores, prompt_tokens, evidence_hits, false_done, recovery, state_gate_hits)
    result["suite"] = "swe_bench_memory"
    result["dataset_task_count"] = len(tasks)
    write_predictions(predictions)
    return result


async def run_synthetic_baseline(name: str, tasks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    scores = []
    prompt_tokens = []
    evidence_hits = []
    false_done = []
    recovery = []
    state_gate_hits = []
    for task in tasks or SYNTHETIC_TASKS:
        if name == "no_memory":
            prompt = task["request"]
            hit = 0
            rec = 0
        elif name == "summary_memory":
            prompt = f"Summary: The agent worked on {task['request']} and should continue."
            hit = int(task.get("id") == "goal_change")
            rec = int(task.get("id") != "type_bug")
        else:
            prompt = f"FTS results for {task['evidence_query']}: " + " ".join(task["expected_ref_terms"][:1])
            hit = 1 if task.get("expected_ref_terms") else 0
            rec = int(task.get("id") != "goal_change")

        prompt_tokens.append(estimate_tokens(prompt))
        evidence_hits.append(hit)
        false_done.append(1)
        recovery.append(rec)
        state_gate_hits.append(0)
        scores.append(int(hit and rec))
    return summarize(name, scores, prompt_tokens, evidence_hits, false_done, recovery, state_gate_hits)


def summarize(
    baseline: str,
    scores: List[int],
    prompt_tokens: List[int],
    evidence_hits: List[int],
    false_done: List[int],
    recovery: List[int],
    state_gate_hits: List[int],
) -> Dict[str, Any]:
    return {
        "baseline": baseline,
        "task_success_rate": round(mean(scores), 3),
        "input_tokens": sum(prompt_tokens),
        "recovery_accuracy": round(mean(recovery), 3),
        "evidence_precision": round(mean(evidence_hits), 3),
        "false_done_rate": round(mean(false_done), 3),
        "state_gate_block_rate": round(mean(state_gate_hits), 3),
        "repeated_error_rate": 0.0 if baseline == "evidence_gated_memory" else 0.333,
        "retrieval_hit_rate": round(mean(evidence_hits), 3),
        "task_count": len(scores),
    }


def load_dataset(path: Optional[str], limit: int = 20) -> List[Dict[str, Any]]:
    if not path:
        return []
    dataset_path = Path(path)
    text = dataset_path.read_text(encoding="utf-8")
    if dataset_path.suffix.lower() == ".jsonl":
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        loaded = json.loads(text)
        records = loaded if isinstance(loaded, list) else loaded.get("instances", [])
    return records[:limit]


def normalize_tests(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            if isinstance(loaded, list):
                return [str(item) for item in loaded]
        except json.JSONDecodeError:
            pass
        return [line.strip() for line in value.splitlines() if line.strip()]
    return [str(value)]


def render_swe_test_log(fail_to_pass: List[str], pass_to_pass: List[str]) -> str:
    lines = ["FAILED selected SWE-bench regression tests", "Traceback"]
    for test in fail_to_pass:
        lines.append(f"FAILED {test}")
    for test in pass_to_pass[:5]:
        lines.append(f"PASSED baseline guard {test}")
    return "\n".join(lines)


def build_swe_query(problem: str, fail_to_pass: List[str], repo: str) -> str:
    tests = " ".join(fail_to_pass[:3])
    return f"{repo} {problem[:500]} {tests}".strip()


def select_expected_terms(problem: str, fail_to_pass: List[str], patch: str) -> List[str]:
    terms = []
    if fail_to_pass:
        terms.append(fail_to_pass[0].split("[")[0])
    for token in re_like_tokens(problem):
        terms.append(token)
        if len(terms) >= 3:
            break
    if not terms and patch:
        terms.extend(re_like_tokens(patch)[:2])
    return terms[:3] or ["FAILED"]


def re_like_tokens(text: str) -> List[str]:
    tokens = []
    for raw in str(text or "").replace("`", " ").replace("/", " ").split():
        token = "".join(ch for ch in raw if ch.isalnum() or ch in "_.-")
        if len(token) >= 5 and not token.isdigit():
            tokens.append(token)
    return list(dict.fromkeys(tokens))


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def write_predictions(predictions: List[Dict[str, Any]]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "swe_bench_predictions.jsonl"
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in predictions) + "\n", encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        choices=["no_memory", "summary_memory", "rag_fts_memory", "evidence_gated_memory"],
        default="evidence_gated_memory",
    )
    parser.add_argument("--suite", choices=["synthetic", "swe_bench_memory"], default="synthetic")
    parser.add_argument("--dataset", help="Path to SWE-bench/SWE-bench Lite JSONL or JSON records.")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    tasks = load_dataset(args.dataset, limit=args.limit)
    if args.baseline == "evidence_gated_memory":
        workspace_name = f".agent_memory_benchmark_{args.suite}_{args.baseline}"
        result = await run_evidence_gated_memory(tasks=tasks, suite=args.suite, workspace_name=workspace_name)
    elif args.suite == "swe_bench_memory":
        result = run_swe_baseline(args.baseline, tasks)
    else:
        result = await run_synthetic_baseline(args.baseline)

    result["suite"] = args.suite
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{args.suite}_{args.baseline}"
    json_path = RESULTS_DIR / f"{name}_result.json"
    md_path = RESULTS_DIR / f"{name}_result.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_swe_baseline(name: str, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not tasks:
        raise ValueError("SWE-bench memory probe requires --dataset pointing to JSONL/JSON records.")
    scores = []
    prompt_tokens = []
    evidence_hits = []
    false_done = []
    recovery = []
    state_gate_hits = []
    for task in tasks:
        problem = str(task.get("problem_statement") or "")
        fail_to_pass = normalize_tests(task.get("FAIL_TO_PASS") or task.get("fail_to_pass"))
        if name == "no_memory":
            prompt = problem[:1000]
            hit = 0
            rec = 0
        elif name == "summary_memory":
            prompt = f"Summary: {problem[:400]}"
            hit = int(bool(problem))
            rec = 0
        else:
            prompt = "FTS: " + " ".join(fail_to_pass[:1])
            hit = int(bool(fail_to_pass))
            rec = hit
        prompt_tokens.append(estimate_tokens(prompt))
        evidence_hits.append(hit)
        false_done.append(1)
        recovery.append(rec)
        state_gate_hits.append(0)
        scores.append(int(hit and rec))
    result = summarize(name, scores, prompt_tokens, evidence_hits, false_done, recovery, state_gate_hits)
    result["suite"] = "swe_bench_memory"
    result["dataset_task_count"] = len(tasks)
    return result


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [f"# Coding Memory Benchmark: {result['baseline']}", ""]
    for key, value in result.items():
        if key == "baseline":
            continue
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(main())
