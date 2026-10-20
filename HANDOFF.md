# ECA Desktop：交给无上下文 Coding Agent 的接力文档

维护日期：2026-10-20。本文可以整份复制给新的 Agent，或让它先读取本文件。以下是项目事实、用户偏好和操作约定；开始执行前仍需核对本机文件与进程状态。

## 1. 你接手的是什么

产品叫 **ECA — Easy Coding Agent**，桌面产品叫 **ECA Desktop**。这是已经可以运行的 Windows coding agent，不是等待从零搭建的 Demo。

- Python 是 Agent 核心，CLI 与桌面共用运行时。
- 桌面用 Electron + React + TypeScript，默认中文、跟随系统主题。
- 支持模型连接管理、工具授权、真实文件修改、验证、恢复、Skills、MCP、LSP、子 Agent。
- 支持多个项目、多个会话并发；左侧按项目分组显示会话。
- 右侧是按需打开的浏览器、原生终端、侧边聊天、子 Agent 详情和审查。
- 主对话与侧聊可发送图片、代码和文本附件。
- 没有自动更新、云账号、内置代码编辑器、关窗后继续运行。不要把未来规划当成已实现功能。

**接手后先读现有代码，再进行用户本次要求的改动。不要重做技术栈、覆盖现有工作、重置仓库或给界面套一套新模板。**

## 2. 路径、仓库与当前状态

| 项目 | 本机位置 / 状态 |
|---|---|
| 真正的仓库根目录 | `G:\Projects\easy-coding-agents`，注意末尾是复数 **agents** |
| Git origin | `https://github.com/yushui2022/easy-coding-agents.git` |
| 当前分支 | `main` |
| 2026-10-20 复核 HEAD | `cf79151`，提交标题 `feat(desktop): concurrent projects, subagents, activity and attachments (0.29-0.34)` |
| 本地源码 / 安装包版本 | 源码与安装版均为 `0.34.1`（安装于 2026-10-20 16:36） |
| 本机安装目录 | `G:\Apps\ECA Desktop` |
| 程序入口 | `G:\Apps\ECA Desktop\ECA Desktop.exe` |
| 模型连接及加密凭据 | `G:\Data\ECA\Desktop\preferences.json` |
| 项目会话 | 各用户项目自己的 `.eca`，不是源码仓库中的统一会话库 |
| 发布产物 | `G:\Projects\easy-coding-agents\output\release\desktop` |
| 当前发布报告 | `output/release/desktop/release-0.34.0.json`（对应 0.34.0 安装，不含 0.34.1 源码） |
| 桌面构建 Python | `G:\Projects\easy-coding-agents\desktop\.venv\Scripts\python.exe` |
| 快速搜索 | `C:\Users\xiaoy\.local\bin\rg.exe` |

有些旧会话的 cwd 写成 `G:\Projects\easy-coding-agent`（单数），不要据此新建另一个仓库或在错误目录修改。

### 特别重要：本地未提交内容

2026-10-20 复核：0.29–0.34 的累积源码和本接力文档已进入本地提交 `cf79151`。之后的未提交改动：移除输入框“验证命令／自动修复”入口及相应测试调整、版本升到 0.34.1，以及 `web_fetch` 的代理 Fake-IP DNS 修复。不要恢复该入口；核心验证工作流与历史结果仍保留。**源码为 0.34.1、安装版仍为 0.34.0**，不能凭版本号判断代码是否一致。远端已推送 `cf79151`，之后无新提交。

先运行：

```powershell
Set-Location 'G:\Projects\easy-coding-agents'
git status --short
git branch --show-current
git log -1 --format='%h %s'
git remote -v
```

不要 `git reset --hard`、`git clean -fd`、批量 checkout 文件，或把未跟踪的新组件当垃圾删掉。不要直接 pull 覆盖工作区。用户要求提交时，先检查差异、排除凭据和产物，再提交；推送成功要有实际结果，不能只说“已提交到仓库”。

