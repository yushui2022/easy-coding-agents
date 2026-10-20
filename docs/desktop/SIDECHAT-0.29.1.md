# 0.29.1 侧边聊天陶土界面

本轮针对右侧独立聊天，不改主对话首页及子 Agent 入口。

## 界面

- 背景沿用已有粗颗粒陶土纹理和深浅主题令牌。上下文卡片、空状态标志、按钮和输入区用柔和边缘、浅浮雕阴影区分层次。
- 顶部显示主对话记录数、采集时间与只读状态；更新上下文仍保留当前草稿及讨论记录。
- 空状态提供解释报错、梳理进展、比较方案三个入口，只填入草稿，等待用户发送。
- 输入区整合模型、发送和停止按钮，随文字增长。模型改为弹出菜单，显示连接名称与模型 ID；支持方向键、Home/End、Escape 和焦点返回。
- 消息支持安全 Markdown 与表格；讨论结果仍可放入主对话草稿。费用未定价时显示“未知”。
- 窄栏收起次要快捷键和费用文字，保留完整提示；顶部标签滚动条改为细样式。

## 本地验证

2026-10-20，Windows x64，隐藏的独立测试窗口和 G 盘临时项目。本地 HTTP 模型服务，不消耗付费 API。

- TypeScript 检查、生产构建、14 项桌面 Node 测试通过。
- 侧聊专项：深浅主题、360 CSS px 面板、窄窗口展开、草稿入口、上下文更新、模型菜单键盘操作、长模型名称、Enter/Shift+Enter/中文输入法、Markdown 表格、放入主对话草稿、连接错误、取消和重载不重放通过。
- 开发、打包与真实安装程序分别通过侧聊专项，每次 3 个本地模型请求，渲染异常为 0。
- 工作区回归：主任务与侧聊并行、浏览器、真实 PowerShell、资源清理、弹层和窄窗口通过。该次开发版本输入处理 P95 约 0.10 ms，侧聊取消确认 10 ms，未检测到长任务；这是本机测试数据，不代表所有会话或真实模型的响应速度。

复现命令，在 `desktop` 目录运行：

```powershell
$env:TEMP = 'G:\DevCache\Temp\easy-coding-agents'
$env:TMP = $env:TEMP
$env:ECA_PYTHON = (Resolve-Path '.venv\Scripts\python.exe').Path
npm run build
npm test
node tests/sidechat-design.cjs
node tests/workspace-e2e.cjs
```

设置 `ECA_TEST_EXE` 为打包或安装目录中的 `ECA Desktop.exe` 可验证相应程序；设置 `ECA_TEST_MODE=installed` 可单独保留安装版报告。

截图与报告位于 `output/playwright/sidechat-clay`，工作区报告位于 `output/playwright/workspace-development-report-0.29.1.json`。
安装包仍为未签名本地预览版，未在干净 Windows 虚拟机上验收。

安装包：`output/release/desktop/ECA-Desktop-0.29.1-x64-Setup.exe`，161,430,008 字节。
SHA-256：`32bf7736857792a490e6cd9729a5f141312fdf89cff2851115593ee36ff649af`。
用户退出后已更新至 `G:\Apps\ECA Desktop`：371 个程序文件与打包产物哈希一致，后端握手版本为 0.29.1，模型配置文件 SHA-256 保持不变。安装版再次通过上述侧聊专项，报告为 `output/playwright/sidechat-clay/report-installed.json`。
