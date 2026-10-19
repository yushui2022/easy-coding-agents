# ECA Desktop 0.28.0 预览版

Windows x64 桌面入口，复用 ECA Python 核心。CLI 的 `eca` / `ecs` 继续可用。
首版包含模型配置、项目与会话、流式对话、授权和提问、任务停止、修改审查、验证与用量。
0.26.0 增加右侧工作区：独立侧边聊天、浏览器、PowerShell 交互终端与原任务审查。没有内置代码编辑器、云账号、自动更新或关窗后继续运行。

打开项目后，点击主对话右上角聊天图标进入侧聊；工作区顶部的地球、终端图标分别打开网页和终端。侧聊与主任务独立发送、独立停止，讨论结果可以放入主对话草稿。原来的文件修改、验证、进度和用量位于“审查”标签。工作区可拖宽、展开或收起。

0.25.1 将连续工具调用收纳为执行记录，保留异常和最近步骤，展开查看完整参数与输出。项目内文件显示相对路径；读取图片失败会说明文本工具的能力边界。[执行区设计与验收](EXECUTION-0.25.1.md)。

右侧工作区的背景与设计见 [升级方案](WORKSPACE-PANELS-PLAN.md)，实际交付范围和测试见 [0.26.0 验收记录](VERIFICATION-0.26.0.md)。

0.27.0 统一桌面设计令牌、三栏比例、导航、聊天与空状态的外观。见 [视觉升级与验证](VISUAL-0.27.0.md)。

0.26.1 将输入框下方收拢为单行验证入口与快捷键提示，设置按需展开。见 [底栏调整与验证](COMPOSER-0.26.1.md)。

0.27.1 收紧新任务页面与输入区，将模型、模式及操作权限分组，快捷任务改为轻量入口。见 [新任务区域调整与验证](WELCOME-0.27.1.md)。

0.28.0 参考用户提供的 Pi Desktop 与 Codex 截图，改为居中开场、底部悬浮输入区，集成 ECA 原创视觉图形。验证设置按需展开，输入区随内容增长。见 [布局与验证记录](WELCOME-0.28.0.md)。

## 安装与使用

安装包位于 `output/release/desktop/ECA-Desktop-0.28.0-x64-Setup.exe`，可选择安装目录。
本机 C 盘空间不足时，开发者使用 `pwsh -File desktop/scripts/install-local.ps1` 安装；它将临时解压放在 G 盘，并核对安装文件和后端启动。仅选择 G 盘安装目录不会自动迁移安装器的临时解压目录。
这是未签名的本地预览包；不要将“构建成功”理解为签名或干净机器验收通过。
程序携带 Electron、Python 和 MCP 客户端依赖，首次运行不执行 npm/pip 安装。
项目需要的编译器、测试框架、Git、语言服务器和 MCP 服务端不包含在包内。

1. 打开「模型与设置」→「添加连接」，选服务商模板、输入 API 密钥，密钥输入完成后自动获取模型列表，也可展开手动填写模型 ID；保存后可测试连接并设为桌面默认。每个连接独立保存密钥。
2. 打开项目文件夹，默认使用桌面默认连接。在输入框的模型选择器里，可以指定其他连接或明确选择「沿用项目配置」。项目选择会记住，原 `.env` / `eca.toml` 不被改写。
3. 输入任务；也可以先写任务再选择项目。取消选目录或刷新界面会保留草稿；选完项目后点击发送或按 Enter 才执行。Shift+Enter 换行，中文输入法选字不会发送，Ctrl/Cmd+Enter 保持兼容。展开「验证与自动修复」，每行填写一条检查命令，并选择失败后停止或最多修复 1～3 次。填写检查时默认修复 1 次；不填检查时不自动修复。
4. 输入框旁可选「逐次确认」「自动编辑」「完全访问」。自动编辑仅放行文件修改，完全访问需明确开启且只对本次打开项目有效。逐次确认时点击「本次允许」或「拒绝」；拒绝不会自动批准后续操作。
5. 在修改面板查看差异、标记已审查或撤销。标记已审查不会提交 Git。右上角可收起／打开工作区；窄窗口切换主对话与工作区，Escape 返回主对话。

左上角可折叠导航，会话支持搜索。工具调用与返回合成一条摘要，展开后查看参数与输出；大记录可加载完整内容并继续分段展开。右侧「验证」独立展示每轮失败、修复和复验。授权固定在输入区上方；查看旧消息时不会自动跳到底部，可点击「回到最新」。这些只改变显示与加载方式，不限制模型输出或删除历史。[工作台设计说明](WORKBENCH-0.25.0.md) · [0.25.0 验证报告](VERIFICATION-0.25.0.md)。

保存连接不会中断当前任务。点击「用于当前项目」或在输入框选择模型才切换当前执行模型；切换会话继续保持该项目选择。默认连接用于没有单独指定模型的项目；更改默认后，已打开项目可点击「跟随桌面默认」立即应用。CLI 配置优先级保持原样。关闭后可从项目中的原 `.eca` 会话继续；中断时需要检查外部命令是否已产生效果。
同一项目只能由一个 ECA 进程持有，CLI 和桌面不能同时占用它。

