# MCP、子 Agent 与费用账本

## MCP

先安装可选依赖：`python -m pip install -e ".[mcp]"`。实现使用 [官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk) 1.x。默认安装不需要 MCP 依赖。

在目标项目 `eca.toml` 中添加：

```toml
[mcp_servers.local]
transport = "stdio"
command = "python"
args = ["G:/Projects/my-mcp/server.py"]
timeout = 30
env = { SERVICE_TOKEN = "MY_SERVICE_TOKEN" }

[mcp_servers.remote]
transport = "http"
url = "https://example.com/mcp"
headers = { Authorization = "MY_MCP_AUTHORIZATION" }
```

`env` 与 `headers` 的值是环境变量名，从项目 `.env` 或进程环境读取；不要直接填写密钥。Authorization 对应变量应包含完整 `Bearer ...` 值。配置中的 command/args 不应含密钥。HTTP 不跟随重定向，请填最终端点。

`/mcp` 仅列出配置，不连接。告诉模型使用某个服务后，它可以调用 `mcp_list` 获取 schema，再用 `mcp_call` 调用工具。每次操作重新建立并关闭 MCP 会话，启动本地服务也需要批准；不支持依赖跨调用内存状态的服务器。服务列表最多 200 个工具、10 页，输出受 `output_limit` 限制。

单次脚本显式授权指定服务：

```sh
eca -p "使用 local 服务查询工具并完成任务" --allow-mcp local
```

可以重复 `--allow-mcp` 指定多个服务。`--allow-shell` 和 `--accept-edits` 不授权 MCP。plan/chat 模式不允许 MCP。工具调用会先记入 action 日志；超时、中断不自动重放，外部副作用需要自行核对。

只接入 tools/list、tools/call；保留文本、结构化结果和 isError，二进制媒体省略。暂不支持资源/提示词浏览、OAuth、sampling、elicitation、长任务协议或自动重连。MCP 服务权限由其进程/账户决定，不受 ECA 文件范围或撤销机制保护。服务描述、annotations 与结果不能绕过审批。

## 子 Agent

模型可调用 `delegate(task, mode)`，默认 `plan`；也可以直接要求“让子 Agent 分析 X，并给出验收检查”。子任务使用父会话当前配置的模型。新会话只接收任务文本与项目规则，不复制父会话聊天记录；开启项目记忆时仍可检索该项目的来源记录。

- `plan` 子任务只读文件、搜索、规划和提问；父会话为 plan 时不能创建 code 子任务。
- `code` 子任务沿用父会话文件/Shell 权限和工作目录，修改有自己的快照。子任务不能继续委派，也不能调用 MCP；恢复子会话后仍保持此限制。
- 子任务顺序执行，不是并行分支或隔离工作树。父任务取消会传递到当前子任务；已发生的修改不会自动回滚。
- `/agents` 查看子会话 ID；`/resume ID` 后可 `/changes`、`/undo ID` 审阅或撤销该子任务的文件修改。可再恢复原父会话继续。
- 返回父会话的报告包含状态、会话 ID、摘要与停止原因；子任务自报完成不等于验收通过。

在 `[agent]` 中配置 `subagent_max_calls = 3`、`subagent_max_turns = 6`、`subagent_timeout = 180`。限制按每次父任务计算，子任务轮数不会超过父会话的 max_turns 设置；子任务的额外调用计入同一费用账本。

## 用量与费用

`/usage` 或 `eca --usage --resume SESSION --json` 读取本地账本，不调用模型，损坏的模型配置也不影响查看。`/status` 和 JSONL `usage` 事件包含汇总。账本在 `.eca/sessions.sqlite3` 的 `usage_requests` 表中，按请求保存会话、根会话、模型、用途、状态、API 原始 usage、规范化 token、价格快照和费用。

默认不猜测价格。按模型 ID 配置每百万 token 价格；以下**仅演示计算格式，不是官方价格**：

```toml
[pricing."YOUR_MODEL_ID"]
currency = "USD"
input = "1.00"
output = "2.00"
cache_read = "0.10"
cache_write = "1.25"
cache_write_5m = "1.25"
cache_write_1h = "2.00"
```

OpenAI 兼容接口输入减去明确报告的缓存命中量，输出已经包含 reasoning token，不重复计费。Anthropic input_tokens、缓存读取与缓存创建量分别计数；5 分钟/1 小时创建量按 API 分类分别定价。普通缓存创建使用 cache_write。不存在的分类不需要填价，有实际 token 却缺少价格时该请求费用保持未知。

每次请求发出前保存记录，返回后写 usage 和 Decimal 计算结果；重试独立计数，压缩 purpose 为 compact，子任务关联根会话。修改价格只影响之后的请求。多个币种分别汇总，不做隐式汇率转换。新版本无法补回旧会话没有记录的历史费用。

`reported_tokens` 是已获取用量，`priced_subtotals` 是可定价部分；`incomplete_usage_requests` / `incomplete_cost_requests` 非零时不能当总量或最终账单。失败或取消可能只有部分 usage；进程崩溃后的 pending 请求也不能按零处理。API 省略缓存分类且配置了不同缓存价格时，不生成精确费用。

`[agent].stream_usage = true` 默认请求 OpenAI 流式 usage。不支持 stream_options 的兼容服务可设为 false，但若服务不返回 usage，则用量和费用保持未知。请求数量不等于计费次数；免费额度、阶梯折扣、税费、外部 MCP 服务费用不在本地计算范围，最终以供应商账单为准。