若在另一台机器接手，需要先获得包含当前未提交源码与新资源的完整源码交接，或确认这些内容已经提交推送。只克隆旧提交会缺少功能。不要传 `.env`、用户 `.eca`、加密配置或测试中的私人数据。

## 3. 当前版本与待办

### 0.34.0 新增

1. 主对话、侧聊共用附件入口：点击加号、拖入文件、粘贴截图、发送前预览和移除。
2. 附件草稿按项目/会话/主侧聊隔离，IndexedDB 保存，刷新后恢复。
3. 图片以原生图片内容块传入 OpenAI Chat、Responses、Anthropic 适配器；不是把文件名交给模型假装看过。
4. 右侧默认收起；审查按需打开，只有“文件修改”“检查结果”两个标签，任务活动与用量改为折叠详情。

### 真实边界

- 支持 PNG、JPEG、WebP 和界面接受的 UTF-8 文本/代码文件；暂不解析 PDF、Office、压缩包。
- 每次最多 6 个附件；单张图片 4 MB、文本 256 KB、合计 12 MB。这是上传限制，不是连续输出次数限制。
- 模型和代理端点必须支持图片输入；不能只凭名字宣称支持视觉。服务拒绝时显示错误，切换支持视觉的模型，或新建不含图片的会话。
- 图片快照在项目 `.eca/attachments/`，文本快照在会话中。备份会话要包含附件目录，不能按缓存删除。
- 已发送记录当前展示附件名和大小；发送前有图片缩略图。不要声称已实现历史附件全文编辑或图片浏览器。
- 同项目多会话共享实际文件，已有文件一致性检查不是完整 OS 沙箱；shell/MCP 的外部效果不能全部撤销。
- 用本地模拟模型通过测试，不代表任意真实模型、第三方代理或干净 Windows 均已验证。

### 安装进展

本次用户已明确回复“已退出，可以更新”，允许将 0.34.0 更新到原安装位置。最终安装及复测结果见本文末尾“本次交接结果”和 `release-0.34.0.json`。后续新版本更新仍先确认用户应用没有运行中的任务，不强杀用户工作。

0.34.0 安装包：

```text
G:\Projects\easy-coding-agents\output\release\desktop\ECA-Desktop-0.34.0-x64-Setup.exe
163020117 bytes
SHA256 a8b1fd7d91c15058d0c6459a36f55178ce2fd0b01d61c9c98c3a9f9c742f6a20
```

这是本地未签名预览包，没有发布 npm registry；不要编造公网下载地址。

## 4. 用户明确的工作方式与磁盘规则

- 中文沟通，直接推进已授权的修改，避免反复询问同一许可。
- 用户明确说过：**不要随便使用 computer use 接管桌面**。优先代码、CLI、独立隐藏测试。不要自动操作用户浏览器、鼠标键盘或真实业务项目。
- 测试尽量本地模拟模型，不默认使用用户付费 API。密钥不出现在命令行、日志、源码、截图或交接文档。
- 用户重视长任务能持续完成，不希望为了防死循环随意限制连续输出。显示层折叠/分页和执行预算要区分。
- 不要在 C 盘、桌面、文档、AppData/Temp、D/E 盘堆积新依赖、模型、构建和素材。可再生的大文件默认放 G。
- 生成超过 500 MB、装大量依赖或打包前检查 G 盘空间，说明输出、缓存、临时目录。
- 不迁移 Windows、Program Files、整个 AppData、工具链或数据库目录。不把配置、密钥、源代码、附件、原始数据当缓存删。
- Windows 递归删除/移动前核对绝对路径和目标范围；不要跨 PowerShell/cmd 拼接删除命令。
- 后台辅助程序使用 `Start-Process -WindowStyle Hidden`。只有用户明确要求看界面时才启动可见窗口。

新 PowerShell 会话先设置：

