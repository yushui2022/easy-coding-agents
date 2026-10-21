# 工作模式与目标（1.1.0）

桌面端原来只有「逐次确认 / 自动编辑 / 完全访问」三档审批，没有工作模式。后端其实早就有 `mode=code|plan|chat`（`eca/tools.py: allowed()`），CLI 用 Shift+Tab 切换，但桌面端从未暴露，也没有任何目标跟踪。

本轮把两件事补齐：

| 能力 | 位置 | 说明 |
|---|---|---|
| 工作模式 | `eca/desktop_rpc.py` `mode.set`、`desktop/src/renderer/ModeMenu.tsx` | 编码 / 计划 / 对话，按会话保存 |
| 目标与验收标准 | `eca/goal.py`、`goal_update` 工具、`desktop/src/renderer/GoalBar.tsx` | 用户写目标，模型逐条标记 |

## 工作模式

| 模式 | 工具集 | 用途 |
|---|---|---|
| 编码 `code` | 全部工具 | 默认。可以改文件、跑命令、跑测试 |
| 计划 `plan` | 只读：read/glob/grep/code_search/repo_map/code_relations/skills/lsp_rename/web_*/todo/ask/delegate/lsp/goal_update | 先调研再给计划，一个文件都不改 |
| 对话 `chat` | 无工具 | 只按已有上下文回答 |

约束：

- 模式**不是权限**。切到编码模式不会自动放行写文件，审批档位照旧生效；切到计划模式也不会放宽任何检查，只是把写类工具从工具表里去掉。
- 工具表在每次请求时按 `settings.mode` 生成，模式切换在下一轮请求生效。
- 运行中不能切换（`mode.set` 返回「请先停止或等待当前任务结束」）。正在跑的任务不会因为切模式而拿到另一套工具。
- 模式写进会话状态 `state['mode']`，切走再切回、重开项目都保留；新会话仍用项目默认模式。
- 计划模式不跑验证/自动修复链（`workflow.py` 只在 `code` 模式跑），也不允许 `write/edit/delete/shell`。被拒绝时工具层返回 `Denied: <tool> is unavailable in plan mode.`

「按此计划执行」：计划模式一轮跑完后，输入区下方出现按钮。点击先 `mode.set code`，再把「按上面的计划执行」作为新指令发送，计划内容留在会话上下文里。

## 目标与验收标准

- 用户在输入区「目标」按钮里写：目标一句话 + 验收标准（每行一条，最多 20 条）。
- 存在会话状态 `state['goal']`：`{text, criteria:[{text,done}], status}`，`status` 为 `active|done|abandoned`。
- 目标存在时，`agent.system_prompt()` 追加一段：目标 + 编号后的验收标准 + 「做到全部满足再停；用 goal_update 记录真实进度；不得为了看起来完成而勾选」。
- 模型只能通过 `goal_update(updates=[{index,done}], status?)` 改勾选状态，1-based 编号与提示词里的编号一致。越界索引、非布尔 done、多余字段都会被拒绝。
- 全部勾选后 `status` 自动变 `done`，这段提示词随即停止注入（避免达成后继续绑着模型）；手动 `abandoned` 不会被自动改回。
- 界面：输入区上方一条目标条，显示 `目标文本 · 2/4`，展开看逐条标准，可编辑或清除。`done` 时变绿色。

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
