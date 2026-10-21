# 工作模式与目标（1.1.0）

桌面端原来只有「逐次确认 / 自动编辑 / 完全访问」三档审批，没有工作模式。后端其实早就有 `mode=code|plan|chat`（`eca/tools.py: allowed()`），CLI 用 Shift+Tab 切换，但桌面端从未暴露，也没有任何目标跟踪。

本轮把两件事补齐：

| 能力 | 位置 | 说明 |
|---|---|---|
| 工作模式 | `eca/modes.py`、`eca/desktop_rpc.py` `mode.set`、`desktop/src/renderer/ModeMenu.tsx` | 编码 / 计划 / 目标 / 对话，按会话保存 |
| 目标与验收标准 | `eca/goal.py`、`goal_update` 工具、`desktop/src/renderer/GoalBar.tsx` | 用户写目标，模型逐条标记 |

## 工作模式

四种模式并列，`eca/modes.py` 是唯一的值域来源（`MODES`、`WORKING`）：

| 模式 | 工具集 | 用途 |
|---|---|---|
| 编码 `code` | 全部工具 | 默认。可以改文件、跑命令、跑测试 |
| 计划 `plan` | 只读：read/glob/grep/code_search/repo_map/code_relations/skills/lsp_rename/web_*/todo/ask/delegate/lsp/goal_update | 先调研再给计划，一个文件都不改 |
| 目标 `goal` | 与编码相同 | 先定目标与验收标准，再一直推进到达标 |
| 对话 `chat` | 无工具 | 只按已有上下文回答 |

`code` 和 `goal` 都是「能干活」的模式：验收命令、自动修复、worker-first 和 code 子 Agent 用 `modes.working()` 判断，因此在目标模式下同样可用。1.1.x 里这些判断直接比较 `mode == 'code'`，加模式必然会误判成只读，所以先抽了这层。

约束：

- 模式**不是权限**。切到编码模式不会自动放行写文件，审批档位照旧生效；切到计划模式也不会放宽任何检查，只是把写类工具从工具表里去掉。
- 工具表在每次请求时按 `settings.mode` 生成，模式切换在下一轮请求生效。
- 运行中不能切换（`mode.set` 返回「请先停止或等待当前任务结束」）。正在跑的任务不会因为切模式而拿到另一套工具。
- 模式写进会话状态 `state['mode']`，切走再切回、重开项目都保留；新会话仍用项目默认模式。
- 计划模式不跑验证/自动修复链（`workflow.py` 只在 `code` 模式跑），也不允许 `write/edit/delete/shell`。被拒绝时工具层返回 `Denied: <tool> is unavailable in plan mode.`


### 计划是结构化清单，不是一段文字（1.1.1）

计划模式的提示词要求模型**用 `todo` 工具产出计划**：一条 pending 一步、按顺序、最多 50 条，再用一两句话概括。理由写在提示词里——「没有 todo 清单，用户就没有东西可以批准」。`todo` 本来就在只读工具集里，写类工具仍然全部拒绝。

对话区渲染 `PlanChecklist`，同一份 `state['tasks']` 在两种身份间切换：

| 阶段 | 标题 | 行为 |
|---|---|---|
| 计划模式、未批准 | 计划步骤 `0/3` | 逐条列出待办；底部提示「确认无误后再执行」 |
| 批准后、编码模式 | 执行清单 `1/3` | 模型每完成一步用 `todo` 勾掉，完成项加删除线，进行中项用橙色 |

「按此计划执行」把这份清单**原样交给模型**：`mode.set code` 之后发送「已批准的计划清单：1. … 2. …」，并明确要求开始一步标 `in_progress`、真正完成（改动落地且相关检查跑过）才标 `completed`，不许跳步、不许把没验证的标成完成。没有清单时退化为让模型先用 `todo` 记录步骤。

清单持久化在会话里，刷新、切会话都保留；右侧审查面板里的任务列表仍在，两处读的是同一份数据。

## 目标与验收标准

- 用户在输入区「目标」按钮里写：目标一句话 + 验收标准（每行一条，最多 20 条）。
- 存在会话状态 `state['goal']`：`{text, criteria:[{text,done}], status}`，`status` 为 `active|done|abandoned`。
- 目标存在时，`agent.system_prompt()` 追加一段：目标 + 编号后的验收标准 + 「做到全部满足再停；用 goal_update 记录真实进度；不得为了看起来完成而勾选」。
- 模型只能通过 `goal_update(updates=[{index,done}], status?)` 改勾选状态，1-based 编号与提示词里的编号一致。越界索引、非布尔 done、多余字段都会被拒绝。
- 全部勾选后 `status` 自动变 `done`，这段提示词随即停止注入（避免达成后继续绑着模型）；手动 `abandoned` 不会被自动改回。
- 界面：输入区上方一条目标条，显示 `目标文本 · 2/4`，展开看逐条标准，可编辑或清除。`done` 时变绿色。