```powershell
$ErrorActionPreference = 'Stop'
$EcaRepo = 'G:\Projects\easy-coding-agents'
$EcaTemp = 'G:\DevCache\Temp\easy-coding-agents'
Get-PSDrive G | Select-Object Name,@{Name='FreeGiB';Expression={[math]::Round($_.Free / 1GB, 2)}}
New-Item -ItemType Directory -Force -Path $EcaTemp | Out-Null
Set-Location $EcaRepo
$env:TEMP = $EcaTemp
$env:TMP = $EcaTemp
$env:ECA_TEST_TMP = $EcaTemp
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:npm_config_cache = 'G:\DevCache\npm'
$env:PNPM_STORE_DIR = 'G:\DevCache\pnpm-store'
$env:PIP_CACHE_DIR = 'G:\DevCache\pip'
$env:UV_CACHE_DIR = 'G:\DevCache\uv'
$env:ELECTRON_CACHE = 'G:\DevCache\electron'
$env:ELECTRON_BUILDER_CACHE = 'G:\DevCache\electron-builder'
$env:PLAYWRIGHT_BROWSERS_PATH = 'G:\DevCache\playwright'
$env:CARGO_TARGET_DIR = 'G:\DevCache\CargoTarget'
$env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
```

本项目用 npm，不需要为此安装 pnpm 或 Rust。若未来使用 pnpm，应另核实其实际 store 配置，不能仅凭环境变量假定生效。

应用运行缓存默认 `G:\DevCache\eca-desktop`；可用 `ECA_DESKTOP_CACHE_HOME` 覆盖。应用数据可用 `ECA_DESKTOP_DATA_HOME` 覆盖。测试必须用独立目录，不能指向用户的 `G:\Data\ECA\Desktop`。

## 5. 下载、环境准备与启动

### 同一台机器

优先使用现有仓库和 `desktop/.venv`，不要重复下载或另建嵌套目录。文档编写时可用：Node `24.13.0`、npm `11.6.2`、Python `3.11.1`，Windows x64。

### 新机器 / 全新目录

先解决第 2 节的未提交源码交接；确认远端包含所需版本后，才可：

```powershell
git clone https://github.com/yushui2022/easy-coding-agents.git 'G:\Projects\easy-coding-agents'
Set-Location 'G:\Projects\easy-coding-agents'
```

若目标目录存在，检查并复用，不覆盖。无 G 盘的另一台机器，先选定非系统盘位置并检查脚本中固定的 G 盘路径；不要原样照抄本机路径后回退到 C 盘下载。

开发依赖按锁文件安装：

```powershell
# 已执行上一节的环境变量设置，当前目录为仓库根。
if (!(Test-Path -LiteralPath 'desktop\.venv\Scripts\python.exe')) {
    py -3.11 -m venv desktop\.venv
    if ($LASTEXITCODE) { throw '创建 Python 环境失败' }
}
& .\desktop\.venv\Scripts\python.exe -m pip install -r desktop\requirements-build.lock
if ($LASTEXITCODE) { throw '安装锁定 Python 依赖失败' }
npm.cmd ci --prefix desktop
if ($LASTEXITCODE) { throw '安装桌面依赖失败' }
$env:ECA_PYTHON = Join-Path $EcaRepo 'desktop\.venv\Scripts\python.exe'
```

`desktop/package-lock.json`、`desktop/requirements-build.lock` 是桌面发布依赖依据。若锁定版本拉取失败，记录具体错误并排查源；不要静默升级全部依赖。根目录 npm 包负责 CLI，不能把根目录 `npm test` 当成桌面测试。

编译界面：

```powershell
npm.cmd run build --prefix desktop
if ($LASTEXITCODE) { throw '桌面构建失败' }
```

用户要求查看开发版时：

```powershell
$env:ECA_PYTHON = Join-Path $EcaRepo 'desktop\.venv\Scripts\python.exe'
Push-Location (Join-Path $EcaRepo 'desktop')
try { npm.cmd run dev } finally { Pop-Location }
```

