# 使用手册

本手册说明当前 CLI 的配置、权限、恢复和记忆机制。简明入口见 [项目首页](../README.md)。

## 开始使用

需要 Python 3.11+。在项目根目录运行：

```powershell
python -m pip install -e . --cache-dir G:\DevCache\pip
python -B main.py --doctor
python -B main.py
```

也可双击 `run_agent.bat`。安装后从任何仓库使用：

```powershell
eca --cwd G:\Projects\your-project
```

本机可直接使用已安装的依赖运行 `python -B main.py`，不强制重建环境。新虚拟环境与依赖建议放在 G 盘。

在要操作的项目中配置 `.env`，或使用进程环境变量：

```dotenv
MODELSCOPE_API_KEY=your-key
MODEL_NAME=your-tool-capable-model
```

其他 OpenAI 兼容服务：

```dotenv
ECA_API_KEY=your-key
ECA_BASE_URL=https://your-provider.example/v1
ECA_MODEL=your-tool-capable-model
```

接口需要支持 **Chat Completions 流式输出与工具调用**。这不表示所有模型或厂商接口都已实测。原有 ModelScope 环境变量继续有效；本项目不读取或转售第三方订阅登录凭据。

可复制 `eca.example.toml` 为 `eca.toml`，设置模式、超时、上下文预算和自定义角色。密钥放环境变量，不写进 TOML。

## 日常使用

```text
code › 看一下这个项目的结构，找出启动方式。
code › 修复这个函数的边界问题，并运行相关测试。
code › /mode plan
plan › 先给我重构计划，不修改文件。
```

- 文字流式显示，工具调用和结果单独显示。
- 编辑前展示 unified diff，默认确认后才落盘。
- Shell 显示命令并请求确认，结果包括退出码与超时标记。
- Ctrl+C 停止当前任务并保留会话；输入区 Ctrl+C 取消输入。
- Ctrl+J 插入换行，Enter 发送；Shift+Tab 切换模式。
- 文件工具限定在当前项目，过滤常见密钥文件和内部状态目录。**Shell 不在沙箱中**，确认后具有当前用户的权限。

| 命令 | 功能 |
| --- | --- |
| `/help` | 命令帮助 |
| `/new` | 新会话，保留历史 |
| `/sessions` | 当前项目的历史会话 |
| `/resume ID` | 按 ID 前缀恢复；`latest` 恢复最近会话 |
| `/mode code\|plan\|chat` | Code 工具开发；Plan 只读与规划；Chat 无工具 |
| `/model NAME` | 当前进程切换模型 |
| `/permission ask\|accept-edits` | 每次确认编辑，或允许项目内编辑；不自动允许 Shell |
| `/agent NAME` | 选择 TOML `[profiles]` 中的角色；`off` 取消 |
| `/compact` | 请求模型总结上下文，消耗一次 API 请求；保留完整历史 |
| `/tasks` | 查看任务计划 |
| `/status` | 模型、模式、会话、状态与服务端报告的用量 |
| `/diff` | 查看相对 HEAD 的已跟踪文件差异；不包含未跟踪新文件 |
| `/export` | 导出 Markdown 到 `.eca/exports/` |
| `/exit` | 退出 |

Plan/Chat 的限制由工具分发器执行，不只依赖提示词。自动读取项目根目录的 `AGENTS.md` 和 `MEMORY.md`；角色配置只调整指令，不能绕过模式和权限。

## 脚本调用

```powershell
eca --cwd G:\Projects\demo --mode plan -p "分析项目入口" --json
eca --cwd G:\Projects\demo --accept-edits -p "为 README 修正一个拼写错误"
eca --cwd G:\Projects\demo --resume latest -p "继续总结上一轮工作"
eca --cwd G:\Projects\demo --list-sessions
```

一次性模式不弹确认框，默认拒绝需要确认的动作。`--accept-edits` 明确允许文件修改；只有你确实要授权任务中的所有 Shell 命令时，才追加 `--allow-shell`。它不限制命令访问范围。

`--json` 输出 JSONL 事件，包括 `text`、`tool`、`result`、`notice`、`error` 和最终 `status`。退出码：0 正常结束；1 配置/执行错误；2 达到轮数或重复调用限制；130 用户中断。正常结束不等于代码已通过测试，应检查实际输出。

## 会话与恢复

