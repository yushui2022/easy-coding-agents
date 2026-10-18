# Changelog

## Unreleased — 持续执行与模型输出额度

- 主 Agent 默认不限响应轮数和输出截断恢复次数，显式正整数上限继续有效，Ctrl+C 可中断。
- 已知官方 DeepSeek 模型采用模型对应的输出/上下文默认值，配置与命令行显式值优先。
- 添加四个额度命令行选项；子 Agent 仍保留自己的轮数限制。

## 0.20.0 — 安装包整合与发布验收

- 整合下列 Skills、LSP、协作验收、后台进程及联网源码升级，统一 npm/Python 版本。
- 增加发布包白名单、摘要及模块校验；独立安装验证覆盖会话恢复。
- 加入 Windows/Linux CI 发布检查（尚待远端运行）；本机全局 ecs 已升级。
- 验证与已知边界见 docs/RELEASE-0.20.0.md；仍为本地分发，未发布 npm registry。

## Unreleased — Skills、LSP 重命名与协作验收

- 项目/用户 SKILL.md 加载、按任务选择和显式 `/skill` 调用，保留工具授权限制。
- LSP 重命名预览、UTF-16 位置校验、全目标冲突检查、逐文件修改日志及修改后诊断。
- 根会话共享请求额度（含重试与摘要），串行委派可附验收命令，失败交回主 Agent。
- 增加单模型与 Worker-first 配对评测入口；未据机制测试声称真实模型成功率提升。

## Unreleased — 会话内后台进程

- 新增五个 `process_*` 工具与 `/run`、`/jobs`、`/logs`、`/stop` 命令，可在模型后续回合继续使用开发服务。
- 启动前展示命令并请求主机执行授权；Docker 和子 Agent 禁用。日志有界，最多四个并发任务，默认存活 600 秒，正常关闭时清理。
- 日志匹配与真实健康检查明确区分；不支持崩溃恢复、跨会话重连或脱离父进程的守护服务。源码功能尚未更新到全局安装包。

## 0.19.0 — 首次配置、连接诊断与新版安装包

- 新增 `ecs --configure` 单 API 配置向导：保留已有配置，支持环境变量和可选的隐藏密钥输入，保存前确认，不把密钥写入 TOML。
- 新增显式 `ecs --doctor --check-api`，支持三种协议的一次有界请求，区分鉴权、限流和连接问题，不显示服务商响应原文、不自动重试。
- npm/Python 版本统一升至 0.19.0，安装包包含下述恢复、上下文、Docker 实测与大仓库定位改动。包仍为本地分发，未发布 npm registry。
- 实际独立安装暴露 SOCKS 代理依赖缺失，正式加入 `httpx[socks]`，并为缺失代理支持提供脱敏错误。
- 全量 280 passed、6 skipped；npm 启动器 7 项通过，配置/诊断专项 15 项通过。真实默认 API 探针返回 401，未把鉴权失败记为连通成功。

## Unreleased — 大仓库关联定位

- 全量回归 273 passed、6 skipped（179.27 秒）；最后补充根路径拒绝后，定位专项 7 项再次通过。跳过为未开启的 Docker/MCP 可选验收，本轮未调用模型 API。
- 新增 `code_relations` 与 `/related SYMBOL`：返回定义、Python 调用/导入位置和测试文件标识；明确同名、别名、动态调用及语法版本限制。
- `code_search`、`repo_map` 支持相对目录/文件筛选，增量索引报告复用、读取量、删除量和解析降级。
- 修复全文索引逐文件按路径删除造成的重复扫描，改为事务内读取 rowid 后定点删除，并增加关系表路径索引。
- 增加重命名、删除、真实分支切换、目录边界和语法降级回归；DeerFlow 4,014 文件仓库三项定位任务通过，详见 [定位验收](docs/REPOSITORY_NAVIGATION.md)。仍未验证模型驱动的大仓库跨文件修改成功率。

## Unreleased — 真实隔离验收与取消状态