开发版直接使用 Python 源码；**安装版只使用随包后端**，修改 `.py` 后仅编译前端不能更新安装版后端。

## 6. 构建 Windows 安装包

技术链路：**PyInstaller onedir（保留 stdin/stdout）→ Electron 隐藏启动后端 → electron-builder NSIS**。不调用交互式 CLI，不解析终端输出，不开本地 HTTP RPC 端口。

版本号一起更新：

- `package.json`
- `desktop/package.json`
- `desktop/package-lock.json` 的顶层与根包版本
- `pyproject.toml`
- `eca/__init__.py`

依赖已准备好的常用构建：

```powershell
# 仓库根目录；先检查 G 盘，确保缓存变量已设置。
Get-PSDrive G
& .\desktop\.venv\Scripts\python.exe desktop\scripts\build-runtime.py
if ($LASTEXITCODE) { throw 'Python 后端打包失败' }
npm.cmd run package --prefix desktop
if ($LASTEXITCODE) { throw 'Electron/NSIS 打包失败' }
```

完整重建也可用 `desktop/scripts/package.ps1`，但它会重新执行 npm ci 和 pip 安装；依赖没有变化时不必每次重装。PowerShell 执行策略导致 npm.ps1 不可执行时，用 `npm.cmd`，不要全局降低系统执行策略。

| 内容 | 输出位置 |
|---|---|
| PyInstaller 临时文件 | `G:\DevCache\Temp\easy-coding-agents\pyinstaller-work` |
| Python 随附运行时 | `desktop/runtime/eca-backend` |
| React / Electron 编译结果 | `desktop/dist` |
| 未安装的完整应用 | `output/release/desktop/win-unpacked` |
| NSIS 安装包 | `output/release/desktop/ECA-Desktop-<版本>-x64-Setup.exe` |
| 发布日志、哈希、报告 | `output/release/desktop` |
| UI 截图、测试报告 | `output/playwright` |

仅修改前端、且已确认 runtime 与本轮 Python 源码完全一致时，可省去重新构建 Python。不要凭目录存在就判断 runtime 是最新。

构建完成后生成 SHA256 与机器可读发布报告。**安装器退出成功不等于更新成功**；还要检查安装文件、后端握手和运行流程。

## 7. 更新本机安装版：保持配置和会话

1. 检查指定路径的应用进程，不能按所有 electron/node/python 进程一概杀掉。
2. 若应用正在运行，先完成构建和可独立执行的测试，再请用户保存退出。不要停止用户进行中的项目任务。
3. 用户已确认退出后，再核对进程。必要时只向该应用发送正常关闭请求；若还有退出确认，等待用户完成，不擅自强杀。
4. 比较安装包 SHA256；安装前保存 preferences 文件的哈希，不打印文件内容。
5. 在原位置执行安装，再运行安装后的测试。

```powershell
$EcaInstalled = 'G:\Apps\ECA Desktop\ECA Desktop.exe'
Get-Process -Name 'ECA Desktop' -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $EcaInstalled } |
    Select-Object Id, MainWindowTitle

# 确认没有占用后执行。该脚本默认按 desktop/package.json 选择安装包。
& .\desktop\scripts\install-local.ps1 -InstallDirectory 'G:\Apps\ECA Desktop'
if (!$?) { throw '安装或安装校验失败' }
(Get-Item -LiteralPath $EcaInstalled).VersionInfo |
    Select-Object ProductVersion, FileVersion
```

脚本设置 G 盘安装临时目录，静默 NSIS 更新，并调用 `desktop/scripts/verify-install.cjs` 校验 payload 哈希和后端版本握手。该验证脚本需要开发机 Node；安装好的用户应用不依赖外部 Python/Node。

凭据保护：