每个仓库使用独立 `.eca/`：SQLite 保存完整消息、工具调用及结果；操作日志记录工具开始与完成。恢复时补齐未完成的消息配对，对结果不确定的操作提示核实，不自动重放。单个项目同一时刻只允许一个 ECA 进程。

上下文窗口使用字符预算；必要时按完整用户轮次裁剪发送内容，原始历史不删。可手动 `/compact` 生成摘要。当前没有精确 token/cost 仪表盘。

旧入口保存在 `legacy_main.py`，旧模块和历史数据原样保留；旧 Markdown 会话不自动导入新运行时。详见 [升级与迁移说明](UPGRADE-v0.2.md)。

## 开发与验证

```powershell
$env:ECA_TEST_TMP = "G:\DevCache\Temp\easy-coding-agents\tests"
$env:PYTHONUTF8 = "1"
python -m pip install -r requirements-dev.txt
python -B -m pytest -q
```

测试使用离线响应和本地 HTTP 流式服务器，不调用付费模型。核心模块在 `eca/`，旧 `core/` 等模块不再由默认入口调用。新增工具同时定义 schema 和执行方法，并补充与真实失败相关的测试。

[验证记录](VALIDATION-v0.2.md) · [升级说明](UPGRADE-v0.2.md) · [原版 README](legacy/README-v0.1.md)

暂未实现 MCP、Responses 协议、OAuth 登录、LSP、子 Agent 或 Shell 沙箱。优先把现有开发闭环做好，再逐项扩展。

## 记忆研究模块

保留远端已有的 `agent_memory_core/`、`benchmark/` 及其测试，作为独立研究模块；v0.5 CLI 通过受控适配层复用其 SQLite/FTS 存储检索，研究模块的自动声明提取和任务状态门控尚未接入。原研究入口与说明见 [记忆研究 README](legacy/README-memory.md)。旧入口 `legacy_main.py` 使用 `requirements-legacy.txt` 依赖。

## 直接连接 Anthropic

兼容接口仍为默认值。使用 Claude 原生 Messages API 时，在目标项目 `.env` 配置：

```dotenv
ECA_API_FORMAT=anthropic
ANTHROPIC_API_KEY=your_key_here
ECA_MODEL=your-claude-model-id
ANTHROPIC_BASE_URL=https://api.anthropic.com/v1
```

模型 ID 使用你的账号实际可用值。也可通过 `--api-format anthropic --model MODEL_ID` 指定。
若已有 `eca.toml`，同步修改其中的 `api_key_env`、`base_url` 和 `model`；配置了 `api_key_env` 时会从指定变量读取密钥；否则优先使用 `ECA_API_KEY`。`ECA_BASE_URL` 优先于 TOML 地址。
先运行 `python -B -m eca --doctor` 检查协议、地址和密钥是否配置（不会发起 API 请求）。

支持文本流、工具调用、多个工具结果回传、会话恢复与 `/compact`。`[agent].max_output_tokens` 控制原生接口响应预算，默认 8192。
断流、输出截断、损坏的工具参数或错误事件不会交给工具执行。临时网络错误在输出文本前可有限重试；不启用 Thinking、服务端工具、图片或订阅 OAuth。