### 目标模式（1.2.0 起是并列模式，不再是旁挂对象）

- **进入时必须先有目标**：在模式菜单选「目标」且本会话还没目标时，自动弹出目标对话框；不填完就没有「要达成什么」可言。填完才开工。
- **提示词分两种**：没有目标时说清楚「本会话还没有目标，不要先改文件，问清楚要什么结果」，避免模型自己编一个；有目标时要求推进到每一条验收标准都满足，**不要用进度汇报代替完成**。
- **未达标不许停**：模型不调工具想收尾时，`Agent.continue_goal()` 检查目标是否仍 `active` 且还有未勾选的条目，若有就追加一条 `[Runtime guidance] The session goal is not met: …`（持久化进历史，和输出上限恢复的提示同一机制），然后继续下一轮。
- **上限 6 次**：`Agent.GOAL_CONTINUATIONS = 6`，用完即停并提示「还差 N 条验收标准」。上限只针对自动续跑，不影响用户自己继续发指令；`max_turns` 剩余为 1 时也不再续跑，避免撞预算。
- 只在 `mode=goal` 时生效；计划模式、编码模式即使挂着目标也不会自动续跑。目标数据依旧存在会话里，切回编码模式不会丢，只是不再注入「必须达标」的措辞。
- 审批档位不受模式影响：进目标模式不会自动放开写文件或命令。

**重要边界**：勾选是模型的判断，不是验证。测试通过、文件状态、用户复核才算数；目标和子 Agent 报告一样是规划状态。UI 里也明确写了这句话。

## 协议变化

新增两个 JSON-RPC 方法（主进程白名单同步加了 `mode.set`、`goal.set`）：

```
→ {"method":"mode.set","params":{"mode":"plan"}}
→ {"method":"goal.set","params":{"goal":{"text":"…","criteria":["…","…"]}}}
→ {"method":"goal.set","params":{"goal":null}}          # 清除
```

`live()` / `snapshot()` 新增 `goal` 字段（`null` 或上述结构）；`settings.mode` 原本就在。事件：`mode_changed`、`goal_changed`，工具内勾选发 `goal`。两者都会触发界面整屏刷新。

## 验证

- `tests/test_goal.py` 13 项：状态校验、进度结算、abandon 保持、提示词、`plan` 只读工具集、`goal_update` 工具、`mode.set` 持久化、计划模式拒绝写文件、`goal.set` 往返、目标进入 system prompt、空验收标准被拒。
- `tests/test_goal.py + test_runtime + test_side_chat + test_anthropic + test_config_provider + test_desktop_projects + test_desktop_sessions + test_desktop_rpc`：103 项通过，1 跳过。
- `npm run build --prefix desktop`（tsc + 构建）通过；`npm test --prefix desktop` 15 项通过。
- `desktop/tests/mode-goal-e2e.cjs`（隐藏窗口 + 本地模拟模型，0 次付费调用）：模式芯片切到计划、`goal.set` 建目标、计划模式请求的工具表 14 个且不含 write/edit/shell/delete、目标文本确实进了模型请求、`按此计划执行` 切回编码并发起第二轮（工具表含 write）、刷新后目标与模式都还在、清除目标后 `goal` 变 `null`、渲染进程零报错。
- 同一脚本在打包版（`output/release/desktop/win-unpacked`）与安装版（`G:\Apps\ECA Desktop`）各跑一次，均通过；安装版记录见 `output/playwright/mode-goal/installed.json`。
- 安装：`install-local.ps1` 退出码 0，328 个 payload 文件哈希通过，后端握手 `1.1.0`；`preferences.json` 安装前后 SHA256 相同（未读取内容），未触碰用户项目会话。
- 未验证：真实服务商下计划模式的输出质量、`goal_update` 在长任务里的勾选准确度、macOS/Linux。

证据：`output/playwright/mode-goal/{development,packaged,installed}.json`、`output/playwright/mode-goal/plan-goal.png`、`output/release/desktop/release-1.1.0.json`。