- `preferences.json` 用 Electron safeStorage 加密密钥，不要读取输出、重写或替换成测试配置。
- 同一用户的原位置更新保留数据；不要卸载后清理用户数据来“重装”。
- 若哈希发生变化，只能说“配置文件发生变化”，排查原因；不能声称逐字节保留。
- 加密配置不保证可以跨电脑/Windows 账户直接解密，换机应通过界面重新配置密钥。
- 不覆盖用户项目 `.eca`；不要清理其 SQLite、变更记录或附件。
- 不自动重放旧任务、工具、审批。恢复必须沿用核心恢复检查。

用户明确要求打开安装版时才执行：

```powershell
Start-Process -FilePath 'G:\Apps\ECA Desktop\ECA Desktop.exe'
```

这是用户可见的交互窗口，不能把后台辅助服务也照此可见启动。

## 8. 测试方法和当前证据

默认使用隐藏、独立的 Electron 测试窗口 + 本地模拟模型 + G 盘临时项目。不要操纵用户现有窗口，不花用户 API 费用，不用真实业务项目当测试夹具。

### 基础检查（仓库根）

```powershell
$env:PYTHONPATH = 'tests'
& .\desktop\.venv\Scripts\python.exe -B -m unittest test_attachments test_runtime test_side_chat test_anthropic test_config_provider test_desktop_projects
if ($LASTEXITCODE) { throw 'Python 检查失败' }
npm.cmd run build --prefix desktop
if ($LASTEXITCODE) { throw '类型检查/构建失败' }
npm.cmd test --prefix desktop
if ($LASTEXITCODE) { throw '桌面单元测试失败' }
# 涉及 CLI 启动器再运行：
npm.cmd test
```

桌面 `.venv` 是打包环境，不包含所有 legacy 测试依赖。不能因旧模块缺依赖就说全部 Python 回归通过，也不能为无关旧模块无限扩张本次测试范围。

### UI 流程

统一从 **desktop 目录**运行，避免部分脚本依赖 cwd 的问题：

```powershell
$env:ECA_PYTHON = Join-Path $EcaRepo 'desktop\.venv\Scripts\python.exe'
Remove-Item Env:ECA_TEST_EXE -ErrorAction SilentlyContinue
$env:ECA_TEST_MODE = 'development'
Push-Location (Join-Path $EcaRepo 'desktop')
try {
    node tests/attachments-e2e.cjs
    if ($LASTEXITCODE) { throw '附件流程失败' }
    node tests/e2e.cjs
    if ($LASTEXITCODE) { throw '完整流程失败' }
    node tests/workspace-e2e.cjs
    if ($LASTEXITCODE) { throw '工作区流程失败' }
} finally { Pop-Location }
```

按改动选择 `concurrent-projects.cjs`、`concurrent-sessions.cjs`、`subagents-e2e.cjs`、`activity-stream.cjs`、主题与性能脚本。旧 UI 测试若假定审查默认展开，需要更新入口步骤，不能删除实质断言来伪造通过。

打包 / 安装版使用同一脚本：

```powershell
$env:ECA_TEST_EXE = Join-Path $EcaRepo 'output\release\desktop\win-unpacked\ECA Desktop.exe'
$env:ECA_TEST_MODE = 'packaged'
# 安装后改为：
# $env:ECA_TEST_EXE = 'G:\Apps\ECA Desktop\ECA Desktop.exe'
# $env:ECA_TEST_MODE = 'installed'
Push-Location (Join-Path $EcaRepo 'desktop')
try {
    node tests/attachments-e2e.cjs
    if ($LASTEXITCODE) { throw '随包/安装版附件流程失败' }
} finally { Pop-Location }
```

部分旧脚本报告 mode 只区分 development/packaged，即使传入已安装 exe 也写 packaged；应同时记录真实启动路径，不仅凭 mode 判断安装验收。

0.34.0 已有证据：

