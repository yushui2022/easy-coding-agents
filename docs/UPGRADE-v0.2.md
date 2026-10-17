# v0.2 implementation and migration

This project began as a personal coding assistant. v0.2 keeps its name and Python foundation while replacing the default execution path. It is a runnable development release, not a claim of Claude Code/OpenCode feature parity.

## Implementation plan and outcome

Goal: a single-user terminal coding workflow with reliable tool exchanges, explicit permissions, persistence, and a scriptable entry point.

| Module | Responsibility |
| --- | --- |
| `eca/config.py` | Project settings, environment secrets, compatible provider endpoint |
| `eca/provider.py` | Native async streaming, response completeness checks |
| `eca/store.py` | SQLite session snapshots, action journal, crash repair, project process lock |
| `eca/tools.py` | File/search/plan/question/shell tools, approvals and bounded output |
| `eca/agent.py` | Awaited execution loop, mode enforcement, context and cancellation |
| `eca/cli.py` | Prompt, slash commands, streamed output, diffs, JSONL and one-shot mode |
| `tests/` | Runtime invariants, HTTP streaming integration, process cleanup |

Execution order: separate the runtime → persist full protocol → enforce permissions → connect tools → implement CLI → test offline and via a local HTTP server → document behavior.

## Preserved material

- The original entry point is `legacy_main.py`; old `core/`, `memory/`, `tools/`, and `utils/` remain intact.
- Original requirements are in `requirements-legacy.txt`.
- The old README and integration guide are retained in `docs/legacy/`.
- Existing `.env`, `MEMORY.md`, agent definitions and Markdown sessions are not edited or deleted.
- `main.py` and `python -m eca` now enter the v0.2 CLI.

Legacy Markdown sessions deliberately are not automatically imported as executable history: their format omitted tool results and confused headings with roles. They remain readable source material. Old custom agent JSON is retained; recreate selected instructions in `[profiles]` in `eca.toml`. Old smart-search/Tree-sitter modules remain in the legacy runtime; the new runtime uses bounded literal search and glob without a Tree-sitter dependency.

## Configuration and permissions

Flags override settings. Model/endpoint environment variables override TOML. Secrets come from the selected project's `.env` plus process environment (environment wins). A configured `api_key_env` explicitly selects the variable; otherwise `ECA_API_KEY`, `OPENAI_API_KEY`, then `MODELSCOPE_API_KEY` are checked.

Project files `AGENTS.md` and `MEMORY.md` are included when they are non-symlink files up to 64 KB. Nested AGENTS instructions are requested in the system prompt; automatic hierarchy resolution is not implemented.

Code mode offers tools with approvals; plan mode excludes mutations and shell in both schema and dispatcher; chat mode exposes no tools. Permission `accept-edits` authorizes workspace edits only. Shell commands are still individually approved unless `--allow-shell` explicitly grants them for a one-shot task.

The path policy is a guardrail, not a sandbox. Approved shell commands execute with the current user's OS rights and can affect files outside the project. Do not treat the built-in protected file list as a complete secret scanner. Project TOML and guidance should be used only from trusted repositories.

## Persistence and cancellation guarantees

All full assistant/tool messages are retained in `.eca/sessions.sqlite3`. Before a tool runs, its intent is committed. A completed journal result can close an interrupted protocol exchange on resume. An action without a completed record is marked outcome-unknown, never automatically replayed. This is not exactly-once execution for arbitrary shell commands.

File changes use a temporary file and atomic replacement, with a pre-write conflict check after approval. This guards against ordinary concurrent edits during the prompt; it is not a hostile-filesystem transactional sandbox. Symlinks escaping the root and `.eca` symlinks/junctions are rejected.

Ctrl+C cancels the current async task; subprocess cleanup is awaited. Windows uses taskkill /T /F; POSIX uses process groups. Detached/background processes that escape their original process tree/group are outside this guarantee. API cancellation stops local consumption; it cannot guarantee the provider stops billing or remote computation.

One process at a time owns a project session store, preventing concurrent snapshot overwrites. A stale lock file is harmless: the OS file lock is released when its owning process exits.

## Context and reporting

The context limit is a character budget, not an exact token meter. Complete older user turns can be omitted from requests with an explicit notice; full history stays on disk. `/compact` requests a summary and changes the active context offset, retaining the archive. A very large transcript is summarized from a bounded excerpt and marked partial. Neither approach guarantees perfect memory.

Todo completion and the idle status do not assert code correctness. The agent is instructed to run appropriate checks and report limits; no universal verifier is implemented. Usage displays provider-reported data when available, not an invented token/cost estimate.

## Verification and remaining risks

Tests use fake responses and a localhost SSE server; no real model key or paid request is needed. They cover approval denial, ambiguous edits, CRLF, conflict checks, modes, protected paths, session roundtrips, crash repair, cancellation, timeouts, context handling, fragmented streams, incomplete responses, and an actual CLI subprocess that writes a file then resumes.

A CI template for Windows/Linux with Python 3.11/3.12 is saved as `docs/ci-workflow.yml`. It is not active: the current GitHub credential lacks workflow scope. Local results are documented in `docs/VALIDATION-v0.2.md`.

Not included: native Anthropic/Responses protocol, OAuth subscriptions, MCP, LSP diagnostics, autonomous subagents, automatic compaction, shell sandboxing, reliable live cost accounting, or legacy session migration. OpenAI-compatible Chat Completions streaming with tool calling is required; compatibility varies by provider and model.

The repository previously tracked `.env`, venv and bytecode. `.gitignore` prevents new untracked copies but does not erase tracked files or Git history. This upgrade does not rewrite history or stage mass removals. Before public distribution, audit secrets and establish the project's license/rights. The wheel configuration includes only `eca`, not the environment or legacy user data.
