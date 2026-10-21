# 贡献指南

欢迎 Issue 和 PR。这个项目同时在**改一个会动你文件的 agent**，所以对「证据」和「不变量」的要求比一般项目高：任何行为改动都要有能复现的验证。

## 1. 先开 Issue

- 报问题用[问题反馈](https://github.com/yushui2022/easy-coding-agents/issues/new?template=bug-report.yml)模板：**版本号 + 模型/端点 + 复现步骤**是必填，缺了我没法判断是你的环境还是代码
- 提功能用[功能建议](https://github.com/yushui2022/easy-coding-agents/issues/new?template=feature-request.yml)：先说卡在哪，再谈方案

版本号在桌面版侧栏底部；CLI 用 `eca --version`。

## 2. 本地开发

### CLI / Python 核心

```sh
python -m pip install -r requirements-dev.txt
python -m pip install -e ".[mcp]"
python -B -m pytest -q
```

### 桌面端

```sh
cd desktop
npm ci
npx tsc --noEmit          # 类型检查，PR 前必须过
node scripts/build.mjs    # 直接构建 dist（开发用）
```

桌面架构、面板约定与验收细节见 [`docs/desktop/README.md`](docs/desktop/README.md)，本机交接信息见 [`HANDOFF.md`](HANDOFF.md)。

## 3. 跑测试（PR 前请自己跑一遍）

桌面/协议相关的核心回归（Windows，仓库根目录下）：

```powershell
cd tests
$env:PYTHONPATH='<仓库根目录>'
..\desktop\.venv\Scripts\python.exe -B -m unittest test_desktop_sessions test_desktop_rpc test_activity test_attachments test_runtime test_side_chat test_web test_desktop_projects test_child_activity
```

界面 E2E（隐藏窗口 + 本地合成数据，**不花钱、不调外部模型**）：

```powershell
cd desktop
node tests\execution-ui.cjs
```

它会打印一行 JSON，含 `renderer_errors`（必须为空）、`version`、`paid_api_calls`（必须为 0）。

## 4. 打包与自测安装

```powershell
python desktop\scripts\build-runtime.py     # PyInstaller onedir 运行时
npm run package --prefix desktop            # NSIS 安装包 → output\release\desktop\
desktop\scripts\install-local.ps1 -InstallDirectory 'G:\Apps\ECA Desktop'
```

安装脚本会做**握手校验**（协议版本 + 后端版本 + 能力位）和负载文件哈希校验。装完请确认：

- 握手版本等于你刚构建的版本
- `%LOCALAPPDATA%`/数据目录下的 `preferences.json` 哈希没有变化（安装不该动用户配置）
- 应用能正常启动并 `renderer_errors` 为空

## 5. 代码约定

**必读** [`AI_CODER_GUIDE.md`](AI_CODER_GUIDE.md)。里面是各子系统的不变量（上下文预算、编辑匹配、审批与文件基线、记忆证据门槛、评测口径），改动这些区域前先读对应段落，别绕开它们。

几条通用的：

- **不提交密钥**：`.env` 已在 `.gitignore`；密钥只走环境变量或系统凭据，不写进日志、异常信息、报告和会话文件
- **不给没验证过的结论**：行为改动要附上你实际跑过的命令与结果；跑不了就说明跑不了，不要写成「应该可以」
- **测试不连付费 API**：默认测试用本地假 provider / 合成数据；真实模型评测是显式开启的独立流程（见 `benchmark/AGENT_EVAL.md`）
- **保持改动可回滚**：文件修改走既有的审批、基线与撤销链路，不要新增绕过它们的写文件路径

## 6. 提交与 PR

- 一个 PR 一件事。顺手重构请单独提，别混在行为修复里
- Commit 标题用英文祈使句，正文说清**为什么**，以及测过什么：

```
fail stalled model streams instead of waiting forever

- the chat stream now requires real content to count as progress …
- tests: a silent stream and a keep-alive-only stream both raise
```

- `CHANGELOG.md` 用中文，按版本分节，写「改了什么 + 为什么 + 怎么验证的」
- 升版本时四处一起改：`desktop/package.json`、`desktop/package-lock.json`、`pyproject.toml`、`eca/__init__.py`

## 7. 发布（维护者）

1. 升版本 + 补 `CHANGELOG.md`
2. 用打包产物跑一次 E2E：`$env:ECA_TEST_EXE='output\release\desktop\win-unpacked\ECA Desktop.exe'; node tests\execution-ui.cjs`
3. `git tag -a vX.Y.Z -m "…"` → push tag
4. `gh release create vX.Y.Z output\release\desktop\ECA-Desktop-X.Y.Z-x64-Setup.exe --title … --notes-file …`
5. 发布说明里**必须**包含 SHA256 与「未签名」说明；下载回来核对哈希后再对外说「可以下载」

## 8. 已知踩坑（省你一小时）

- **PowerShell 写文件会加 BOM**：`Set-Content -Encoding utf8` 在 PS5 下写 BOM，会破坏 JSON / electron-builder 配置 / 测试文件开头。改文件请用编辑器或脚本（Node/Python）写 UTF-8 无 BOM
- **Git 的 LF→CRLF 警告**：仓库以 LF 存储，Windows 检出会有警告，属正常；不要为了消警告改 `.gitattributes`
- **CSS 挂在 `.eca-app` 下**：浮层/菜单要 `createPortal` 到 `.eca-app`，portal 到 `body` 会完全没样式
- **`live` 不能查库**：流式期间 `live` 每秒被轮询十余次，不能做数据库查询或全量重算（有回归测试钉住这点）；需要缓存
- **原生 `<select>` 无法美化**：需要自定义样式时用自绘菜单，不要试图给原生下拉加 CSS
- **改动 `desktop/runtime` 前先关应用**：运行中的进程会占用文件，替换会失败

## 9. 许可

当前仓库未附带开源许可证文件。在补充之前，**默认不接受以再分发为目的的贡献**；如需在其他项目中使用，请先开 Issue 说明用途。