DeepSeek 桌面连接默认使用快速模式；模型设置中可改为均衡、深入或服务默认。运行过程展示等待模型、思考字符数、工具参数生成和执行耗时。[0.23.0 说明与验证](EXECUTION-0.23.0.md)。

检查和修复次数在当前窗口按项目记住，刷新不会丢失。右侧保存每轮失败和通过记录；拒绝授权、超时或取消不会触发修复，修复后从第一条检查重跑。Python 文件工具修改公开函数或事务设置后可显示回归检查建议；提示仅来自有限语法分析，不覆盖 shell/MCP 修改，也不保证正确性。[0.24.0 实测记录](VERIFICATION-0.24.0.md)。

## 数据与权限

Windows 密钥使用 Electron safeStorage 的系统加密。不可用时仅在本次进程中保存，不落明文。
系统加密不隔离同一 Windows 用户下的所有其他应用。项目既有 `.env` 的管理方式不变。
默认有 G 盘时，应用配置在 `G:\Data\ECA\Desktop`，浏览器缓存在 `G:\DevCache\eca-desktop`；其他机器使用标准用户应用目录。
可用 `ECA_DESKTOP_DATA_HOME`、`ECA_DESKTOP_CACHE_HOME` 显式指定目录。不要把配置和密钥当作缓存清理。
卸载不删除项目 `.eca`；升级安装保留应用配置。首版没有自动迁移或删除旧会话。

授权与工具执行仍由 Python 核心处理。页面禁用 Node、原始 HTML 和远程图片，外链只在用户点击后通过系统浏览器打开。
停止按钮取消任务；关窗运行中会询问保留窗口还是停止退出。清理超时提供继续等待或强制结束所属进程的选择。

## 开发与构建

需要 Windows x64、Node 与 Python 3.11。代码在 `desktop/`；根目录 npm 包仍是 CLI 启动器。

```powershell
$env:npm_config_cache = 'G:\DevCache\npm'
$env:ELECTRON_CACHE = 'G:\DevCache\electron'
$env:ELECTRON_BUILDER_CACHE = 'G:\DevCache\electron-builder'
$env:TEMP = 'G:\DevCache\Temp\easy-coding-agents'
$env:TMP = $env:TEMP
cd desktop
npm ci
npm run dev
```

开发模式使用 `ECA_PYTHON` 指向的解释器，未设置时使用 `python`；打包版本仅使用随附后端。
完整构建运行 `desktop/scripts/package.ps1`：检查空间、安装锁定依赖、生成 PyInstaller onedir、编译界面、生成 NSIS 安装包。
`requirements-build.lock` 固定 Windows/CPython 3.11 构建依赖；`package-lock.json` 固定桌面构建依赖。
构建输出和 `.venv` 均不提交 Git，图标从现有项目 logo 转换。

## 验证

- 根目录：在安装了项目开发/测试依赖的 Python 环境运行 `python -B -m pytest -q -p no:cacheprovider` 与 `npm test`。桌面构建专用虚拟环境不包含旧模块的全部测试依赖。
- 桌面目录：`npm run build`、`npm test`、`npm run test:e2e`。
- 设置 `ECA_TEST_EXE` 为安装后的 `ECA Desktop.exe` 再运行端到端测试，可验证打包程序；测试会从子进程 PATH 移除 Python、Node 和 Git。
- 测试使用本地 HTTP 模型，覆盖真实文件修改、授权时刷新、验证命令、差异、外部修改冲突、重启恢复和网络等待取消，不调用付费模型。
- 截图与机器可读报告在 `output/playwright`；每次测试创建独立临时项目和应用配置，避免覆盖用户数据。
- 桌面性能：设置 `ECA_PYTHON` 指向开发 Python，运行 `node tests/performance.cjs current`。`ECA_TEST_EXE` 可指定打包程序，`ECA_TEST_WORKBENCH=1` 额外验证新导航与按需历史。数据在 `output/performance`；同口径比较时应使用同机器、同构建类型、同测试脚本。隐藏窗口的测量不代表物理显示延迟。

PATH 隔离测试不能替代没有开发工具的独立 Windows 环境。具体结果与未验收项见 [本地验收记录](VALIDATION.md)。

构建选择参考 [PyInstaller onedir 与标准输入输出说明](https://pyinstaller.org/en/stable/operating-mode.html)；密钥保存行为与保护边界参考 [Electron safeStorage 文档](https://www.electronjs.org/docs/latest/api/safe-storage)。

0.21.1 的输入与界面改造见 [桌面修复记录](UI-0.21.1.md)。模型管理与本轮验收见 [0.22.0 说明](MODELS-0.22.0.md)。

Enter 发送与自动获取模型列表见 [输入与模型配置](INPUT-0.22.1.md)。

端到端测试自动设置 `ECA_DESKTOP_TEST_HIDDEN=1`，不显示测试窗口；仍使用真实 Electron、Python 与本地模型服务。
