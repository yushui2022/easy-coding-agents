# ECA Desktop 0.26.0 工作区交付与验证

日期：2026-10-19。安装包为 Windows x64 本地未签名预览版；本机生产安装是否更新以文末状态为准。

## 使用方式

- 打开项目后，在主聊天右上角点击聊天图标打开侧边聊天，或按 Ctrl+Alt+S。选中主对话文字再点击图标可把选中文字加入新侧聊；已有侧聊用“更新上下文”刷新来源。
- 侧聊默认继承当前主任务模型，可单独选择已有连接；独立发送/停止，Enter 发送，Shift+Enter 换行。只提供读取、搜索工具，不能写文件、运行命令或调用 MCP/LSP。结果可放入主对话草稿，由用户确认发送。
- 工作区顶部的地球和终端图标新建浏览器或终端，可开多个标签。审查标签保留原修改、验证、进度、用量。拖动左右分隔线调整宽度；展开图标切换全宽，窄窗口使用主对话/工作区切换，Escape 返回主对话。
- 浏览器支持 HTTP(S)、localhost 与项目内 HTML 预览，HTML 的相对模块可加载；提供后退、前进、刷新和页面文字引用。自动弹窗、下载和敏感设备权限在本版拒绝。没有接入 Agent 自动点击或图像视觉验收。
- 终端为本机 PowerShell，支持实际键盘输入、中文、ANSI、resize、Ctrl+C 与输出引用。隐藏面板继续运行，关闭终端结束所属进程；切换项目/会话前提示停止运行终端。主任务停止不杀用户终端。
- 会话刷新恢复工作区与侧聊，不自动重发请求、重新执行终端命令。应用退出停止所属运行；重启可恢复侧聊记录，不能重新附着已退出终端。网页缓存和测试临时文件使用 G 盘。

## 实现与边界

沿用 Python Agent、Store、UsageLedger 与项目独占锁；新增 SideChats 管理器只关闭分支资源，最后由主运行时关闭 Store。共享请求预算和原计费根避免重复计费；金额仍基于服务商报告和已知定价，未知费用不显示为零。

侧聊上下文是有采集时间的有限摘要，文件可能继续被主任务修改。默认最近 50 条侧聊消息，旧记录可分页；流式内容按流 ID 与游标增量传输，不限制模型总输出。

浏览器使用独立 partition 和无 preload 的 WebContentsView。项目预览解析真实路径，拒绝越界、隐藏目录和非预览文件；网页无法调用应用 IPC。原生浏览器视图在应用弹窗/授权出现时隐藏。

node-pty 1.1.0 使用随包携带的 Windows x64 原生组件，已在实际 Electron 运行验证；原生文件从 asar 解包，禁止安装时重新编译。Windows x64 发布包排除 macOS 与 Windows ARM64 组件；安装校验同时覆盖应用 EXE、asar、解包后的原生依赖及 Python 后端。终端渲染需要动态样式，因此仅应用页面的 `style-src` 允许内联样式；`script-src` 仍仅允许随包脚本，Markdown 禁用原始 HTML，网页与应用隔离。

终端输出不经过 React 全局消息状态；PTY 批量输出、短时暂停与有界尾部缓冲防止持续增长，截断明确提示。shell 提示符或普通终端文字不作为结构化测试通过证据。手动终端按本机账户权限运行，不宣称 Docker 隔离。

## 验证命令与证据

所有测试使用独立的 G 盘临时项目和配置、本地模拟模型，无付费 API 调用，不控制用户窗口。

```powershell
$env:TEMP = 'G:\DevCache\Temp\easy-coding-agents'
$env:TMP = $env:TEMP
$env:ECA_TEST_TMP = $env:TEMP
python -B -m pytest -q -p no:cacheprovider
npm test
cd desktop
npm test
npm run build
node tests/workspace-e2e.cjs
node tests/e2e.cjs
# 同一测试可指定打包程序或隔离安装目录中的程序
$env:ECA_TEST_EXE = 'G:\Projects\easy-coding-agents\output\release\desktop\win-unpacked\ECA Desktop.exe'
node tests/workspace-e2e.cjs
node tests/e2e.cjs
```

工作区测试覆盖主/侧并行、只读工具、放回草稿、不重放刷新、真正 PTY 输入与中断、中文空格路径、模块预览、页面隔离、受保护路径、错误 owner、弹窗遮挡、窄窗口和资源关闭。终端关闭测试另外启动真实后台 PowerShell 子进程，再检查该 PID 已退出。联合负载同时保留主模型请求、侧聊流、终端输出与浏览器页面。

