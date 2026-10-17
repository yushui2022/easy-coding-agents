# v0.13：可选多模型 Worker，单 API 默认不变

只配置原来的一个 API 即可正常使用。`worker_profiles` 默认 `[]`，不会启用额外模型，不会下载或启动本地模型；原有子 Agent 继续继承当前主模型。单纯定义一个模型档案也不会自动允许主 Agent 向它派任务。

## 按需开启

在现有 `eca.toml` 的 `[agent]` 段增加一行（不要重复创建同名段）：

```toml
worker_profiles = ["local_helper"]
```

然后在文件末尾增加可选模型档案：

```toml
[model_profiles.local_helper]
model = "YOUR_INSTALLED_TOOL_CAPABLE_MODEL"
base_url = "http://localhost:11434/v1"
api_format = "openai"
api_key_env = "LOCAL_MODEL_KEY"
stream_usage = false
max_output_tokens = 2048
context_chars = 16000
```

`model` 必须换成你已安装且通过测试的模型 ID。自行启动兼容 OpenAI Chat Completions 的本地服务；无需鉴权的本地服务也需要在 `.env` 设置 `LOCAL_MODEL_KEY=local`，这是客户端占位值，不是另一个付费 API。需要鉴权的服务应填真实密钥。模型文件和缓存建议放在 G 盘。

云端 Worker 使用相同配置方式：独立的 model、base_url、api_format 和密钥环境变量。可以配置多个档案，但仅 `worker_profiles` 列出的名称允许用于委派。`/models` 显示每个档案的 `worker_enabled`。

## 运行行为

启用后，主模型可以在 `delegate` 或 `delegate_parallel` 的各子任务里设置 `model_profile`。省略此参数仍使用当前主模型；不会默认把所有任务交给小模型。主模型选择是否委派和选择哪个已启用档案，程序负责强制执行白名单、权限、轮数、并发数和超时上限。

每个子 Agent 获得独立模型设置，主 Agent 的 API、模型和上下文不被切换。并行任务在复制源码前解析项目 `.env` 中的凭据，密钥不写进会话，不复制 `.env` 到隔离工作区。子会话记录模型档案，已有用量账本按实际子模型记录并归集到父任务。缺失用量或价格仍显示未知，不把本地计算资源成本当成零。

Worker 故障会返回失败，不会静默换模型、自动升级费用或重放工具。主 Agent 可以依据返回的证据决定下一步。不同模型的历史不直接互相回放；父 Agent 接收有界子任务摘要及修改信息。

## 小模型边界

1B/2B 是参数规模，不是能力保证。当前 Worker 仍使用 Agent 工具调用协议，要求具体服务/模型支持流式响应和工具调用；不支持的模型不能仅靠填写 API 地址变成可靠编码 Worker。上下文上限按服务和模型实际能力设置；`context_chars` 是字符预算，不是 token 数。

优先尝试只读检索、信息提取和小范围分析。默认子任务 `mode=plan`，保持只读；编码任务仍须明确设置 code 模式。子任务结果是待核对材料，不是测试通过证明。`delegate` 共享目录，涉及并行修改时使用 `delegate_parallel` 的隔离目录和显式合并。没有新增递归蜂群、自动下载、自动扩容或无上限调度。

## 验证

新增 7 项本地回归通过，覆盖单 API 兼容、模型/凭据独立、混合模型并行、隔离目录不含 `.env`、未启用模型拒绝、schema 不污染、配置校验、实际子模型记账及失败不静默回退。与既有模型/LSP 测试联合运行 17 项通过，新增的最终 7 项单独通过。未调用付费 API，未下载本地模型；尚未对具体 1B/2B 模型作能力验收。

最终完整回归：**216 passed, 2 skipped**，耗时 364.42 秒。

安装包 `easy_coding_agent-0.13.0-py3-none-any.whl` 已构建，25 个运行时模块与源码逐字节一致，大小 95,011 字节，SHA-256：`e4f4e1101bafd8b69d6cd5738eba0e835241eff6c1130fd06194ff9aa67ff6af`。示例 TOML 已检查，Worker 默认关闭。
