# macOS 版桌面（Apple Silicon）

上游只发布 Windows x64 安装包，`desktop/` 里也留有若干 Windows 假设。这个分支把同一份
Electron + Python 代码做成可以在 Mac 上构建、运行和打包的版本。**没有重写界面**：UI、
会话、审批、记忆等行为和 Windows 版是同一套源码。

## 和上游的差异

只为跨平台改了以下几处，改动点都能在原文件里搜到注释：

| 文件 | 改动 | 原因 |
| --- | --- | --- |
| `desktop/src/main/index.ts` | 新增 `devPython()`：优先用仓库 `.venv/bin/python`，其次 `python3` | Windows 叫 `python`，macOS 只有 `python3`；开发模式不再需要手动设 `ECA_PYTHON` |
| `desktop/src/main/index.ts` | 打包后的后端名增加无后缀的 `eca-backend` | macOS 的可执行文件没有 `.exe` |
| `desktop/src/main/terminal-host.ts` | darwin 用 `/bin/zsh -l` 起项目终端 | 登录 shell 才会读到用户真实 `PATH`（Homebrew、`~/.local/bin` 等） |
| `desktop/src/renderer/workspace/Workspace.tsx` | 工作区快捷键接受 `Cmd` | macOS 用户按 `Cmd+T` / `Cmd+`` 才符合习惯 |
| `desktop/package.json` | 新增 `mac` 打包目标（dmg / arm64）、`package:mac`、`backend:mac` 脚本；不再在打包时排除 `darwin-*` 的 node-pty 预编译产物 | 上游 `files` 规则会把 macOS 终端依赖一起排除掉，导致终端打不开 |
| `desktop/scripts/build-backend-mac.{mjs,py}` | 新增 macOS 后端冻结脚本 | 上游 `build-runtime.py` 依赖 `.ico`、VSVersionInfo 和 PyInstaller 的 Windows 参数 |
| `desktop/resources/icon.icns` | 由 `docs/assets/eca-logo-v1.png` 生成 | macOS 应用图标格式 |

CLI 部分本来就是跨平台的，未改。

## 构建

前置：Node.js 20+、Python 3.11+、Xcode Command Line Tools（`xcode-select --install`）。

```bash
cd easy-coding-agents
uv venv --python 3.12 .venv          # 或 python3.12 -m venv .venv
uv pip install --python .venv/bin/python -e . pyinstaller "mcp>=1.26,<2" jsonschema

cd desktop
npm install
npm run backend:mac                   # PyInstaller 冻结 Python 核心 → desktop/runtime/eca-backend
npm run package:mac                   # 产出 output/release/desktop/ECA-Desktop-<版本>-arm64.dmg
```

国内网络如果 Electron 下载卡住，给打包命令加镜像：

```bash
ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/ npm run package:mac
```

## 开发调试

```bash
cd desktop
npm run dev        # tsc + esbuild 后直接启动 Electron
```

`npm run dev` 会自动使用仓库 `.venv/bin/python` 跑 `python -m eca.desktop_rpc`；要换解释器就设
`ECA_PYTHON=/path/to/python`。应用数据默认在
`~/Library/Application Support/ECA Desktop`，用 `ECA_DESKTOP_DATA_HOME` 可以隔离一份测试数据。

macOS 冒烟测试（真实 Electron 窗口 + 真实 Python 后端 + 本地 HTTP 假模型，不调用付费接口）：

```bash
ECA_PYTHON=../.venv/bin/python node tests/mac-smoke.cjs
```

覆盖：窗口启动、模型连接与模型列表、打开项目、发任务、写入审批、后端真实写文件。
2026-10-29 在 macOS 27.2 / arm64 上通过，渲染层无报错。

一键构建 + 安装（含 ad-hoc 签名和 dmg 重建）：

```bash
cd desktop
scripts/package-mac.sh            # 只产出 dmg
scripts/package-mac.sh --install  # 顺便安装到 /Applications
```

## 安装

把 dmg 里的 `ECA Desktop.app` 拖到 `/Applications` 即可。构建产物没有签名和公证，
本机构建的包可以直接打开；如果从别的机器拷贝过来，第一次需要：

```bash
xattr -cr "/Applications/ECA Desktop.app"
```

### 实际产物（2026-10-29，macOS 27.2 / arm64）

| 路径 | 说明 |
| --- | --- |
| `/Applications/ECA Desktop.app` | 已安装并 ad-hoc 签名，可直接双击 |
| `output/release/desktop/ECA-Desktop-1.19.0-arm64.dmg` | 177 MB，内含同一份已签名 app |
| `desktop/runtime/eca-backend/` | PyInstaller 冻结的 Python 核心（约 50 MB） |

打包版再用同一份冒烟测试跑过：窗口、模型连接、打开项目、发任务、审批、后端写文件全部通过，
渲染层无报错。启动日志里会出现一条
`sandbox_extension_issue_file failed for ... Helper.app/Contents/Resources`，
这是 ad-hoc 签名包的已知提示，不影响功能。

## 已知边界

- 只有 **arm64** 产物，Intel Mac 没有验证过。
- 未购买 Apple 开发者证书：没有签名、没有公证，也没有自动更新。
- 上游文档里的 `--sandbox docker` 需要 Docker Desktop；macOS 上没有做额外验证。
- 项目终端是 `zsh`（登录 shell），不是 Windows 的 PowerShell；用到 PowerShell 语法的提示词需要改写。
