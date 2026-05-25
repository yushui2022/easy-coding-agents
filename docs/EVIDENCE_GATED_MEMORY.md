# Evidence-Gated Coding Memory

This repo now contains a reusable memory package:

```text
agent_memory_core/
```

It is designed for coding agents that need to continue long tasks, recover after context loss, and avoid claiming work is complete without evidence.

## Public Interface

```python
from agent_memory_core import CodingMemory

memory = CodingMemory(project_root=".", workspace=".agent_memory")

await memory.record_user_message(text)
await memory.record_assistant_message(text, tool_calls=None)
await memory.record_tool_result(name, args, result)
context = await memory.build_prompt_context(current_user_request)
gate = await memory.check_quality_gate(proposal)
await memory.commit_task_outcome(result)
```

`memory.MemoryManager` remains as a compatibility facade for the existing engine, so the project does not need a full engine rewrite at once.

## What Changed

The old memory model was mostly recent dialogue plus summary compression. The new model stores evidence first, then builds prompt context from structured state.

```text
tool result -> refs/*.md
tool summary -> SQLite events
task progress -> task_nodes
current phase -> task_state
prompt -> quality gates + task state + task map + retrieved evidence summaries
```

Large outputs are offloaded to Markdown refs. The prompt keeps only summaries and `result_ref` pointers, so the agent can recover exact evidence when needed.

## Storage Layout

```text
.agent_memory/
  memory.db
  refs/
  sessions/
  task_maps/
  exports/
```

Core SQLite tables include:

- `events`: L0 raw events for user, assistant, tool, state, file, and test evidence.
- `refs`: Markdown ref index for large tool outputs, logs, diffs, and searches.
- `task_nodes`: task-map nodes with `node_id`, status, files, summary, and `result_ref`.
- `task_state`: soft state machine state and current goal version.
- `claims`: important agent claims that should bind to evidence.
- `memories`: long-term memories such as Preference, Project, Decision, Failure, and Procedure.
- `memory_items`: append-only extracted facts used for temporal and conflict-aware retrieval.
- `entities`: coding-oriented entity index for files, functions, classes, tests, errors, commands, goals, and preferences.
- `memory_sources`: source links from memories back to events or refs.
- `retrieval_logs`: query and hit records for prompt construction.

## Retrieval Signals

Prompt construction uses a local multi-signal retriever:

```text
ref_exact + entity_match + FTS/BM25 + recency/temporal intent
+ task_focus + failure_priority + file_match + source_confidence
```

`retrieval_logs` stores the selected rows and each row's `signals` breakdown.
This makes it possible to test whether a context was built from a current task
node, a failing test log, an exact `result_ref`, a file entity, or a long-term
memory item.

## Soft State Machine

The state machine records the task phase, but it does not force a rigid workflow. The LLM can decide the next action. The system enforces quality boundaries.

States:

```text
UNDERSTANDING
GATHERING_CONTEXT
PLANNING
EDITING
TESTING
DEBUGGING
WAITING_USER
DONE
UNKNOWN
```

Quality gates:

- File claims require read/search/ref evidence.
- Error explanations require command or test log evidence.
- DONE requires verification evidence, or an explicit unverified reason.
- Long-term memories require source refs before being injected as facts.
- Conflicting memories require tracing back to original events or refs.
- Goal changes require a new goal version and re-planning.

## Prompt Shape

The memory core builds context in this order:

```text
<System>
Base agent instructions

<Quality Gates>
Evidence rules the agent must obey

<User/Project Memories>
Only sourced long-term memories

<Current Task State>
State, goal, evidence refs, next actions

<Task Map Mermaid>
Lightweight task graph

<Evidence Summaries>
Retrieved refs and event summaries

<Recent Dialogue>
Recent user, assistant, and tool turns

<Current User Request>
Current request
```

## Benchmark

The benchmark is intentionally focused on coding-agent memory, not generic RAG.

```powershell
python benchmark\coding_memory\run.py --baseline no_memory
python benchmark\coding_memory\run.py --baseline summary_memory
python benchmark\coding_memory\run.py --baseline rag_fts_memory
python benchmark\coding_memory\run.py --baseline evidence_gated_memory
```

Metrics:

- `task_success_rate`
- `input_tokens`
- `recovery_accuracy`
- `evidence_precision`
- `false_done_rate`
- `repeated_error_rate`
- `retrieval_hit_rate`

The first target is not to beat every public memory project on generic retrieval. The focused target is stronger coding-task recovery and lower false-DONE behavior than summary-only memory.