- Python 定向回归 51 项，1 跳过，0 失败；桌面 Node 15 项通过。
- TypeScript、生产构建通过。
- 主桌面完整流程 13 次本地请求通过：授权、真实修改、撤销冲突、验证修复、停止、恢复、后端异常。
- 工作区 4 次本地请求通过：侧聊、浏览器、原生终端、资源清理、窄窗口。
- 最终打包版附件 3 次本地请求通过：真实请求 payload、主侧聊图片、文本、草稿恢复、会话隔离、粘贴/拖入/移除、不支持的格式、视觉拒绝、深浅主题、窄窗口按钮可达。
- 以上均为 0 次付费 API；没有干净 Windows 实机验收。隐藏窗口测试不能当作物理屏幕延迟或全面性能保证。

报告位置：

```text
output/release/desktop/release-0.34.0.json
output/release/desktop/attachments-python.log
output/release/desktop/full-e2e-0.34.0.log
output/release/desktop/workspace-0.34.0.log
output/release/desktop/attachments-packaged-0.34.0.log
output/playwright/attachments/packaged.json
output/playwright/attachments/packaged-light.png
output/playwright/attachments/packaged-dark.png
```

## 9. 项目结构与不能破坏的边界

| 模块 | 负责什么 |
|---|---|
| `eca/agent.py` | Agent 循环、工具调用、上下文与任务状态 |
| `eca/runtime.py` / `workflow.py` | CLI/桌面共用任务启动、取消、验证及有限修复 |
| `eca/desktop_rpc.py` | JSON-RPC 2.0，逐行 stdin/stdout，授权/提问 ID、事件、恢复 |
| `eca/desktop_sessions.py` | 单项目多会话运行时 |
| `eca/desktop_projects.py` | 多项目协调、独立锁、事件路由与关闭 |
| `eca/side_chat.py` | 独立只读侧聊，当前工具为 read/glob/grep |
| `eca/attachments.py` | 附件验证、图片快照、协议内容块 |
| `eca/provider.py` / `responses.py` / `anthropic.py` | 三种模型协议适配 |
| `eca/store.py` | 项目 `.eca` SQLite、记录、独占锁 |
| `eca/child_activity.py` / `activity.py` | 子 Agent 与模型实时活动 |
| `desktop/src/main/index.ts` | Electron 生命周期、受限 IPC、配置、项目会话工作区 |
| `desktop/src/main/connections.ts` | 多连接、加密密钥、默认与项目选择 |
| `desktop/src/main/browser-manager.ts` / `terminal-manager.ts` | 浏览器、原生 PTY 与所属资源 |
| `desktop/src/preload/index.ts` | 受限桥接，不暴露任意 Node/文件系统 |
| `desktop/src/renderer/index.tsx` | 主界面与输入、状态订阅、审查 |
| `Sidebar.tsx` / `sidebar.css` | 项目分组、会话列表与搜索 |
| `Attachments.tsx` / `attachments.css` | 主/侧聊共用附件输入与草稿 |
| `Transcript.tsx` | Markdown 与工具记录、历史附件名称 |
| `ModelMenu.tsx` / `ModelSettings.tsx` | 模型搜索、最近使用、推理强度与配置 |
| `RunActivity.tsx` / `run-activity.css` | 动作、工具、对象、tokens/s 和耗时 |
| `workspace/` | 浏览器、终端、侧聊和按需审查 |
| `subagents/` | 主对话子 Agent 入口与右侧详情 |

边界约定：

- 一个 Electron 主进程管理一个 Python 后端；多个项目由后端协调，不为每个会话偷偷建立另一套数据库。
- 项目标识 + 会话标识组合构成工作区 owner；不能只用 session_id 路由。后台项目的事件不能覆盖前台 UI。
- 每个项目仍有进程独占锁，CLI 占用时说明原因，不抢锁。
- 切换项目/会话保留任务、授权、草稿、模型、浏览器、终端；取消仅影响目标任务及其子任务。
- 关闭应用时处理所有项目与所属进程，不能误杀系统其他终端。
- 批准必须回到 Python 权限逻辑，不通过界面“假批准”绕过。完全访问要由用户明确选择。
- stdout 只输出协议 JSON，不能插入 rich 日志或 print 调试文字；诊断使用脱敏 stderr。
- 后端崩溃、通信 EOF、窗口重载不能自动重放任务/工具/授权。
- 模型密钥只由主进程读取，经私有管道交给后端；renderer 配置读回只显示状态。
- 文件撤销遵守一致性检查，标记已审查不等于 Git 提交。
- tokens/s 的估算/上一轮语义必须保留，不伪造精确速度；费用无依据显示“未知”。

