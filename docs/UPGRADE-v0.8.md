# v0.8：从功能接入到可靠协作

## 研究依据与取舍

2026-10-17 阅读了以下一手材料。没有直接复制第三方实现代码；本项目仍使用自己的 Python 运行时。

| 参考 | 借鉴点 | ECA 的落地 |
| --- | --- | --- |
| [Pi README](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/README.md) | 小核心，工作流能力保持模块边界 | 调度、语言服务器、模型配置分别留在独立模块，CLI 负责交互 |
| [Pi 子 Agent 示例](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/examples/extensions/subagent/index.ts) | 任务数与并发数分开限制；结构化返回失败与进度 | 独立并发配置、queued/running 状态、单任务失败不取消其他任务、返回改动清单 |
| [Pi 模型配置](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/models.md) | 接口协议、鉴权来源和模型行为应一起配置；恢复模型选择 | 命名模型配置，切换时重建客户端；会话只保存配置名，重新解析凭据 |
| [OpenCode LSP 文档](https://opencode.ai/docs/lsp/)及[公开 LSP 服务源码](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/lsp/lsp.ts) | 将语言服务器作为有生命周期的服务，重视诊断反馈 | 会话内连接复用、文件同步、push/pull 诊断、显式状态与断开 |
| [OpenCode MCP 文档](https://opencode.ai/docs/mcp-servers/) | 连接状态、超时和显式管理是工具接入的一部分 | 真实存活状态、最近错误类型、每服务操作队列、新操作重新连接 |

Pi 的子任务示例不等同于内置文件沙箱；ECA 没有因此取消自己的审批和隔离限制。参考项目功能很多，这次优先修复生命周期与状态正确性，没有宣称实现其所有能力。链接指向移动分支/在线文档，未来可能变化。

## 并行任务

```toml
[agent]
subagent_max_calls = 6 # 每次父任务最多派发的子任务数
subagent_concurrency = 2 # 同时运行的上限，1..8，默认 2
subagent_timeout = 180 # 从开始执行计时，排队时间不占用该限额
```

一批仍最多 8 个任务。任务依次进入 preparing、queued、running 和最终状态；同一批中某个子 Agent 初始化/执行失败，不再让其他任务一并失败。父任务取消会停止运行与排队中的任务，保留状态。若复制源码失败，已创建的子任务会标记 error，保留标识和可能的部分工作区，不自动删除。

子任务结果新增 `stop_reason` 和最多 200 项的 `changes` 清单。`/agents` 列出状态，`/agents ID` 查看某个子会话的文件工具改动（支持唯一 ID 前缀）。查看状态不会执行恢复逻辑；合并拒绝 preparing/queued/running 的任务，不会先将它们改成 interrupted。

源码快照、显式选择文件合并、冲突检查和撤销继续沿用 [v0.7](UPGRADE-v0.7.md)。不是 Git worktree，不复制依赖；隔离子任务仍不能运行 Shell、MCP、LSP 或递归委派。没有系统级沙箱。

## LSP 长连接与诊断

```toml
[lsp_servers.python]
command = "pyright-langserver"
args = ["--stdio"]
language_id = "python"
timeout = 30
diagnostic_timeout = 2 # 等待 push 诊断的上限，1..30 秒
```

仍需自己安装语言服务器。首次启动需批准；审批说明进程会保持到断开。之后的查询复用同一个服务，不反复启动/索引。`/lsp` 查看状态；`/lsp disconnect python` 关闭。切换会话、退出、查询超时或取消会清理相应进程；新的查询重新启动时再次审批。服务配置变化也重新启动。

每次查询前读取目标文件的当前磁盘内容，发送 didOpen 或递增版本的 didChange；最多保持 32 个打开文档，超出时关闭最早文档。尚未监听磁盘变化，也不会在每次写入后自动等待所有语言服务器；需要模型主动使用 LSP 工具查询。

`lsp(..., operation="diagnostics")` 的结果有明确语义：

- `status=reported, source=pull`：服务器声明支持 pull diagnostics，返回完整报告。
- `status=reported, source=push, freshness=versioned`：收到与当前文档版本相符的推送，丢弃旧版本通知。
- `freshness=unversioned`：服务器未附文档版本，不能证明报告一定对应最新内容。
- `status=pending`：限时内没有收到当前报告，**不等于没有错误**。

新增 `implementation` 查询，已有 definition/references/hover/symbols 继续可用。位置仍为 1-based 行、0-based UTF-16 字符。支持服务器查询空配置与工作区信息，仍拒绝 `workspace/applyEdit` 等其他服务端请求。没有自动重命名、动态注册能力、任意服务端命令执行或自动安装。

## 模型配置与恢复

```toml
[agent]
model_profile = "fast" # 可选默认配置

[model_profiles.fast]
model = "YOUR_FAST_MODEL"
base_url = "https://YOUR_PROVIDER/v1"
api_format = "openai"
api_key_env = "FAST_MODEL_KEY"
stream_usage = true
max_output_tokens = 4096

[model_profiles.deep]
model = "YOUR_REASONING_MODEL"
base_url = "https://YOUR_RESPONSES_PROVIDER/v1"
api_format = "responses"
api_key_env = "DEEP_MODEL_KEY"
reasoning_effort = "low"
```

- `/models`：列出配置名、模型和协议，不连接远端。
- `/model @deep`：切换整套接口配置，关闭旧客户端与工具连接。
- `eca --model-profile deep -p "任务"`：单次任务选择。
- `/model MODEL_ID`：保留当前接口，仅修改模型 ID；清除命名配置的恢复标记。

每套配置必须明确 model/base_url/api_format/api_key_env。其他可选字段为 reasoning_effort、stream_usage、max_output_tokens、context_chars；未指定的可选模型参数回到默认值，不继承上一个模型的专属设置。不会将一个配置的 key 自动用于另一个配置。密钥仍从项目 `.env` 或环境变量解析，不写入会话。

显式命名配置覆盖通用环境中的模型/接口选择；CLI 的 --model/--base-url/--api-format 则覆盖配置，对这种临时组合不保存配置名。配置文件在 CLI 启动时加载；恢复会话按当前已加载配置表解析保存的配置名，并重新读取凭据。修改 TOML 后需重启 CLI，新配置会影响恢复；不冻结历史密钥。离线 `--changes/--undo` 不依赖模型配置仍然可用。价格仍由 `[pricing."MODEL_ID"]` 提供，不做自动价格同步或订阅 OAuth。

Responses 的加密 reasoning 项现在绑定模型 ID 与接口地址。同一配置继续保留；切换模型或接口后只迁移可移植的文本和函数调用记录，不把旧加密推理数据送到其他模型。旧版没有来源标记的 reasoning 项同样不复用。摘要请求只包含可读文本和工具记录，不把加密 reasoning 当作正文再发送给模型；完整历史中的原始数据仍保留。

## MCP 状态与取消

`/mcp` 检查连接所有者任务是否已经结束，不再将存在于字典中的死连接显示为 connected；失败只显示错误类型，不回显服务端错误正文或凭据。相同服务的操作串行执行，取消排队中的请求不会关闭另一个正在运行的操作。

已断开的连接可在下一次明确操作时重建；失败的工具调用本身不重放。授权、schema 校验、资源与提示词的不可信数据边界均保持。OAuth、订阅、sampling/elicitation 仍未实现。
