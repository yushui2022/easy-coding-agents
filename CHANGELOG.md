# Changelog

## 0.7.0 — 2026-10-17

- 新增有数量/轮数/超时限制的并行子任务，独立源码快照、冲突检查与可撤销文件合并。
- 隔离子任务在执行层禁用 Shell/MCP/LSP 与递归委派，恢复后保持隔离。
- MCP 连接所有者任务、显式断开、资源/模板读取和提示词获取，保留逐次审批与无重放原则。
- 新增 Responses 流式协议、reasoning 项回传和请求用量统计；支持可选 reasoning_effort。
- 新增经审批的 stdio LSP 定义、引用、悬停、符号及 pull diagnostics 查询。
- 边界：无 OS 沙箱、OAuth、Git worktree 合并或 LSP 自动重命名。见 docs/UPGRADE-v0.7.md。


## 0.6.0 — 2026-10-17

- Add optional official-SDK MCP stdio/Streamable HTTP tool discovery and invocation with per-operation approval, bounded timeouts, schema validation and no automatic replay.
- Add bounded child agents with independent durable sessions, sequential execution, inherited file/Shell approvals and parent mode ceilings. Children cannot delegate or invoke MCP.
- Persist each model request attempt, including retries, cancellation, compaction and child work. Normalize provider cache usage and calculate Decimal subtotals from per-request price snapshots; unknown or incomplete usage/prices remain explicit.
- Add `/mcp`, `/agents`, `/usage`, headless `--usage`, and server-scoped `--allow-mcp`.

## 0.5.2 — 2026-10-17

- Pass max_output_tokens to OpenAI-compatible requests, matching the native provider's output cap.
- Tell the model its remaining response budget and encourage direct reads, batched independent reads and timely final reporting; no additional summary request is added.
- Warn on repeated identical tool observations while still executing fresh calls; preserve JSON results and the existing repetition stop guard.
- Label recognized unittest/pytest zero-test output as no_tests, preserve the actual exit code, and exclude it from successful-command memory. This is a bounded-output heuristic, not a universal test-runner parser.

## 0.5.1 — 2026-10-17

- Replace configuration-only doctor output with structured, read-only local readiness checks and actionable warnings.
- Keep session listing and file review/undo available with malformed model configuration; avoid initializing state when listing an empty project.
- Reject unknown agent options, invalid key-variable types, invalid endpoint ports and credential-bearing query/fragment URLs.

## 0.5.0 — 2026-10-17

- Integrate existing memory-core SQLite/FTS through a source-qualified CLI adapter; package the core with ECA.
- Capture successful test-command evidence with session/action provenance and bounded project fingerprints; exclude stale records from new-session context.
- Add `/memory`, `/remember`, `/forget` and optional automatic-memory opt-out.
- Load hierarchical AGENTS.md rules before file edits; defer mutations until rules have reached a subsequent model request.
- Keep legacy research databases isolated and assistant claims out of automatic project memory.

## 0.4.0 — 2026-10-17

- Persist before/after snapshots before file-tool writes; review, accept and undo individual edits without resetting the Git index or overwriting later edits.
- Add interactive and headless review commands; undo updates conversation context and supports interrupted write/undo records.
- Automatically summarize older context while retaining recent complete tool exchanges and the full archive.
- Add bounded, cancellable transient model retries before text output, persisted stop reasons and `/continue`.
- Keep shell side effects outside file undo; document snapshot scope and model usage costs.

## 0.3.0 — 2026-10-17

- Native Anthropic Messages streaming and normalized tool-use history, selected by config/environment/CLI.
- Strict completion checks before tools execute; output budget, usage, credential isolation and protocol diagnostics.
- Native protocol fixtures plus real HTTP CLI execution and cross-process session recovery tests.
- Preserve upstream memory research and legacy entry point; test both runtimes together.
- CI template retained under docs because current GitHub credentials lack workflow scope.

## 0.2.0 — 2026-10-17

- New `eca` package and CLI; original application retained as `legacy_main.py`.
- Native async streaming with complete-response validation and local endpoint proxy bypass.
- SQLite sessions and tool journal, project isolation and exclusive process lock.
- Code/Plan/Chat tools enforced at dispatch; explicit file and shell approvals.
- Atomic file writes, unique edits, conflict checks, bounded search and command output.
- Awaited cancellation and subprocess cleanup, repetition and turn limits.
- Session/model/profile/mode/permission commands, context summary, Git diff and Markdown export.
- Headless tasks and JSONL events; installable wheel and Windows/Linux CI configuration.
- Offline regression tests and real localhost HTTP streaming CLI integration test.

See docs/UPGRADE-v0.2.md for migration, preserved history and limitations.
