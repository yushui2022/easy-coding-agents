# 子 Agent 对话入口与右侧内容

主模型调用 `delegate` 或 `delegate_parallel` 时，主对话在该次工具调用的位置显示一行子任务入口：小陶土标志、任务名称和状态。六种标志按同一主会话内的创建顺序循环分配，不预设研究、编码等固定角色。

点击入口，在右侧工作区打开对应标签；主会话继续执行。已显示子任务状态时，底部不再重复显示 `delegate_parallel` 执行提示。右侧以子任务回答为主，顶部显示任务名称与模型；完整任务说明和修改数量收进可展开的说明中。实际工具记录保留，Markdown 表格支持横向滚动。运行中的文字也按 Markdown 渲染。`已返回` 只表示子任务返回报告，不表示独立验收通过。隔离子任务的文件仍需主 Agent 合并。

关闭查看标签不取消任务，不切换执行会话。停止主任务仍会取消运行及排队的子任务。授权继续在主对话处理，右侧没有另建绕过权限的执行入口。窄窗口使用已有工作区展开布局，Escape 返回主对话。

## 通信与历史

- 子任务持久记录 `parent_call_id`、`parent_message_index`、模型及任务描述，将入口关联到实际调用，支持同一会话的多轮任务。
- CLI 保留串行子任务的工具参数、结果、差异及提示输出，仍执行密钥脱敏。
- 串行和并行统一发送带子会话 ID 的 `subagent_progress`；子任务文本不混入主对话流，也不进入有界事件日志。
- `subagent.snapshot({owner,id,backend_id?,message_revision?,before?})` 只读当前主会话的直属子任务，不调用会话修复或恢复执行。消息每页 50 条；相同消息版本不重复发送历史。运行中预览保留最近 64,000 字符，完整回答仍保存在子会话中。
- 主 Agent 与子 Agent 在开始执行工具时清除已保存回答的流式副本，避免正文重复显示。
- 文本事件由主进程限频通知右侧；关闭或隐藏的子任务面板不请求刷新，主对话不为每个子任务 token 加载全量快照。
- 桌面会话导航和项目默认恢复只选择顶层会话。CLI 原有会话列表保持兼容。
- 重新加载界面恢复查看标签，不重放任务；读取崩溃遗留的运行状态按“已停止”展示，不改写保存记录。
- 旧会话没有调用关联字段时，根据已保存工具结果的子会话 ID 关联入口。

## 验证命令

依赖、临时目录和发布产物均在 G 盘。测试使用独立临时项目与隐藏 Electron 窗口，不操作用户正在使用的窗口，不调用付费 API。

```powershell
$env:TEMP='G:\DevCache\Temp\easy-coding-agents'
$env:TMP=$env:TEMP
$env:ECA_TEST_TMP=$env:TEMP
$env:PYTHONPATH='tests'
desktop\.venv\Scripts\python.exe -B -m unittest test_child_activity test_desktop_rpc
npm --prefix desktop run build
npm --prefix desktop test
cd desktop
node tests/subagents-e2e.cjs
```

测试覆盖直属子任务访问检查、分页和脱敏、串行与并行实时内容、排队、拒绝授权、异常、取消传播、关闭与重开标签、刷新不重放、项目恢复、六种素材加载、Markdown 表格、深浅主题和窄窗口。实际执行报告与截图位于 `output/playwright/subagents/`。构建和本机验收不代表干净 Windows 环境或付费模型任务质量验收。

本机安装及测试结果见 [0.29.0 验收记录](VERIFICATION-0.29.0.md)。
