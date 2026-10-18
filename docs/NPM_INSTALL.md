# npm 安装与 ecs 命令

当前提供本地 `.tgz` 安装包，尚未发布到 npm registry。安装和使用本地包无需 npm 账号；公开发布需要发布者账号。包名暂定 `easy-coding-agent-cli`，`private: true` 防止误发布；确认账号、可用包名和许可证后再发布。

## 安装

需要 Node.js 20+、Python 3.11+（含 venv/ensurepip）。此版是 npm 启动器加 Python 运行时，不是独立原生二进制。

下载或构建本项目的安装包后：

```sh
npm install -g ./easy-coding-agent-cli-0.18.0.tgz
ecs --version
ecs --setup
cd your-project
ecs
```

`--setup` 是可选的提前初始化。直接输入 `ecs` 也会在首次运行时自动建立独立虚拟环境，从包内 wheel 安装 ECA，并联网安装 Python 依赖。后续启动复用环境，无需手动激活 venv，也无需运行 Python 脚本。npm 安装阶段不运行 postinstall，不自动下载 Python 或模型。

Windows PowerShell 通常也可以输入大写 `ECS`；跨平台统一使用小写 `ecs`。若 PowerShell 的脚本执行策略拦截 npm 生成的 shim，可使用 `ecs.cmd`，无需降低系统执行策略。旧 `eca` 命令继续支持 Python 安装方式，Python 包同时注册 `ecs` 别名。

## Windows：存储放到 G 盘

npm 默认全局目录可能在 C 盘。可显式安装到 G 盘：

```powershell
npm install -g --prefix G:\DevTools\npm .\easy-coding-agent-cli-0.18.0.tgz --cache G:\DevCache\npm
G:\DevTools\npm\ecs.cmd --setup
```

将 `G:\DevTools\npm` 加入用户 PATH，重新打开终端后即可输入 `ecs`。这是 npm 可执行文件目录；不要把包的 node_modules 目录加入 PATH。

启动器在 Windows 检测到 G 盘时，将 Python 环境、pip 缓存、安装临时文件放在 `G:\DevCache\easy-coding-agent\runtimes`。其他机器默认使用用户缓存目录。

可选环境变量：

- `ECA_RUNTIME_HOME`：运行环境和缓存根目录，建议绝对路径。
- `ECA_PYTHON`：指定 Python 可执行文件的完整路径，不接受拼接的命令或参数。

运行环境按版本和内置 wheel 摘要区分。新版本首次启动会创建新环境，旧环境不会自动删除。npm 卸载启动器也不会删除独立环境或项目 `.eca` 数据。

## 行为和诊断

- npm 的 bin 映射创建终端命令，保留工作目录、参数和退出码；从当前项目读取配置和保存会话。
- 原有模型配置、`--worker-first`、`--verify-command` 等功能全部透传。
- `ecs --version` 无需 Python、初始化或网络；`ecs --help` 需要完成首次初始化。
- 内置 wheel 摘要校验失败时拒绝启动；使用 Python `-I` 启动，防止当前项目中的同名模块或 PYTHONPATH 替代安装的 CLI。
- 并发初始化使用独占锁；进程崩溃后锁可能保留。只有确认没有安装进程后，才手动移除提示中的具体 `.lock` 目录并重试。
- 缺失 Python 或安装失败时显示处理建议，不会静默使用系统中其他版本的 ECA。
- MCP SDK 为可选依赖；如需使用，可通过 `ecs --setup` 显示的运行环境 Python 路径安装该版本的 MCP extra。npm 启动器本身不额外启用 MCP。

## 开发与打包

在仓库根目录执行（构建 Python 需已有 pip、setuptools 和 wheel）：

```sh
npm test
npm pack --pack-destination output/release
```

`prepack` 构建与 npm 版本一致的 wheel，写入摘要清单。发布包采用文件白名单，不包含 `.env`、会话数据库、测试缓存、项目虚拟环境或整个源码仓库。

公开发布前需确定 npm 账号/包名、明确许可证并移除 `private: true`，再审查 `npm pack --dry-run` 内容。当前没有执行 `npm publish`，不能使用 registry 包名假装已经发布。
