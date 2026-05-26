# Agent Memory Core

Evidence-Gated Coding Memory is a reusable memory module for coding agents.
It combines TencentDB-Agent-Memory-style context offloading and task maps with
OpenViking-style filesystem organization and SQLite/FTS retrieval.

## Benchmark Status

The current benchmark layer evaluates the memory subsystem after context wipe.
It is a retrieval and evidence smoke test, not an official LongMemEval or
LoCoMo answer-accuracy score yet. Official-style answer accuracy still requires
an answer generator and judge.

Latest `evidence_gated_memory` smoke results:

| Suite | Dataset | Limit | Retrieval / Term Recall | Evidence Source Coverage | Evidence Precision | Latency p50 | False Fact Rate |
|---|---|---:|---:|---:|---:|---:|---:|
| LongMemEval-S | `longmemeval_s_cleaned.json` | 5 | 0.40 | 1.00 | 1.00 | 0.9048s | 0.00 |
| LoCoMo10 | `locomo10.json` | 5 | 0.00 | 0.80 | 0.80 | 0.5671s | 0.00 |
| BEAM-lite | synthetic 100K tokens | 1 | 1.00 | 1.00 | 1.00 | 0.0242s | 0.00 |

LongMemEval-S `limit=100` baseline results:

| Baseline | Cases | Retrieval / Term Recall | Evidence Source Coverage | Input Tokens | Latency p50 | False Fact Rate |
|---|---:|---:|---:|---:|---:|---:|
| `no_memory` | 100 | 0.01 | 0.00 | 1,321 | 0.0000s | 0.00 |
| `summary_memory` | 100 | 0.15 | 0.00 | 11,400 | 0.0000s | 0.00 |
| `long_context_only` | 100 | 0.54 | 0.36 | 5,500,800 | 0.0007s | 0.00 |
| `keyword_fts_memory` | 100 | 0.39 | 0.87 | 182,969 | 0.5088s | 0.00 |
| `vector_rag_memory` | 100 | 0.38 | 0.67 | 184,067 | 0.7292s | 0.00 |
| `evidence_gated_memory` | 100 | 0.40 | 0.87 | 178,117 | 0.9138s | 0.00 |

LoCoMo10 `limit=100` and BEAM-lite `100K tokens / 50 cases` are documented in
`benchmark/memory_eval/README.md`.

The main difference from a normal summary memory is quality gating:

- no file-content claim without read/search/ref evidence
- no error diagnosis without command/test log evidence
- no DONE claim without verification evidence or an explicit unverified reason
- no sourced long-term memory without evidence refs
- conflicting memories must trace back to refs/events

## Basic Usage

```python
from agent_memory_core import CodingMemory

memory = CodingMemory(project_root=".", workspace=".agent_memory")

await memory.record_user_message("Fix the memory module bug")
await memory.record_tool_result(
    name="bash",
    args={"cmd": "pytest"},
    result="FAILED...\nTraceback...\nAttributeError...",
)

messages = await memory.build_prompt_context("AttributeError")
gate = await memory.check_quality_gate({"to": "DONE", "evidence_refs": []})
```

## Storage Layout

```text
.agent_memory/
  memory.db
  refs/
  sessions/
  task_maps/
  exports/
```

`refs/*.md` stores raw tool results. SQLite stores events, refs metadata,
task nodes, current task state, claims, long-term memories, source links, and
retrieval logs.

## Matured Retrieval Layer

The v1 retrieval path is still local-first: SQLite + FTS5 + Markdown refs.
It now adds a coding-oriented entity and temporal layer before any vector
database is required.

- `memory_items` is append-only. New facts are inserted as new rows; old facts
  stay available for historical lookup and conflict tracing.
- `claims` from the assistant are first-class facts, but unsupported claims are
  marked and are not injected as sourced memory.
- `entities` indexes coding entities: files, functions, classes, tests, errors,
  commands, goals, and user preferences.
- Retrieval logs include signal breakdowns such as `ref_exact`, `entity_match`,
  `fts_bm25`, `task_focus`, `failure_priority`, `file_match`, `memory_item`,
  and `temporal_latest`.
- Temporal queries containing words like `latest`, `current`, `previous`, or
  `现在` boost newer goal versions without deleting older facts.

## Public Interface

- `record_user_message(text)`
- `record_assistant_message(text, tool_calls=None)`
- `record_tool_result(name, args, result, tool_call_id=None)`
- `build_prompt_context(current_user_request=None)`
- `check_quality_gate(proposal)`
- `commit_task_outcome(result)`
- `add_memory(content, memory_type="Decision", source_refs=None)`
- `save_session()`
