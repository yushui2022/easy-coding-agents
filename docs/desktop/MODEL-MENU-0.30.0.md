# 0.30.0 模型选择与推理强度

主对话与侧边聊天共用模型弹层，沿用陶土色、圆角边缘和浅浮雕控件。

## 使用方式

- 点击输入框里的模型，按模型 ID、连接名称或服务商搜索。
- 最近选择或发送过请求的连接排在前面，最多保留六个；记录按连接 ID 去重，同名模型的不同连接不会混淆。连接名称显示在模型下方，勾号对应实际连接。
- 选择模型后面板保持打开，可继续调整推理强度。用滑杆、档位文字或键盘方向键调整；Escape 关闭并返回模型按钮。
- 主对话保留“跟随桌面默认”“沿用项目配置”和连接管理入口。侧聊选择只影响侧聊。
- 已打开项目时，强度保存在对应会话中，按协议、端点、模型区分；主对话与侧聊独立。未打开项目时，调整的是桌面默认连接的强度。不会改写项目 `.env` 或 `eca.toml`。
- 运行期间不可修改当前任务的模型参数；空闲侧聊的强度可在主任务运行时独立修改。

## 档位语义与支持范围

“默认”表示不向 API 发送强度参数，并关闭 ECA 旧预设的覆盖；“关闭”发送 `none`，两者不同。

DeepSeek Flash/V4 模型提供默认、关闭、低、中、高、最高。按 [DeepSeek 文档](https://api-docs.deepseek.com/guides/thinking_mode/)，`medium` 是兼容值，服务端按 `high` 处理；界面明确提示，不将其描述为独立算力档位。

已识别的 OpenAI 推理模型使用各自支持的档位，Chat Completions 发送 `reasoning_effort`，Responses 发送 `reasoning.effort`。例如 GPT-6 Astra 不提供关闭选项。能力表依据 [OpenAI reasoning 文档](https://developers.openai.com/api/docs/guides/reasoning) 保守开放，后续新模型需要更新能力表。

当前原生 Anthropic 适配器尚未实现强度参数；未知兼容服务和未识别模型仍可正常选择，但不显示可操作的强度滑杆，不声称已经支持。兼容网关对参数的实际支持以其服务为准。

## 实现与验证入口

- `ModelMenu.tsx` / `model-menu.css`：共用面板、搜索、选择状态和滑杆，兼容深浅主题及窄窗口。
- `connections.ts`：最近连接与未打开项目前的默认强度；保留现有加密密钥。
- `reasoning.py`：唯一的档位描述与校验入口，会话设置按模型身份保存；只替换 Provider，不重建消息、工具、权限或共享预算。
- `desktop_rpc.py` / `side_chat.py`：独立设置、忙碌拒绝、会话校验和恢复。

在仓库根目录：

```powershell
$env:TEMP = 'G:\DevCache\Temp\easy-coding-agents'
$env:TMP = $env:TEMP
$env:ECA_TEST_TMP = $env:TEMP
$env:PYTHONPATH = 'tests'
desktop/.venv/Scripts/python.exe -B -m unittest test_desktop_reasoning test_side_chat test_thinking_modes test_desktop_rpc -q
npm --prefix desktop run build
npm --prefix desktop test
node desktop/tests/model-menu-e2e.cjs
```

`ECA_TEST_EXE` 可指向打包或安装后的 `ECA Desktop.exe`，`ECA_TEST_MODE=installed` 单独保留安装版报告。测试使用独立临时项目、隐藏窗口和本地 HTTP 服务，不调用付费模型。截图和报告在 `output/playwright/model-menu`。

本版本仍是未签名 Windows 预览包；本机验证不等于干净 Windows 环境验收。

## 本次验收（2026-10-20）

- Python 回归 28 项、桌面 Node 测试 15 项、TypeScript 检查及构建通过。
- 开发版完整流程通过，包括配置、授权、实际文件修改与验证、取消、恢复和后端异常处理；无渲染器错误。
- 打包版模型菜单通过 7 次本地 HTTP 请求验收，核对六个 DeepSeek 档位实际发送的参数。另验证搜索、最近连接、同名模型区分、两侧独立设置、键盘操作、刷新保留设置和运行中拒绝修改。
- 打包版工作区通过侧聊并行、真实终端、浏览器预览、中文路径、取消与资源清理检查；无渲染器错误。
- 本机已安装至 `G:\Apps\ECA Desktop`，371 个程序文件与构建产物一致，后端握手版本为 `0.30.0`。安装前后模型配置文件 SHA256 一致。
- 安装版再次通过模型菜单完整流程：7 次本地 HTTP 请求，六个档位、侧聊独立设置、刷新与取消均通过，无渲染器错误。报告为 `output/playwright/model-menu/report-installed.json`。
- 所有模型请求均使用隔离的本地模拟服务，付费 API 调用为零。未将这些测试等同于真实模型推理效果评测。

安装包：`output/release/desktop/ECA-Desktop-0.30.0-x64-Setup.exe`（161,438,232 字节）。

SHA256：`4596ee0a3df57819d63d0af128c0356aba4b817856e56964baf01f8c689607fc`。
