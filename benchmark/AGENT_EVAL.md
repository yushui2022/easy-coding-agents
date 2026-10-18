# ECA 固定编码任务评测（suite v4）

此工具用于记录自身基线与后续回归，不是 Pi/OpenCode 排名。需要从源码仓库运行，npm 运行时不包含评测集。

```powershell
# 先在环境变量中配置 DEEPSEEK_API_KEY，不要写入源码或结果文件。
python -B benchmark/agent_eval.py --model deepseek-flash
# 重复试验可降低单次模型采样的偶然影响：
python -B benchmark/agent_eval.py --model deepseek-flash --cases bug api user_edits --repeats 3
```

默认 14 项、各一次、逐项串行。可通过 `--base-url`、`--api-key-env` 配置其他 OpenAI 兼容接口。模型必须支持工具调用。默认主 Agent 16 轮、子 Agent 每个 8 轮、每项 360 秒、输出上限 4096 tokens；摘要、网络重试和子 Agent 请求计入真实请求总数。恢复场景两段执行共享墙钟预算，但恢复后重新获得运行轮次预算。

`--rates` 接受经核实的每百万 tokens 价格快照，例如包含 input/output/cache_read/currency 的 JSON。未提供价格时费用保持 unknown；请求用量缺失时不把缺失部分当作零。不要用旧价格推断当前账单。

## 固定任务

| ID | 内容 | 额外独立检查 |
|---|---|---|
| bug | 均值函数修复 | 单元素、空输入和其他数值 |
| refactor | 跨模块迁移并删除旧模块 | 新接口可用、旧文件删除、行为保持 |
| tests | 为已有实现补测试 | 至少五项测试；故意损坏实现后必须失败 |
| parallel | 两个独立子任务与父级合并 | 两个子 Agent 完成、父 Agent 使用合并并测试 |
| resume | 首次保存后协作取消，再重开会话 | 完成两处修改，没有重复写入 |
| api | 浮点价格接口迁移为整数分 | 三个模块一致，旧字段消失 |
| user_edits | 带用户未暂存修改和未跟踪笔记的修复 | 定制函数、笔记原文和 Git 暂存区保持 |
| tool_failure | 注入一次读取失败 | 故障确实发生，之后完成正确修复 |
| compact | 合成历史触发压缩，再继续任务 | 摘要确实发生，早期约束和边界行为保持 |
| config | 严格解析配置布尔值 | 字符串规范化、严格区分 float/int、拒绝非法输入 |

所有任务还检查原测试/指导文件不变、实际运行过非空且成功的测试、工具调用结果配对和 Agent 正常结束。模型的“已完成”文本不作为通过依据。

## 结果与复现

每次运行创建独立的 `output/agent-eval/run-UTC时间-随机标识/`，不覆盖旧目录：

- `manifest.json`：运行时与评测器源码 SHA256、Git HEAD 和 dirty 标记、fixture 摘要、模型/接口/参数、价格快照；结束时检查源码是否变化。
- `report.json` / `report.md`：总体结果、每次试验失败项、请求数、耗时、费用完整性和人工干预情况。
- `任务-次数.json`：详细外部验收、用量、工具失败、询问次数与预设恢复次数。
- `任务-次数/`：可检查的独立工作目录、Git index 和 `.eca` 会话数据。

中途取消或失败会保留已完成结果，未运行任务记为 incomplete，不从计划总数中消失。每项普通运行异常不会阻止后续任务；进程强杀无法保证当前项报告完整，但已写入的报告和会话仍保留。主任务耗时与包含外部验收的总耗时分别记录。

全程不人工修补结果、不重跑直到通过。询问需求时给固定答复并计数；预设的取消续接单独计数，不冒充人工介入。保留失败样例是基线的目的。

## 局限

这是合成 Python / SQLite 多模块 fixture 集；压缩使用合成历史，恢复使用协作取消，不能代替真实大型仓库、断电恢复或多语言评测。默认一次采样不能推断稳定成功率；模型别名可能在服务商侧变化，记录请求模型 ID 不等于锁定底层权重版本。

验收逻辑保存在工作目录外，但测试代码仍以宿主用户权限执行；精确 shell 白名单不是 OS 沙箱，本评测不声称能防止恶意生成代码作弊或越权。不要把原始会话数据库和密钥提交到 GitHub。默认离线 pytest 只验证评测器，绝不调用真实模型。

## SQLite 维护任务与验证闭环

新增 `shop_idempotency`（重复请求/冲突订单号）、`shop_cancel`（取消恢复库存且只执行一次）、`shop_batch`（批量下单整批提交或回滚）。每项从独立的五模块应用开始，保留已有公开测试；外部断言检查持久化、边界值及原有购买行为。它不是完整前后端系统或生产规模仓库。

```powershell
python -B benchmark/agent_eval.py --model deepseek-flash --cases shop_idempotency shop_cancel shop_batch --verify --repair-attempts 1 --max-turns 24 --timeout 600
```

`--verify` 在任务结束后执行已有运行时验证流程；`--repair-attempts` 显式允许 0..3 轮修复（默认 0）。所有轮次共享该任务墙钟预算；每次修复获得新的 max-turns 轮次预算。未开启 --verify 时保持原先执行方式。

JSON 的 `verification.rounds` 保存每轮命令证据；`first_verification_passed` 与 `repair_rounds` 区分首次验证和修复后成功。首次验证通过仅指公开命令通过，不代表外部验收通过。独立外部验收只在最后运行，不反馈给模型修补答案。既有 v1 的 10/10 结果不能当作本套件 13 项的实测结果。

### suite v3 契约澄清

首轮真实实测发现“保留测试”与字节不变验收之间存在歧义，批量接口请求体也未明确。v3 明确现有测试文件字节不变、新增测试另建文件，以及 dispatch 的 batch 请求体直接为 items 列表。验收断言未放宽；v2 的失败记录保留。两个套件版本的结果不得合并为同一成功率或当作运行时升级的因果证据。

### suite v4 数据库迁移

`shop_migration` 要求新增 reserved 列、迁移旧数据库并保留订单和库存、重复连接保留数据、拒绝更高版本，并增加 available API。外部验收检查新旧数据库和原购买行为；不模拟进程中途崩溃或多进程同时迁移。新增任务未包含在既有 9/9 基线中。
