# DeepSeek 真实 API 验收

这是显式运行的在线验收脚本，不属于默认 pytest，也不在 CI 中自动消费 API。它通过当前 `Agent`、`Provider`、`Store` 和文件工具执行任务，使用真实 DeepSeek 流式响应。

## 执行

在项目根目录执行，需要 Python 运行依赖及 Git：

```powershell
python -B benchmark/live_acceptance.py --model deepseek-flash
```

设置 `DEEPSEEK_API_KEY`，或在启动后通过隐藏输入提示提供密钥。密钥不会写入脚本、测试仓库或结果 JSON。模型名应以服务商 `/models` 的当前返回为准。

可用 `--cases bug refactor tests parallel resume` 选择场景。默认创建 `output/live-acceptance/run-时间-随机标识/`，不会复用或清理已有任务目录。可以用 `--output` 指定 G 盘其他目录。

费用默认未知；如需计算，必须显式提供核实过的每百万 Token 价格快照：

```powershell
python -B benchmark/live_acceptance.py --model deepseek-flash --rates '{"input":"0.15","output":"0.6","cache_read":"0.003","currency":"USD"}'
```

以上价格仅为 2026-10-17 查到的 Flash 非高峰价示例，不会随时间自动更新。运行前核对 [官方价格](https://api-docs.deepseek.com/quick_start/pricing/)。中断请求缺少用量时仍标为未知，已计价小计不是完整账单。

## 五个验收场景

| 场景 | 独立验收条件 |
| --- | --- |
| bug | 修复平均数计算，处理空输入及单元素；外部断言及原测试通过 |
| refactor | 函数跨模块迁移、调用方更新、删除旧模块、行为不变 |
| tests | 新增至少五项测试；原实现保持不变；故意损坏实现后测试必须失败 |
| parallel | 两个 code 子 Agent 修改不同文件，父 Agent 使用 merge_agent 合并并测试 |
| resume | 第一项写入后取消运行，关闭 Agent/Store 并重新加载会话，完成第二项修改，无重复写入 |

每项还检查：Agent 正常结束、实际运行过非空且成功的测试、工具调用结果完整配对、原有测试和指导文件未篡改、Git 暂存区未改变。外部验证逻辑放在工作目录之外；模型不能通过修改验收脚本获得通过。默认只批准精确匹配的 unittest Shell 命令；文件工具使用 accept-edits。

生成每项 JSON、总体 report.json，以及可检查的独立 Git 工作目录和 `.eca` 会话数据。report 包含运行器 SHA256、运行时基线提交、请求用量、状态、变更记录和结果。不要把整个原始会话数据库提交到 GitHub。

## 能证明什么

这些是从固定缺陷创建的小型 Git fixture 仓库，验证完整调用链和可复现的基础编码行为。它们不是大型真实业务仓库评测，也不证明 CLI 终端交互、进程强杀恢复、完整 OS 隔离、LSP/MCP 或所有语言栈的成熟度。

恢复场景使用协作取消和存储重开，不模拟断电或 SIGKILL。只跑少量任务不能得出统计性的成功率结论。固定命令审批也不是安全沙箱，测试代码仍以当前用户权限执行。

`tests/test_live_acceptance.py` 用离线固定修复验证验收器：初始缺陷必须失败，正确修复必须通过，删除原测试不能蒙混通过，新增测试必须捕获损坏实现。
