# v0.10：多项验收与有界修复

v0.9 能在模型结束后执行一次检查。v0.10 把它扩展为顺序验收清单，并提供显式开启的修复循环。

```powershell
eca --cwd G:\Projects\your-project -p "修复导出功能，保持现有兼容性" --accept-edits --allow-shell --verify-command "python -B -m pytest -q" --verify-command "python -B scripts/check_exports.py" --repair-attempts 2
```

- `--verify-command` 可重复，最多 10 项，顺序运行；第一项失败即停，后续命令不执行。
- `--repair-attempts` 默认 0，保持 v0.9 的不自动重跑行为。显式设为 1..3，表示允许修复后重新执行所选整组命令，包括之前通过的命令。仅支持非隔离 code 模式。
- 正常失败或检测到无测试时，将原始任务、所选检查和已有工具输出交给模型，要求针对性修复，不允许削弱测试或原始要求。修复结束后重新执行整组检查。
- 命令拒绝、超时、取消、进程异常终止或结果不明，不进入自动修复。指纹不可确认也不会因为重试次数尚有剩余而继续。
- 每轮修复有独立的 `max_turns` 限制；最多初始任务加 N 轮修复。开启修复会增加模型请求与工具执行，仍记录在原会话账本中，不自动扩大配置预算。
- `--allow-shell` 批准本次任务所有 Shell 命令，并非沙箱。应只选择可安全重复执行的检查；不要把部署、扣费或数据迁移当作可重复的验收命令。

## 状态和恢复

JSONL 增加 `verification_suite` 事件，最终 `status` 同时包含整组状态与最新单项 `verification`。`/progress` 也显示整组验收记录。

每轮记录 `attempt`、已完成的 `checks` 和状态；整体记录命令列表、修复预算与各轮结果。只有所有检查通过且从整组开始到结束源码指纹一致，才能标为 `passed`。后续文件变化显示 `stale`。不能将不同源码版本分别通过的结果拼成一次成功。

模型未完成任务时不运行检查，整体为 `task_incomplete`；单项未通过或修复预算耗尽为 `failed`，具体原因保留在 `checks`；单项均通过但无法确认整组指纹一致时为 `unconfirmed_snapshot`。取消和异常为 `interrupted`。进程意外退出留下的运行中记录，读取时按中断显示，不自动重放命令。

退出码沿用 v0.9：0 为任务完成且指定验收通过；1 为执行异常；2 为模型任务未完成；3 为任务结束但指定验收未通过；130 为取消。

## 边界

这是受限制的修复工作流，不保证模型一定修好，也不证明测试覆盖充分。检查结果来自普通 Shell，依然不具备 OS 级隔离。仓库测试可以被模型修改；提示词要求不得削弱测试并非防篡改机制，重要验收应使用独立外部检查。

指纹、未知用量、零测试识别和摘要恢复的限制继续适用，见 [v0.9](UPGRADE-v0.9.md)。本轮使用离线模型 fixture 与实际 CLI 测试，没有调用付费 API，也没有重新生成完整 StockFlow 项目。

## 验证

专项覆盖默认不修复、整组重跑、次数耗尽、取消恢复、未知结果不重跑、跨检查版本变化、模式限制和参数校验。真实 CLI 的 Chat Completions / Anthropic 测试执行两项独立检查并断言整组事件。

2026-10-17：专项 21 passed；最终全量 **188 passed, 1 skipped**（346.54 秒）。命令：`python -B -m pytest -q -p no:cacheprovider --basetemp G:\DevCache\Temp\easy-coding-agents\v010-final`。测试不访问付费 API。

wheel 的 23 个 `eca` 运行时模块已逐字节核对，与最终源码一致。SHA256：
`832b309c570472893b0f2c667e0745586785f4fc10d3b071b97552e8a4c636fd`。
