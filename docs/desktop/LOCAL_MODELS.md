# 本地模型：Ollama 与 vLLM

ECA 只要求 **OpenAI Chat Completions 兼容**的接口，所以 Ollama 和 vLLM 都能直接用，
不需要改代码。要跑得顺，需要满足一个前提：**模型和服务端要真的会返回工具调用**，
否则它只会聊天，不会读写文件。

## Ollama

### 桌面版

1. 打开「模型与设置」→「添加连接」
2. 提供方选 **Ollama 本地**（地址已预填 `http://localhost:11434/v1`）
3. 勾选 **本机服务无需密钥**
4. 点刷新模型列表，选一个支持工具调用的模型（qwen3 / qwen2.5 / llama3.1 系列）
5. 保存后设为桌面默认，或「用于当前项目」

### 命令行

```bash
ECA_API_KEY=local \
ECA_BASE_URL=http://127.0.0.1:11434/v1 \
ECA_MODEL=qwen3.8:27b-mlx \
eca
```

### ⚠️ 先确认上下文够用

Ollama 实际用的上下文不是模型的"最大上下文"，而是下面三者里最小的那个：

1. `OLLAMA_CONTEXT_LENGTH`（**没有**在 Modelfile 里写 `num_ctx` 时的默认值）
2. 模型 Modelfile 里的 `PARAMETER num_ctx`
3. 模型本身的原生上限

超出的部分会被**静默截断**，表现为"模型乱答、忘记任务、不调用工具"。

先查这台机器到底是多少，不要猜：

```bash
# 服务端的默认值（空 = 用 Ollama 内置默认）
launchctl getenv OLLAMA_CONTEXT_LENGTH

# 每个模型的原生上限 + 实际生效的 num_ctx + 是否支持工具
/Applications/Ollama.app/Contents/Resources/ollama show qwen3.8:27b-mlx
```

要看两个数：`context length`（原生上限）和 `Parameters → num_ctx`（实际生效）。
线上实测的这台 Mac Studio（64 GB）：

| 模型 | 原生上限 | 实际 num_ctx | 工具 | 32K 时实测占用 |
| --- | --- | --- | --- | --- |
| `qwen3.8:27b-mlx` | 262144 | 32768 | ✅ 且带视觉 | 约 32 GB |
| `qwen3.8-27b-abliterated-mlx:4bit` | 262144 | 32768 | ✅ | — |
| `qwen3.8-27b-abliterated:q4km` | 262144 | 32768 | ✅ | — |
| `ravenx-cyber:35b` | 262144 | 32768 | ✅ | — |

这台机器服务端已设 `OLLAMA_CONTEXT_LENGTH=32768`、`OLLAMA_FLASH_ATTENTION=1`、
`OLLAMA_KV_CACHE_TYPE=q8_0`，模型里也写了 `num_ctx 32768`，所以 **32768 就是实际生效值**，
正好等于 ECA 的默认 `context_window_tokens`，不需要再调。

**要往上调时两边都要改**：只改 Ollama 不会让 ECA 多用，只改 ECA 会被 Ollama 截断。

```bash
# 1) Ollama：换一个更大的 num_ctx（内存随之增长，KV cache 随上下文线性上升）
OLLAMA_CONTEXT_LENGTH=65536 open -a Ollama

# 2) ECA：告诉它这个窗口，否则它仍按 32768 预算
#    命令行
eca --context-window-tokens 65536
#    或项目里的 eca.toml
#    [agent]
#    context_window_tokens = 65536
```

按上面的实测比例估算，64K 大约会多占 10 GB 左右统一内存；64 GB 机器上还有余量，
但不要和 ComfyUI 这类吃显存的程序同时跑 128K。对话里用 `/context` 可以看当前估算。

## vLLM

vLLM 默认**不解析**工具调用，必须显式打开，否则模型输出的工具调用会变成普通文本，
ECA 会把它当成"回答"而不是"动作"：

```bash
vllm serve <模型路径或 HF 仓库名> \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --max-model-len 32768
```

`--tool-call-parser` 要跟模型匹配（常见取值：`hermes`、`mistral`、`llama3_json`、
`qwen3_coder` 等，见 vLLM 文档）。启动后在 ECA 里：

- 地址填 `http://localhost:8000/v1`
- 勾「本机服务无需密钥」（vLLM 默认不校验 key）
- 模型列表里选你 serve 的那个模型

## 这次补了什么兼容

本地服务和 OpenAI 的细节差异会让流式解析直接失败，已按实测补上：

| 差异 | 影响 | 处理 |
| --- | --- | --- |
| Ollama 用 `delta.reasoning` 而不是 `reasoning_content` | 思考阶段的输出不算进度，长思考会被当成"流卡死"掐断 | 两个字段都认，且计为进度 |
| vLLM / 部分网关把 `arguments` 直接给成对象 | 字符串拼接会报错 | 对象自动序列化为 JSON |
| 缺 `index` | 多工具调用排序会崩 | 按出现顺序补位 |
| 缺 `id` | 会被判为"工具调用身份无效" | 生成稳定且唯一的 id |
| 无参数工具给空字符串 | `json.loads('')` 抛异常 | 归一成 `{}` |
| 流结束没有 `finish_reason` | 判为"响应不完整" | 有工具调用时按 `tool_calls` 收尾 |

另外修了一个 macOS 专属问题：`/var`、`/tmp` 在 macOS 上是指向 `/private/...` 的符号链接，
原来的符号链接检查会把这当成"项目里有软链"，导致放在临时目录下的项目打不开
（`.eca` 状态目录、附件目录都会误报）。现在只检查项目根目录以内的部分。

## 验证

```bash
# 解析层单元测试（不需要模型）
python -B -m pytest -q tests/test_local_provider.py

# 真实 Electron + 真实后端 + 真实 Ollama
SMOKE_BASE_URL=http://127.0.0.1:11434/v1 \
SMOKE_MODEL=qwen3.8:27b-mlx \
SMOKE_API_KEY=local \
ECA_PYTHON=../.venv/bin/python \
node desktop/tests/mac-smoke.cjs
```

2026-10-29 实测（macOS 27.2 / arm64，Ollama 0.12，qwen3.8:27b-mlx）：
窗口启动、模型连接、模型列表、打开项目、发任务、审批、后端真实写文件全部通过，
渲染层无报错。同一模型走命令行也完成过"写文件 + 读回验证"。

## 已知限制

- 是否支持工具调用取决于**模型本身**，不是 ECA 能补的；不支持工具的模型只能聊天。
- 上下文设小了会被静默截断，见上文。
- 本地模型首字延迟可能到几十秒（JIT、prompt 处理、思考阶段），ECA 默认 120 秒请求超时；
  特别大的模型可以用 `--context-window-tokens` 调整上下文预算。
- vLLM 只在代码层面按 OpenAI 兼容格式适配并做了单元测试，未在本机（无 NVIDIA GPU）实机验证。
- 未签名的 macOS 构建每次重新打包后签名都会变，macOS 会认为它是"新应用"，
  第一次保存密钥可能弹出钥匙串授权框，必须点允许才能继续。用本机服务时勾
  **本机服务无需密钥** 可以完全绕开钥匙串。
