<p align="center">
  <img src="docs/assets/banner.svg" alt="Easy-Coding-Agent — Evidence-gated memory for long-running coding agents" width="100%">
</p>

# Easy-Coding-Agent

Easy-Coding-Agent is a Python coding-agent project with a reusable memory
module, `agent_memory_core`. The current research focus is not to claim a full
SWE-bench resolved rate yet. The focus is narrower and easier to verify:

- Can the memory subsystem recover useful facts after context is wiped?
- Can retrieved facts point back to source evidence?
- Can the system avoid treating unsupported memories as facts?
- Can coding-agent state, tool logs, failures, and refs survive long tasks with
  lower token cost than long-context-only prompts?

The memory module combines:

- tool-result offloading to Markdown refs
- SQLite/FTS retrieval
- coding-oriented entity extraction
- temporal and goal-version aware ranking
- task-state tracking
- evidence-gated quality rules

## What Is Measured

The benchmark results below are **memory-subsystem retrieval and evidence
results after context wipe**. They are not official LongMemEval or LoCoMo answer
accuracy scores, and they are not SWE-bench patch correctness scores.

Current runner flow:

1. Ingest benchmark sessions into memory.
2. Close the memory object.
3. Reopen the same SQLite database.
4. Build context with `recent_dialogue_limit=0`.
5. Score whether the memory context contains expected answer/evidence terms and
   source refs.

This means the numbers are useful for evaluating retrieval, source coverage,
token cost, and false unsupported facts. They do not yet prove final answer
quality because the runner does not attach an answer generator or judge.

## Larger Memory-Subsystem Results

LongMemEval-S `limit=100`:

| Baseline | Cases | Retrieval / Term Recall | Evidence Source Coverage | Input Tokens | Latency p50 | False Fact Rate |
|---|---:|---:|---:|---:|---:|---:|
| `no_memory` | 100 | 0.01 | 0.00 | 1,321 | 0.0000s | 0.00 |
| `summary_memory` | 100 | 0.15 | 0.00 | 11,400 | 0.0000s | 0.00 |
| `long_context_only` | 100 | 0.54 | 0.36 | 5,500,800 | 0.0007s | 0.00 |
| `keyword_fts_memory` | 100 | 0.39 | 0.87 | 182,969 | 0.5088s | 0.00 |
| `vector_rag_memory` | 100 | 0.38 | 0.67 | 184,067 | 0.7292s | 0.00 |
| `evidence_gated_memory` | 100 | 0.40 | 0.87 | 178,117 | 0.9138s | 0.00 |

LoCoMo10 `limit=100`:

| Baseline | Cases | Retrieval / Term Recall | Evidence Source Coverage | Input Tokens | Latency p50 | False Fact Rate |
|---|---:|---:|---:|---:|---:|---:|
| `no_memory` | 100 | 0.01 | 0.02 | 1,141 | 0.0000s | 0.00 |
| `summary_memory` | 100 | 0.02 | 0.02 | 11,400 | 0.0000s | 0.00 |
| `long_context_only` | 100 | 0.19 | 0.99 | 1,792,483 | 0.0000s | 0.00 |
| `keyword_fts_memory` | 100 | 0.06 | 0.74 | 110,028 | 0.0241s | 0.00 |
| `vector_rag_memory` | 100 | 0.06 | 0.58 | 187,057 | 0.0411s | 0.00 |
| `evidence_gated_memory` | 100 | 0.06 | 0.74 | 182,886 | 0.0943s | 0.00 |

BEAM-lite `100K tokens / 50 cases`:

| Baseline | Cases | Retrieval / Term Recall | Evidence Source Coverage | Input Tokens | Latency p50 | False Fact Rate |
|---|---:|---:|---:|---:|---:|---:|
| `no_memory` | 50 | 0.00 | 0.00 | 450 | 0.0000s | 1.00 |
| `summary_memory` | 50 | 0.00 | 0.00 | 650 | 0.0000s | 1.00 |
| `long_context_only` | 50 | 1.00 | 1.00 | 5,910,300 | 0.0000s | 0.00 |
| `keyword_fts_memory` | 50 | 1.00 | 1.00 | 70,940 | 0.0131s | 0.00 |
| `vector_rag_memory` | 50 | 0.16 | 0.16 | 71,200 | 0.0308s | 0.84 |
| `evidence_gated_memory` | 50 | 1.00 | 1.00 | 109,140 | 0.0242s | 0.00 |