## 10. 视觉风格：这是已确认的产品方向

用户喜欢的是 **陶土材质的真实 UI**，不是在普通灰白 Demo 上贴几张陶土图片。

### 保留这些设计判断

- 暖白/燕麦陶色浅主题，深色炭陶主题，低饱和橙陶色强调。
- 静态可见的粗颗粒，柔和上缘高光与下缘阴影，浅凹表单、圆润卡片、一体式浮动输入区。
- 用户多次要求颗粒更大，不要擅自重新磨成几乎看不见的细噪点。
- 长聊天正文、代码、差异使用安静的平底，纹理不能干扰阅读；不做大面积动画噪点、模糊、炫光。
- 橙色用于品牌/重要操作，不把每个文件夹都做成橙色立体图案。导航不要重复堆叠大装饰图。
- 借鉴 Pi Desktop / Codex 的信息层级、留白和工作流：内容优先、工具记录紧凑、面板按需打开。
- 子 Agent 用不同颜色/形状的陶土小标志；点击主对话入口在右侧看独立内容。形状不是六个固定角色，状态仍靠文字表达。
- 输入区支持 Enter 发送、Shift+Enter 换行、中文 IME 选字不误发；模型、权限、附件控件保持紧凑。
- 不添加大标题营销区、装饰性 KPI 卡片、无用途徽章、巨量说明文字或重复的四标签常驻面板。
- 错误、空状态、等待、完成必须基于真实状态。不要用图片代替可交互控件或把动态文案烘焙到图片里。

### 优先复用现有设计系统

```text
desktop/src/renderer/tokens.css
desktop/src/renderer/clay-surfaces.css
desktop/src/renderer/style.css
desktop/src/renderer/sidebar.css
desktop/src/renderer/workspace/side-chat.css
desktop/src/renderer/model-menu.css
desktop/src/renderer/assets/clay-surfaces/
desktop/src/renderer/assets/clay-icons/
desktop/src/renderer/assets/agent-marks/
desktop/src/renderer/assets/activity/
```

图标当前使用 `@phosphor-icons/react`。不要为了小改动引入另一套庞大 UI 库。素材已有 README、manifest 或提示词记录，先复用。可按用户要求使用图像生成能力补充原创透明陶土标志/表面材质，但必须集成并验证实际显示。

CSS 存在多层覆盖，改动前检查 tokens、基础样式、workbench、workspace、clay 的加载顺序。尽量在组件范围修改，避免用越来越多全局 `!important` 掩盖冲突。深色选中标签、低对比次要文字、窄窗口发送按钮必须实际检查。

本机可选参考文档（新机器不一定存在）：

```text
C:\Users\xiaoy\Documents\Obsidian Vault\前端\从 Demo 到企业级质感：前端升级执行指南.md
C:\Users\xiaoy\Documents\Obsidian Vault\桌面端产品的技术架构\07 前端组件体系：自建组件库、设计令牌与主题复用.md
C:\Users\xiaoy\Documents\Obsidian Vault\产品设计方法论
```

这些是设计参考，不是声称本仓库使用它们提到的 Tailwind、Flask 或其他技术。旧 `MEMORY.md` 混有历史项目记录；现代桌面架构以实际 `eca/`、`desktop/` 源码、最新版本文档和用户指示为准。

## 11. 新 Agent 的第一轮操作