机器可读报告：`output/playwright/workspace-development-report-0.26.0.json`、`workspace-packaged-report-0.26.0.json`、`desktop-e2e-report-0.26.0.json`、`desktop-packaged-report-0.26.0.json`；截图：`workspace-sidechat-0.26.0.png`、`workspace-terminal-0.26.0.png`。Python 完整输出：`output/python-tests-0.26.0.txt`。

性能测试的输入值是 DOM input 事件处理后微任务的耗时，不代表物理键盘到屏幕的完整延迟；隐藏窗口截图与长任务监测也不能替代所有设备的实测。打包程序 PATH 移除 Node/Python 的测试不能替代独立干净 Windows 机器。

## 验收状态

| 检查 | 实际结果 |
| --- | --- |
| Python 全量回归 | 358 passed、6 skipped，329.13 秒 |
| 最终侧聊与 RPC 定向回归 | 22 passed；包含随后补充的流 ID、增量游标与脱敏测试，不与上一行相加为全量总数 |
| npm CLI / 桌面单元测试 | 7 / 14 passed |
| TypeScript 与生产构建 | 通过 |
| 开发版完整流程 | 通过，13 次本地模拟模型请求，渲染错误 0 |
| 打包版完整流程 | 通过，13 次本地模拟模型请求，渲染错误 0；子进程 PATH 不包含 Node/Python/Git |
| 打包版工作区 | 通过，4 次本地模拟模型请求，渲染错误 0；侧聊、浏览器、PTY、刷新、窄窗口及后台子进程退出均通过 |
| 最终安装版完整流程与工作区 | 两套测试均通过，分别 13 / 4 次本地模拟模型请求，渲染错误 0；执行文件为 `G:\Apps\ECA Desktop\ECA Desktop.exe` |

以上测试没有付费 API 调用。完整流程还覆盖模型发现、权限允许与拒绝、外部文件变化时拒绝撤销、修复后重新验证、等待模型时取消、后端中断与恢复不重放任务。

### 性能记录

长会话夹具为 240 条记录，数据在 `output/performance/workspace-0260.json`；旧数据为同机 `execution-0251.json`。这是各一次隐藏窗口抽样，不是多次冷启动分布或物理显示延迟测量。

| 指标 | 0.25.1 | 0.26.0 |
| --- | --- | --- |
| 启动至首屏可操作 | 460 ms | 507 ms |
| 空闲输入事件 P95 | 0.7 ms | 0.9 ms |
| 模型流式期间输入事件 P95 | 0.9 ms | 1.1 ms |
| 停止按钮即时状态反馈 | 1.1 ms | 1.1 ms |
| 直接观测任务停止状态完成 | 124.9 ms | 162.2 ms |
| 超过 50 ms 的界面长任务 | 0 | 0 |

安装版工作区联合负载样本含 48 次侧聊输入，P95 记录为 0 ms（低于当前计时分辨率，不代表绝对零延迟），侧聊取消完成 8 ms，长任务 0。打包完整流程测试另用 UI 轮询记录取消耗时 2050 ms，该口径没有达到方案中小于 2 秒的目标；不能将直接观测的较低数值当成所有取消场景已满足目标，仍需前台与多机复测。

打包完整流程结束阶段采样的 Electron 工作集约 454.1 MiB、后端约 87.6 MiB；旧包对应约 467.4 / 87.7 MiB。这不是空闲或峰值内存，也没有证明所有网页和终端负载下的内存上限。

### 安装包

`output/release/desktop/ECA-Desktop-0.26.0-x64-Setup.exe`：143,266,429 字节（约 136.6 MiB），展开后的程序文件约 442.9 MiB。

SHA-256：`042078f4b9bd7ae29eac1346832aff50aaacc69eb7e5373bab8000f648659d7b`，同目录提供 `.sha256` 与 `release-0.26.0.json`。根目录 CLI 包也已生成并本地检查，未发布 npm。

已安装到 `G:\Apps\ECA Desktop`。371 个程序文件与构建结果 SHA-256 比对通过，后端握手返回 0.26.0 和 sidechat 能力；模型配置文件安装前后哈希相同。记录在 `output/release/desktop/install-0.26.0.json` 与 `install-verification-0.26.0.txt`。

安装版工作区与完整流程端到端测试全部通过，报告为 `output/playwright/workspace-installed-report-0.26.0.json`、`desktop-installed-report-0.26.0.json`。本机安装验收完成；独立干净 Windows、系统签名与所有第三方网站兼容性未验收。
