# v0.7：并行工作区、MCP 扩展、Responses 与 LSP

这轮扩展了五个方向。它仍是开发中的 CLI，并不等同于成熟产品的全部能力。

## 并行与执行隔离

模型可使用 `delegate_parallel(tasks)` 同时运行独立子任务，每项包含 `task` 和可选 `mode`（默认 `plan`）。总次数受 `subagent_max_calls` 限制（默认 3），单批最多 8 个；沿用轮数、时间和费用账本。父任务取消会取消全部子任务并保存状态。JSONL 的 `subagent_progress` 带子会话 ID。

每个子任务在 `.eca/workspaces/<session-id>` 使用独立源码快照，包含当前未提交文件内容。Git 项目遵守忽略规则，并保留已跟踪文件的当前内容；非 Git 目录使用有界文件遍历。复制时排除 `.git`、`.eca`、`.env`、密钥扩展名及既有缓存目录；单文件最大 2 MB，总计最大 20 MB / 2000 个文件，超限明确失败。它不是 Git worktree，没有 Git 历史、索引或依赖目录。

隔离子任务只能通过文件工具工作，执行层禁止 Shell、MCP、LSP 和递归委派；恢复子会话后仍使用原隔离目录。`delegate` 为兼容保留原来的共享目录、顺序子任务行为。模型请求仍会联网。

使用 `merge_agent(session, paths)` 选择子任务文件导入父项目：

- 先对整组选中文件检查父目录是否仍与快照一致；不一致则拒绝覆盖。
- 每个写入遵守作用域 AGENTS.md、diff 审批、并发修改检查及持久修改日志，可用 `/undo` 撤销。
- 只导入 UTF-8 文本文件；删除、二进制、Git 合并需手动处理。
- 多文件写入不是事务，取消、审批拒绝或新冲突可能留下已导入的部分，应查看 `/changes`。
- 主 Agent 在合并后执行测试。子报告不是验证结果。

`/agents` 查看子会话，`/resume ID` 检查隔离目录的修改，恢复父会话后再合并。工作区保留用于审阅，没有自动删除。可在不再需要恢复时手动归档；不要把它们当作必然可丢弃的缓存。

**边界：这是文件工具隔离，不是操作系统沙箱。** 主 Agent 和旧式 `delegate` 的 Shell、用户批准启动的 MCP/LSP 服务仍拥有用户权限。尚无容器、系统级网络限制、独立 Git 分支或自动冲突解决。

## MCP 生命周期与资源/提示词

安装 `pip install -e ".[mcp]"`，沿用 [v0.6 配置](EXTENSIONS-v0.6.md)。在 CLI 中每个服务使用一个连接所有者任务，复用 stdio 进程或 HTTP 连接，所有 SDK 取消作用域都在同一任务内结束。配置或映射凭据变化时关闭旧连接。

新增工具：

| 工具 | 参数与用途 |
| --- | --- |
| `mcp_resources` | `server`，`operation=list/templates/read`；read 需要 `uri` |
| `mcp_prompts` | `server`；不带 `name` 列表，带 `name` 和可选字符串参数表 `arguments` 获取提示词 |

每次操作仍需审批。远端提示词仅作为不可信数据返回，不自动作为系统/用户指令执行。只返回文本资源和文本提示内容。列表有页数、条数上限。工具调用继续重新发现与校验 schema，不缓存过期目录。

`/mcp` 显示配置与连接状态；`/mcp disconnect NAME` 主动断开。退出或切换会话时关闭连接。超时、取消和错误关闭相关连接，不自动重放；之后的新操作可重新连接。

协议由已安装的官方 Python SDK 协商；不能将持久连接等同于跨协议版本的服务端会话保证。本轮未宣称支持所有最新 MCP 扩展。尚无 OAuth 登录、资源订阅、sampling、elicitation 或长任务恢复。HTTP 鉴权仍使用映射环境变量的 headers。

## 模型接入：Responses API

```toml
[agent]
api_format = "responses"
base_url = "https://api.openai.com/v1"
model = "YOUR_MODEL_ID"
api_key_env = "OPENAI_API_KEY"
reasoning_effort = "low" # 仅在所选模型支持时设置
max_output_tokens = 8192
```

也可用 `--api-format responses`。适配器使用流式 Responses，`store=false`，将工具结果映射成 `function_call_output`，持久保存并回传 reasoning 的 encrypted_content，拒绝未完成响应中的工具调用。输入、缓存输入和输出用量纳入原有请求账本。

`reasoning_effort` 同时可用于支持此参数的 Chat Completions 服务；Anthropic 仍使用既有 Messages 适配器，没有新增 thinking 模式。切换到 Chat Completions 时不会发送 Responses 专属字段。依赖要求 `openai>=1.99,<3`。

支持程度取决于服务商。无订阅 OAuth、自动模型目录、动态能力协商或多模态输入。本轮使用模拟服务验证协议行为，未调用付费模型。

## LSP

用户自行安装语言服务器，并在项目 `eca.toml` 配置，例如：

```toml
[lsp_servers.python]
command = "pyright-langserver"
args = ["--stdio"]
language_id = "python"
timeout = 30
```

模型工具 `lsp(server, operation, path, line=1, character=0)` 支持 `definition`、`references`、`hover`、`symbols` 和 `diagnostics`。行号从 1 开始，字符偏移为从 0 开始的 UTF-16 单元。diagnostics 使用 LSP pull diagnostics；服务器不支持时明确报错，不能当作“无诊断”。

启动前审批；单次运行可用 `--allow-lsp SERVER` 授权指定服务，`--allow-shell` 不会自动授权 LSP。初始化后发送磁盘内容的 didOpen，再查询、shutdown、exit；超时或取消清理进程树。每次查询启动一个服务器，尚未复用 LSP 索引。客户端拒绝服务端主动请求（包括 workspace/applyEdit），不实现自动重命名或 WorkspaceEdit。无自动安装语言服务器。

协议参考：[Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)、[MCP 服务能力](https://modelcontextprotocol.io/specification/2025-06-18/server)、[LSP 3.17](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/)。
