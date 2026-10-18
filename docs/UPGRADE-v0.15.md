# v0.15：npm 安装包与 ecs 终端命令

新增 Node.js 启动器，在安装 npm tgz 后直接运行 `ecs`，不用逐次启动脚本或激活 Python 虚拟环境。Python 包也注册 `ecs` 别名，保留 `eca`。

## 当前交付

- 本地包：`output/release/easy-coding-agent-cli-0.15.0.tgz`，约 105 KB。
- npm 安装阶段没有 postinstall；首次 `ecs` 或 `ecs --setup` 创建独立 Python 环境并联网安装依赖。
- 仍需用户机器已有 Node.js 20+、Python 3.11+（venv/ensurepip）；不自动下载 Python 或模型。
- npm 包名暂定，保持 `private: true`；未公开发布，不要求用户现在注册 npm 账号。
- 本机已经安装到 `G:\DevTools\npm`，该目录已加入用户 PATH。重新启动终端后可用 `ecs`，Windows 中 `ECS` 也已验证。
- 独立 Python 环境位于 `G:\DevCache\easy-coding-agent\runtimes\0.15.0-b34482cdcbce8cc7`。

## 防误安装与启动边界

npm 包携带本地构建且版本一致的 wheel，不从 registry 猜测并安装同名 Python 项目。轮子摘要、manifest 和版本验证通过后才启动。参数通过数组传递，不拼 shell 命令；调用者工作目录与退出码保留。

Python 使用隔离模式 `-I`，防止项目目录中的同名模块或 PYTHONPATH 替换已安装 CLI。初始化目录有独占锁，成功后写入完成标记；崩溃后不会擅自清理其他安装进程的锁。

Windows 有 G 盘时运行环境、pip 缓存、安装临时文件默认存入 G 盘。支持 `ECA_RUNTIME_HOME`、`ECA_PYTHON` 覆盖。旧版本运行环境不自动删除，需使用者确认无用后清理。

## 验证

- Node 启动器 7 项测试通过：缓存路径、Python 检测、摘要与路径校验、无依赖版本查询、参数/工作目录/退出码透传、复用已安装环境。
- 实际 `npm pack` 后，使用 tgz 安装到 G 盘；生成 ecs/ecs.cmd/ecs.ps1，版本查询和首次依赖安装成功。
- 在仓库外目录运行已安装 `ecs --help`、`--doctor --json` 成功；doctor 识别的是调用者目录，未进行模型网络请求。
- 复用验证时设置 `PIP_NO_INDEX=1` 和无效的 `ECA_PYTHON`，帮助命令仍可启动，无需重新安装或寻找基础解释器。
- 项目内放置会报错的 `eca.py`，已安装 CLI 仍正常启动，未加载该文件。
- npm tarball 恰含 6 项白名单文件，无 `.env`、会话、缓存、源代码历史；内置 wheel 的 25 个 ECA 模块与当前源码逐字节一致，entry points 同时包含 eca、ecs。
- tarball SHA-256：`6b4895d66cddf0abb5eb0c71613b5873dc1843a9ceef4cf972d743ad4928b5ef`。
- 内置 wheel SHA-256：`b34482cdcbce8cc7091ce644aae639046fec0e7648901b68acc963d0b0910907`。
- Python 完整回归：**222 passed, 2 skipped**，耗时 556.21 秒。

真实安装只在当前 Windows 机器验证；macOS/Linux 安装尚待实机验收。Python 依赖沿用版本范围解析，没有锁定完整依赖树，不宣称跨时间完全可复现。此轮未调用付费模型 API。

详细步骤见 [npm 安装说明](NPM_INSTALL.md)。公开发布还需要发布者 npm 账号、可用包名和明确许可证；本次未执行 npm publish。