- 开启全部 Docker 实测后的全量回归：271 passed、1 skipped（174.79 秒）；5 项真实容器测试通过，无遗留 ECA 容器，未调用模型 API。
- Windows/WSL2 上完成真实容器边界、超时和取消清理专项；通过 inspect 核对资源限制，增加 NoNewPrivs 验证和缺失镜像拒绝执行测试。
- 沙箱取消明确记录 `cancelled`，与独立清理状态一起持久化；引擎不可用时提示 Windows 开始菜单启动，不自动启动或重置 Docker。
- 修复验收脚本对 Docker 错误大小写和非 root 路径访问拒绝的误判。环境、首次失败和复测证据见 [Docker 验收](docs/DOCKER_ACCEPTANCE.md)。

## Unreleased — 供应商上下文恢复与隔离验收

- 明确的 HTTP 上下文超限拒绝触发一次缩小预算和压缩恢复；保留失败请求账本与完整历史，不重放工具。
- 新增显式开启的真实 Docker 验收，覆盖文件/网络/用户权限边界、超时与取消清理；默认不拉取镜像。
- 离线全量 266 passed、5 skipped，其中 3 项为未开启的真实 Docker 验收，不能算作隔离验收通过。

## Unreleased — 长任务恢复

- 最终全量回归 261 passed、2 skipped；本轮未调用真实模型 API。

- 每次持久化保存有界任务检查点，包含需求摘录、任务状态、近期观察与验证日志位置。
- 恢复后的首次运行核对曾读写文件，报告变化、缺失、未核实文件及过期验证和不确定操作；不自动执行命令。
- 新增 `/checkpoint`；恢复信息参与上下文预算，保留旧文件哈希以继续阻止覆盖用户修改。
- 增加模型超时、上下文预算失败、文件变化及真实子进程退出回归。详见 [恢复说明](docs/SESSION_RECOVERY.md)。

## Unreleased — v0.19 验证与修复升级

- 全量 257 passed、2 skipped；迁移实测 3 次完成均通过，另有 1 次中断未完成。完整边界见 [验证记录](docs/VALIDATION-v0.19.md)。

- 新增同源码同诊断重复失败停止、检查回归标记、命令日志关联和 CLI 停止原因。
- suite v4 增加旧数据库迁移任务，共 14 项；历史 v3 实测单独保留。
- 前期固定任务扩展至 13 项：新增 SQLite 订单幂等、取消恢复库存、整批事务回滚，检查跨连接持久化与原有行为。
- 评测接入实际验证工作流，记录首次验证结果和全部修复轮次。
- suite 升至 3，明确测试文件保护和 batch 请求体契约；运行时和 npm 包仍为 v0.18.0。
- DeepSeek 三任务各三次：v2 原契约 1/9；明确契约后 v3 为 9/9、69 次请求，无人工修补；原失败保留，非运行时能力提升对照。见 [实测记录](docs/BASELINE-SQLITE-2026-10-18.md)。
- 用法和边界见 [升级说明](docs/UPGRADE-v0.19.md)。

## 0.18.0 — 2026-10-18

- 新增 10 项固定编码任务评测，复用已有验收并加入接口迁移、用户改动保护、读取失败恢复、压缩与配置解析。
- 自动生成任务结果与总体 JSON/Markdown 报告，保存源码指纹、参数、请求用量、费用完整性与失败项。
- 真实模型运行显式启动；默认离线测试只检查评测器。取消后保留已完成结果与未运行计数。
- 首轮 DeepSeek Flash 基线 10/10、87 次请求、0 次人工介入；单次小型场景结果，未进行竞争产品对照，费用未知。
- 评测器专项 6 passed、npm 7 passed。全量首跑 249 passed、2 skipped、1 项 MCP 测试启动时序失败；改为事件同步后 MCP 模块 9 项复测通过，生产 MCP 代码未改动。
- 用法与真实基线见 [v0.18](docs/UPGRADE-v0.18.md)。

## 0.17.0 — 2026-10-18

- 新增 `edit_many`：同一原文件上预检所有替换，拒绝重叠与依赖前序结果的替换，一次写入与撤销。
- 编辑支持唯一完整多行片段的行尾空白容错；保留缩进、内部空格与标点，支持 `match_mode=exact` 关闭容错。
- 会话保留最近读取/保存文件的字节摘要，拒绝覆盖已检测到的外部修改；审批后继续检查文件是否变化。
- 编辑失败提供有限的候选行与附近文本，供模型定向重读。
- Python 回归 244 passed、2 skipped；npm 启动器 7 passed，本地 v0.17 tgz 构建及源码一致性校验通过。
- 使用方法、边界与验证记录见 [v0.17](docs/UPGRADE-v0.17.md)。

