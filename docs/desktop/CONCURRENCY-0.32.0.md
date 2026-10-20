# 0.32.0：同一项目内的多会话并发

左侧可以在任务运行或等待授权时新建、切换会话。每个会话保留独立的模型连接、任务、流式输出、授权请求、任务草稿、验证设置与子任务。侧栏显示运行数量和每个会话的“运行中 / 待确认 / 侧聊中”状态。

停止按钮只取消当前会话的主任务及其子任务。切换会话不会重新发送请求，也不会终止后台主任务或侧聊。窗口退出会检查所有会话；确认停止并退出或收到通信 EOF 后，取消并清理全部运行时。没有关窗后台运行能力。

## 实现

- `eca/desktop_sessions.py` 管理一个项目 Store 和多个 DesktopRPC 工作实例。项目锁仍属于整个进程，CLI 不能同时占用该项目。
- 每个 Runtime 不拥有共享 Store；关闭所有运行时后由协调器统一释放数据库与锁。CLI 的 Runtime 默认仍拥有 Store。
- 任务及授权操作按 `session_id` 和 `run_id` 定位。不存在的会话、过期 run 或重复回答会被拒绝。
- 快照和 live 返回 `view_revision`、`active_sessions`、`any_busy`、`running_count`。界面只接受较新的选中视图，不将延迟快照套到另一会话；流式游标只能用于同一会话。
- 非选中会话的文本流保留在后端，仅结构变化通知界面更新侧栏。主进程按会话保存模型选择元数据；新会话不继承其他会话临时开启的完全访问。
- 主任务预算按会话独立，子任务及侧聊继续计入各自主任务的共享预算。用量记录沿用 `.eca`。

## 范围与边界

本版支持同一活动项目内多会话并发，不是多个项目并行。项目里还有主任务或侧聊运行时不能切换或关闭项目。

所有会话仍使用同一个工作目录。文件工具在读取版本不一致、等待批准期间被修改以及撤销时版本不符的情况下拒绝覆盖，用户需要重新读取后再修改。Shell、后台进程和外部 MCP 操作可能直接改变共享文件或外部系统，没有自动文件合并或完整副作用隔离。建议并发任务分工到不同文件；需要隔离的子任务仍可使用已有隔离工作区。

右侧浏览器和手动终端仍跟随当前选中会话。切换时关闭当前浏览器，若存在运行中的手动终端会先提示停止终端；不会因此停止后台 Agent 主任务。侧聊及子 Agent 内容可切回查看。

## 本地验证

测试使用 G 盘临时项目和本地 SSE 模型，不使用付费 API。

```powershell
$env:TEMP='G:\DevCache\Temp\easy-coding-agents'
$env:TMP=$env:TEMP
$env:ECA_TEST_TMP=$env:TEMP
$env:PYTHONPATH='tests'
desktop/.venv/Scripts/python.exe -B -m unittest test_desktop_sessions test_desktop_rpc test_desktop_reasoning test_runtime test_side_chat test_background test_workflow test_workers test_child_activity -q
npm.cmd --prefix desktop run build
npm.cmd --prefix desktop test
node desktop/tests/concurrent-sessions.cjs
node desktop/tests/activity-stream.cjs
node desktop/tests/e2e.cjs
```

测试覆盖：同时等待多个模型、后台授权、跨会话回复拒绝、批准期间的文件冲突、独立模型与审批、独立草稿、切换与重载不重放、取消一项保留另一项、空闲页面退出时仍检查后台任务、EOF 全部清理和重新打开后的恢复。

报告及截图：`output/playwright/concurrent-sessions/`。构建与安装验收记录：`output/release/desktop/release-0.32.0.json`。干净 Windows 环境验证需单独完成。

## 本轮结果

- Python 定向回归 93 项（1 项跳过、0 失败），最终协调器 6 项及 CLI 2 项检查通过。
- 桌面 Node 15 项、TypeScript 构建通过。
- 原有桌面完整流程通过：13 次本地请求，含授权、验证修复、模型错误、崩溃恢复及停止退出。
- 开发版和打包版并发流程通过：每轮 4 次本地请求，覆盖运行中切换、授权路由、模型/草稿独立、重载及独立取消。
- 打包版最终并发测得停止反馈 2 ms、取消完成 65 ms；这是本地模拟服务实测，不是外部模型响应速度承诺。
- 开发版及打包版右侧工作区流程通过，包括只读侧聊、原生终端、浏览器模块和资源清理。
- 实时状态及 tokens/s 流程通过；包内 JavaScript 与最终构建一致，后端握手包含 `concurrent_sessions`。

安装包为未签名本地预览版。2026-10-20 已更新至 `G:\Apps\ECA Desktop`：371 个安装文件校验通过，后端握手为 0.32.0，原模型配置文件哈希保持一致，未修改用户项目会话。

安装后并发流程及实时状态/tokens/s 流程均通过，共 6 次本地模拟请求、0 次付费 API 调用、无界面运行错误。并发测试停止反馈 1 ms、取消完成 63 ms；实时状态测试停止反馈 2 ms、取消完成 62 ms。测试使用 G 盘隔离的项目和应用数据。干净 Windows 环境验收仍未完成。
