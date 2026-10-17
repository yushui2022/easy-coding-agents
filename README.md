# Easy Coding Agent

**你的项目，你的模型，你的终端。**

Easy Coding Agent 是一个 Python CLI 编程助手。项目起于一次个人探索，也曾帮助作者找到工作；现在继续维护，让它成为可以日常使用、可以理解和改进的工具。

v0.2 重建了默认运行时：异步流式响应、文件差异确认、可中断命令、完整会话恢复、执行层模式权限，以及可脚本调用的 CLI。当前是开发版本，不宣称与 Claude Code / OpenCode 功能对等。

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

旧入口保存在 `legacy_main.py`，旧模块和历史数据原样保留；旧 Markdown 会话不自动导入新运行时。详见 [升级与迁移说明](docs/UPGRADE-v0.2.md)。

## 开发与验证

```powershell
$env:ECA_TEST_TMP = "G:\DevCache\Temp\easy-coding-agents\tests"
$env:PYTHONUTF8 = "1"
python -B -m unittest discover -s tests -v
```

测试使用离线响应和本地 HTTP 流式服务器，不调用付费模型。核心模块在 `eca/`，旧 `core/` 等模块不再由默认入口调用。新增工具同时定义 schema 和执行方法，并补充与真实失败相关的测试。

[验证记录](docs/VALIDATION-v0.2.md) · [升级说明](docs/UPGRADE-v0.2.md) · [原版 README](docs/legacy/README-v0.1.md)

暂未实现 MCP、原生 Anthropic/Responses 协议、OAuth 登录、LSP、子 Agent 或 Shell 沙箱。优先把现有开发闭环做好，再逐项扩展。

## 记忆研究模块

保留远端已有的 `agent_memory_core/`、`benchmark/` 及其测试，作为独立研究模块；新版 CLI 尚未自动接入该模块。原研究入口与说明见 [记忆研究 README](docs/legacy/README-memory.md)。旧入口 `legacy_main.py` 使用 `requirements-legacy.txt` 依赖。