## Honest Interpretation

The strongest current result is LongMemEval-S. `evidence_gated_memory` is much
better than plain summary memory and roughly matches keyword FTS retrieval while
keeping source-backed evidence constraints. It does not beat `long_context_only`
on raw term recall, but `long_context_only` uses about 5.5M input tokens in this
100-case run, which is not a practical memory strategy.

LoCoMo10 is a weakness. `evidence_gated_memory` improves evidence source
coverage compared with vector RAG in this runner, but answer-term recall remains
low and matches keyword FTS. This suggests the current entity and temporal
retrieval layer is still not strong enough for complex social dialogue and
relationship reasoning.

BEAM-lite is a synthetic stress test. It shows that the system can recover
target evidence from a 100K-token synthetic corpus with low latency and far less
prompt cost than long-context-only. It should not be treated as a real-world
answer-accuracy benchmark.

## Current Claims

Reasonable claims:

- The project now has a reusable memory package, `agent_memory_core`.
- The memory runner can evaluate context-wipe retrieval on public-style data.
- Evidence-gated memory improves substantially over plain summary memory on
  LongMemEval-S retrieval/evidence metrics.
- The system keeps source refs and can block unsupported memory claims from
  entering prompt context.

Claims not supported yet:

- Official LongMemEval or LoCoMo leaderboard accuracy.
- SWE-bench patch resolved rate.
- General superiority over vector RAG or long-context-only across all tasks.
- Strong long-dialogue reasoning on LoCoMo-style relationship questions.

## Reproduce

Install dependencies:

```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Download public data used by the memory eval adapters:

```powershell
python benchmark\memory_eval\download_datasets.py --dataset locomo10
python benchmark\memory_eval\download_datasets.py --dataset longmemeval_s
```

Run the larger memory-subsystem comparisons:

```powershell
python benchmark\memory_eval\run.py --suite longmemeval --baseline all --dataset benchmark\memory_eval\datasets\longmemeval_s_cleaned.json --limit 100 --progress-every 10
python benchmark\memory_eval\run.py --suite locomo_lite --baseline all --dataset benchmark\memory_eval\datasets\locomo10.json --limit 100 --progress-every 10
python benchmark\memory_eval\run.py --suite beam_lite --baseline all --beam-tokens 100000 --beam-cases 50 --progress-every 10
```

Run tests:

```powershell
python -m pytest tests -q
```

## Memory Package Usage

```python
from agent_memory_core import CodingMemory

memory = CodingMemory(project_root=".", workspace=".agent_memory")

await memory.record_user_message("Fix the memory module bug")
await memory.record_tool_result(
    name="bash",
    args={"cmd": "pytest"},
    result="FAILED...\nTraceback...\nAttributeError...",
)

messages = await memory.build_prompt_context("What should I inspect next?")
gate = await memory.check_quality_gate({"to": "DONE", "evidence_refs": []})
```

## Repository Layout

```text
agent_memory_core/          reusable memory module
benchmark/memory_eval/      memory-subsystem benchmark runner
benchmark/coding_memory/    coding-memory and SWE-bench-format probes
core/                       agent engine
memory/                     compatibility layer for older memory APIs
tools/                      filesystem, shell, search, and interaction tools
docs/                       benchmark protocol and project notes
tests/                      unit and integration tests
```

## Next Work

- Add answer generation and judge evaluation for LongMemEval / LoCoMo style
  answer accuracy.
- Improve LoCoMo-style entity linking, relationship tracking, and temporal
  reasoning.
- Preserve per-case retrieval artifacts for easier third-party audit.
- Connect generated `model_patch` outputs to the official SWE-bench Docker
  harness only after the memory benchmarks are stable.