1. 确认实际目录、Git 工作区、源码版本、已安装 exe 版本；不要只看旧 README 标题。
2. 读取本文件与当前需求相关模块；先复现或核对问题，不重写已经完成的功能。
3. 记录目标、涉及文件/模块、执行顺序、验证方式和真实风险。通常不用提前输出完整实现代码。
4. 设置 G 盘缓存与 UTF-8 环境；保持用户配置和用户项目独立。
5. 在现有架构和陶土风格中完成改动，运行与改动相称的测试。
6. 更新功能文档、README/开发指南入口、版本与发布报告，区分源码、打包、安装、安装后测试四种状态。
7. 如需更新安装版，先完成打包与可独立执行的验证，再处理应用退出。不要一开始就让用户反复关闭。
8. 最终说明做了什么、测过什么、安装是否完成、还有哪些真实限制。不要声称全部性能问题、所有模型兼容性或干净机验收已经解决。

建议按需求继续读：

- `docs/desktop/ATTACHMENTS-0.34.0.md`
- `docs/desktop/PROJECTS-0.33.0.md`
- `docs/desktop/CONCURRENCY-0.32.0.md`
- `docs/desktop/ACTIVITY-0.31.0.md`
- `docs/desktop/MODEL-MENU-0.30.0.md`
- `docs/desktop/SUBAGENTS-0.29.0.md`
- `docs/desktop/CLAY-THEME.md`
- `docs/desktop/PROTOCOL.md`

## 本次交接结果

2026-10-20 已将 **0.34.0** 更新到 `G:\Apps\ECA Desktop`，安装程序退出码为 0，exe 产品版本为 `0.34.0.0`。

- 安装目录 371 个 payload 文件哈希检查通过，Python 后端握手版本为 `0.34.0`。
- 用户 `preferences.json` 安装前后 SHA256 相同，模型配置与加密凭据文件未改变；没有操作用户项目会话。
- 安装后的附件端到端测试通过：3 次本地模拟请求、0 次付费 API 调用、无 renderer 错误。覆盖主对话与侧聊图片输入、草稿恢复、会话隔离、纯图片发送、粘贴、拖放、移除、格式拒绝、服务视觉错误、按需审查、深浅主题及窄输入区。
- 没有自动启动用户的交互窗口，也没有重放任何用户任务。
- 此项为安装当时的历史记录；随后源码与交接文档已进入 `cf79151`，当前未提交状态见第 2 节。
- 干净 Windows、真实服务商视觉能力和全部历史 Python 测试仍未因此获得验收。

证据：`output/release/desktop/install-0.34.0.log`、`output/playwright/attachments/installed.json`、`output/release/desktop/attachments-installed-0.34.0.log`、`output/release/desktop/release-0.34.0.json`。

### 2026-10-20 后续：0.34.1 已安装

在用户完成保存并退出后，将 **0.34.1** 装到原位置 `G:\Apps\ECA Desktop`，安装脚本退出码 0：

- `ECA Desktop.exe` 产品版本 `0.34.1.0` / 文件版本 `0.34.1`；后端握手 `0.34.1`。
- 安装目录 328 个 payload 文件与 `win-unpacked` 逐文件哈希一致。本次 payload 比 0.34.0 的 371 个少，差额未逐文件追查；该 payload 本身跑过 11 次真实请求的端到端，未发现缺依赖。
- `preferences.json` 安装前后 SHA256 相同（`e2f4a380…2bfc`），模型配置与加密凭据未改变；未操作用户项目会话。
- 打包版端到端：`mode=packaged`、11 次本地请求、26 项检查通过、0 次付费 API 调用、无 renderer 错误、取消 41 ms。
- 没有自动启动安装后的窗口，也没有重放用户任务。干净 Windows 与第三方代理环境仍未验收。

证据：`output/release/desktop/release-0.34.1.json`、`output/release/desktop/e2e-packaged-0.34.1.log`、`output/playwright/desktop-packaged-report.json`、`output/release/desktop/preferences-before-0.34.1.sha256`。
