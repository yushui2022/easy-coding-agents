# Changelog

## 0.10.0 — 2026-10-17

- `--verify-command` 支持最多 10 项顺序检查，首个失败后停止。
- 新增显式 `--repair-attempts 0..3`：保留原任务要求，失败后有界修复并重跑整组检查。
- 取消、超时、拒绝和未知结果不自动重跑；整组结果要求同一源码指纹。
- 持久记录各轮结果；JSONL 与 `/progress` 显示整组状态，恢复会话不会自动重放。
- 用法与边界见 [v0.10](docs/UPGRADE-v0.10.md)。
- 最终全量回归 188 passed, 1 skipped；安装包 23 个运行时模块与源码逐字节一致。

## 0.9.0 — 2026-10-17

- 最近 12 项文件/命令观察持久保存，压缩后继续提供给模型，新增 `/progress` 汇总入口。
- 三种模型协议识别明确的输出上限；丢弃不完整回复，最多两次要求拆分后续操作，保留原轮数限制与请求账本。
- 新增 `/verify COMMAND` 与 `--verify-command`，复用 Shell 审批、模式限制和日志；失败退出码 3，支持快照失效、无测试和取消状态。
- 使用方法与实际边界见 [v0.9 升级记录](docs/UPGRADE-v0.9.md)。
- 全量离线回归 178 passed, 1 skipped；wheel 的 22 个运行时模块与源码一致。

## 0.8.2 — 2026-10-17

- 修复完整读取 AGENTS.md 后仍重复阻断后续写入的问题，保留同批次、部分读取、截断和规则变更保护。
- 新增 StockFlow 多模块 FastAPI / SQLite 项目验收契约及真实模型构建、修复、恢复运行器。
- 相关规则/删除专项 12 项通过，全量 166 passed, 1 skipped。

## Unreleased

- 新增显式运行的 DeepSeek 在线验收工具，使用独立 Git fixture、外部断言与测试变异检查，覆盖五类编码流程。
- 验收报告记录用量、可选价格快照、运行耗时、子任务状态、工具配对及 Git 暂存区保护。
- 新增离线验收器测试；在线任务不加入默认 pytest 或 CI。

## 0.8.1 — 2026-10-17

- 新增带差异审批与持久记录的单文件 delete 工具，支持删除审阅、接受与字节级撤销。
- 并行子 Agent 返回 deleted 状态；父会话可合并有完成记录的删除，沿用基线冲突检查。
- 拒绝二进制文本变更，补齐空文件删除差异、审批期间修改与删除失败恢复测试。
- 使用范围及限制见 docs/UPGRADE-v0.8.1.md。

## 0.8.0 — 2026-10-17

- 借鉴 Pi 子任务与模型配置、OpenCode LSP/MCP 生命周期设计，保持本项目的审批与隔离边界。
- 新增独立并发上限与排队状态，修复初始化失败影响同批任务及状态读取触发错误恢复的问题。
- 子任务返回失败原因与改动清单；准备失败与取消排队任务均持久记录。
- LSP 改为会话内复用、didChange 同步、push/pull 诊断、版本检查及显式断开，新增 implementation 查询。
- 新增命名模型配置与安全的接口/密钥切换、会话恢复；Responses 推理项仅在同模型/接口复用。
- MCP 真实存活状态、每服务操作队列、取消隔离与下一次明确操作重连。
- 配置、参考资料及未实现边界见 docs/UPGRADE-v0.8.md。


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