## 0.16.0 — 2026-10-18

- 上下文加入 token 预算、输出/安全预留和完整请求预检；实际输入用量用于向上校准，模型档案分别配置窗口。
- 摘要输入保留需求与旧检查点，以合法 JSON 节选大段观察；失败保留历史与旧摘要。
- 新增 `/context` 本地估算，计费继续使用 `/usage` 的供应商用量。
- Python 回归 231 passed、2 skipped；npm 启动器 7 passed，v0.16 本地 tgz 构建及源码一致性校验通过。
- 使用方法、估算边界与验证记录见 [v0.16 升级说明](docs/UPGRADE-v0.16.md)。

## 0.15.0 — 2026-10-18

- 新增 npm 本地分发包与 `ecs` 启动命令，携带版本匹配的 Python wheel，首次运行创建独立环境。
- Python 包新增 `ecs` 入口，保留 `eca`；启动器透传原有参数、工作目录与退出码。
- 提供 `--setup`、无需初始化的 `--version`、摘要校验、初始化锁和 G 盘优先缓存。
- npm 安装阶段不执行 postinstall。此版仍需 Node.js 20+ 和 Python 3.11+，未公开发布 registry。
- Python 全量 222 passed, 2 skipped；Node 7 项通过，Windows 实际 tgz 安装与启动通过。
- [安装方式](docs/NPM_INSTALL.md) · [验证记录](docs/UPGRADE-v0.15.md)。

## 0.14.0 — 2026-10-17

- 显式 `--worker-first PROFILE`：先由已启用的 Worker 执行，再运行用户指定检查。
- 普通检查失败时，按已有 `--repair-attempts 0..3` 预算交给当前主模型修复，再检查；默认零次。
- Worker 未完成、取消、超时或未知检查结果不自动接手重跑。持久记录 Worker、检查轮次与接手原因。
- 全量 222 passed, 2 skipped；25 个运行时模块与安装包一致。用法及共享目录边界见 [v0.14](docs/UPGRADE-v0.14.md)。

## 0.13.0 — 2026-10-17

- 可选 `agent.worker_profiles` 白名单；默认空列表，单 API 使用方式不变。
- 子 Agent 可独立选择模型档案，支持混合模型并行、独立凭据和现有用量归集；不静默回退收费模型。
- `/models` 显示 Worker 是否启用；本地模型需要自行安装并提供兼容工具调用服务。
- 全量回归 216 passed, 2 skipped，25 个运行时模块与 wheel 一致。使用方法和边界见 [v0.13](docs/UPGRADE-v0.13.md)。

## 0.12.0 — 2026-10-17

- 单个标识符搜索优先返回大小写一致的符号定义，附定义行号；旧索引自动补齐符号表。
- 索引扫描支持协作取消，未提交的更新整体回滚，等待后台线程退出后再返回。
- Docker 执行前持久保存容器名称和本地 endpoint；清理结果独立记录，新增只读 `/sandbox` 查看入口。
- 保留未确认清理记录，不自动重放或删除历史容器。Docker 实机隔离仍待验收。
- 全量回归 209 passed, 2 skipped；wheel 的 25 个运行时模块与源码一致。详情见 [v0.12](docs/UPGRADE-v0.12.md)。

## 0.11.0 — 2026-10-17

- 新增可选实验性 Docker Shell 隔离：本地 Linux 引擎、禁网、受限资源、过滤后的只读源码副本、命令写入丢弃、取消清理和容器内超时。
- 后端不可用不回退宿主机；Docker 模式禁用 MCP/LSP，恢复会话保留隔离设置。
- 新增 SQLite FTS5 增量代码索引、Python AST/其他语言词法摘要，提供 code_search/repo_map 工具及 `/search`、`/map`。
- 验收指纹容量提升到 20,000 文件 / 50 MB；超限保持未知。关闭宿主机源码枚举的 Git fsmonitor hook。
- 真实容器验收本机未运行，不能把参数测试视为隔离证明。详见 [v0.11](docs/UPGRADE-v0.11.md)。
- 全量 204 passed, 2 skipped；3,000 文件索引回归通过，wheel 的 25 个运行时模块与源码一致。

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
