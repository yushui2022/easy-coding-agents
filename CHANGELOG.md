# Changelog

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
