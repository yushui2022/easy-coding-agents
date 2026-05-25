# Agent Memory Core

Evidence-Gated Coding Memory is a reusable memory module for coding agents.
It combines TencentDB-Agent-Memory-style context offloading and task maps with
OpenViking-style filesystem organization and SQLite/FTS retrieval.

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
