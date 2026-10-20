# 0.33.0 多项目工作空间

## 行为

- 左侧按项目分组排列会话，支持折叠、搜索、项目内新建会话，以及关闭空闲项目。项目名称悬停显示完整路径，保留陶土材质与当前会话标记。
- 多个项目的主任务和侧聊可以同时运行。切换只改变当前查看的内容，原任务继续执行。
- 模型、审批模式、授权回复、草稿、验证设置与消息按项目和会话定位；停止按钮只取消当前会话。
- 浏览器和交互终端在会话切换时保留。后台浏览器隐藏；切回后恢复标签和终端输出。关闭项目时清理该项目的工作区，退出应用时清理全部项目。
- 每个项目持有各自的 `.eca` 锁。CLI 已占用项目时打开失败，已打开项目及其任务继续保留。
- 关闭项目保留磁盘上的会话记录；运行中的项目需要先停止任务及侧聊。应用退出仍需要确认停止所有项目，重启后不会自动重放任务或授权。

## 实现

`eca/desktop_projects.py` 管理项目级协调器，复用 `DesktopSessions` 和 `Runtime`。规范化真实路径作为 `project_id`，相同目录的路径别名不会重复加锁。会话 ID 相同时也必须按项目路由。

主进程将项目与会话组合为 `workspace_owner`，用于浏览器、终端与子 Agent 查看；过期的工作区操作会被拒绝。模型选择和资源管理按此组合键保存。界面草稿使用同一范围，避免相同会话 ID 串数据。

后台项目的流式文本保存在对应运行时，只推送结构变化以刷新分组状态；前台快照继续使用全局 `view_revision`、后端 ID、会话和流游标拒绝过期数据。

## 范围与限制

不同项目使用独立根目录、模型设置和会话数据库。同一项目里的多个任务仍共用工作目录，文件工具沿用冲突检查。该机制不是操作系统安全沙箱；完全访问模式下的 shell、MCP 或外部服务可能访问其他目录或共享资源。

运行越多，模型请求、内存和供应商限额消耗越多。闲置项目可通过项目标题旁的关闭按钮释放资源。搜索涵盖已打开项目的会话以及最近项目名称；未打开项目的历史记录在打开后加载。

## 本地验证

测试项目、应用数据和缓存全部位于 `G:\DevCache\Temp\easy-coding-agents`，使用本地模拟服务，不调用付费模型，不访问用户项目。

```powershell
$env:TEMP='G:\DevCache\Temp\easy-coding-agents'
$env:TMP=$env:TEMP
$env:ECA_TEST_TMP=$env:TEMP
$env:PYTHONUTF8='1'
$env:PYTHONPATH='tests'
desktop\.venv\Scripts\python.exe -B -m unittest test_desktop_projects test_desktop_sessions
npm.cmd run build --prefix desktop
npm.cmd test --prefix desktop
$env:ECA_PYTHON="$PWD\desktop\.venv\Scripts\python.exe"
node desktop/tests/concurrent-projects.cjs
```

打包版设置 `ECA_TEST_EXE` 为 `output\release\desktop\win-unpacked\ECA Desktop.exe`，并设置 `ECA_TEST_MODE=packaged`。安装后同样指向实际安装路径，设置 `ECA_TEST_MODE=installed`。

重点覆盖跨项目等待模型、后台授权、相同文件名隔离、会话/模型/草稿独立、切换和重载不重放、独立取消、项目关闭、工作区保留、过期操作拒绝、退出清理、深浅主题及窄窗口。结果保存在 `output/playwright/concurrent-projects` 和 `output/release/desktop/release-0.33.0.json`。

安装包是本地未签名预览版，干净 Windows 环境验证尚未完成。安装状态以发布报告为准。

## 本轮结果

- Python 定向回归 99 项完成，1 项跳过、0 失败；桌面 Node 15 项及 TypeScript 构建通过。
- 原有桌面完整流程通过（13 次本地请求），包括授权、模型配置、验证修复、恢复、崩溃及停止退出。
- 开发版和打包版的多项目流程均通过（各 4 次本地请求）。打包版测得停止反馈 1 ms、取消完成 57 ms，仅代表本地模拟服务测试。
- 右侧工作区流程通过，覆盖只读侧聊、原生终端、浏览器隔离、中文路径、终端子进程清理。
- 打包版子 Agent 流程通过（20 次本地请求），包含并行/串行委派、授权拒绝、错误、停止传播、侧边查看和重载恢复。
- 371 个打包文件校验通过，握手包含 `concurrent_projects`；包内 JavaScript 与最终构建一致。深浅主题、窄窗口截图在上述测试目录中。

已安装到原位置，371 个安装文件与后端握手校验通过。安装版多项目流程通过（4 次本地请求），停止反馈 1 ms、取消完成 60 ms。配置文件前后哈希发生变化，不能据此声称逐字节保留。本轮没有调用付费 API 或修改用户项目。