CI 模板保存在 [docs/ci-workflow.yml](ci-workflow.yml)。当前 GitHub 凭据缺少 `workflow` 权限，尚未启用 Actions；取得权限后将模板放入 `.github/workflows/tests.yml`。
协议实现依据 [Anthropic 流式协议文档](https://platform.claude.com/docs/en/build-with-claude/streaming)，验证记录见 [v0.3 验证说明](VALIDATION-v0.3.md)。

## 检查、撤销与长任务恢复

每次 `write` / `edit` 都会在落盘前保存修改前后内容，独立于 Git，包含新建文件。写入前仍沿用逐次差异确认；`--accept-edits` 才会跳过该确认。

| 操作 | 交互命令 | 脚本命令（默认最近会话） |
| --- | --- | --- |
| 查看最近 100 次文件编辑 | `/changes` | `eca --changes --json` |
| 查看单次编辑的差异 | `/changes 12` | `eca --changes 12 --json` |
| 标记已审阅接受 | `/accept 12` | `eca --accept-change 12 --json` |
| 撤销单次文件编辑 | `/undo 12` | `eca --undo 12 --json` |
| 继续未完成工作 | `/continue` | `eca --resume latest -p "继续之前的任务，先检查中断状态"` |

ID 对应一次文件编辑，同一文件多次修改应按 ID 从新到旧撤销。`/accept` 是对已经写入的修改标记审阅完成，不会提交 Git，也不会阻止后续撤销。
撤销将文件恢复到本次编辑前的内容，保留用户原有未提交修改及 Git 暂存区；新文件会被删除。如果当前内容已经不同于记录结果，撤销会拒绝覆盖。
撤销结果也会写入会话，提醒模型重新读取文件，避免直接重新应用被撤销的修改。

快照位于 `.eca/sessions.sqlite3`，只覆盖新版文件工具，不覆盖 Shell、外部编辑器、文件权限或目录结构变更。不要删除 `.eca` 后再期待撤销历史可用。
写入中崩溃可能留下 `prepared`，撤销中崩溃可能留下 `undoing`；检查文件后对该 ID 执行 `/undo`，仅在内容与记录一致时恢复，不会自动重放工具。

长任务新增：

- 上下文达到字符预算约 85% 时，自动摘要较早内容，保留完整磁盘历史和最近的完整工具调用组。摘要会消耗模型请求；可在 `[agent]` 设置 `auto_compact = false`。
- 不足以安全压缩或摘要后仍超限时明确停止，不丢弃存档。摘要不是无损记忆，需要时仍应重新读文件核实。
- 临时网络错误最多重试 2 次（`network_retries = 0..5`），退避等待可中断；已经显示部分文本、参数错误和认证失败不自动重试。重试模型请求不会重放之前的工具。重试可能产生额外 API 费用。
- `/status` 显示持久化的停止原因和恢复建议。`/continue` 根据现有会话继续推理，并要求先检查不确定的副作用。

详见 [v0.4 验证记录](VALIDATION-v0.4.md)。

## 有来源的项目记忆与分级规则

新版 CLI 复用 `agent_memory_core` 的 SQLite/全文检索，将受控项目记忆保存在 `.eca/knowledge.sqlite3`。它与旧 `.agent_memory` 研究数据库隔离，不自动导入旧模型结论。

- `/memory`：查看最近 200 条记忆的 ID、内容、来源、时间和有效性。
- `/remember 项目约束`：由你显式确认并保存约束，供之后的会话使用。模型没有自动保存约束的工具。
- `/forget ID`：从记忆表和检索索引移除该条。纠正记忆时先删除旧项，再保存正确内容。已有会话文本和工具日志不随之抹除。

自动记录仅限识别到的测试命令（pytest、unittest、npm test、cargo test、go test 等）实际返回 `exit_code=0` 且未超时，并且执行前后代码指纹一致。每条记录引用原会话/action 日志，描述的是历史退出码，不能替代当前任务的验证；不会把助手的“测试通过”口头结论写成事实。

新会话按用户请求检索历史命令，并注入显式确认的项目约束。命令对应的代码指纹不再匹配时显示 `stale`，不会作为有效项目记忆注入。指纹最多检查 2000 个文件、总计 20 MB、单文件 2 MB；超过范围或无法检查时不认定有效。Git 项目检查非忽略文件，排除缓存、构建目录及受保护路径；非 Git 项目使用有界文件遍历。指纹不涵盖依赖安装状态、环境变量或外部服务，因此匹配也不代表现在一定能通过。

可在 `[agent]` 设置 `project_memory = false` 关闭自动记录和注入；手动查看、保存、删除仍可使用。记忆只存本地，但注入的相关条目会随正常模型请求发送到所选 API。不要保存密钥；只做了有限的凭据识别和当前 API key 脱敏。

修改文件前，CLI 按项目根目录到文件所在目录加载各级 `AGENTS.md`，标明规则文件路径。深层规则仅作用于其目录，用户明确指令优先。新规则会先通过工具结果返回模型，本批工具调用不会直接越过规则提示写入；规则变化或上下文压缩后会重新确认模型已收到规则。超长规则会阻止编辑并提示调整，不会静默截断后放行。Shell 不受这一文件工具保护覆盖。

这不是完整的语义规则执行器：CLI 保证适用规则先进入模型上下文，模型仍需正确理解和遵守。根目录 `MEMORY.md` 仅标为未经验证的项目笔记。

验证记录见 [v0.5 验证说明](VALIDATION-v0.5.md)。
