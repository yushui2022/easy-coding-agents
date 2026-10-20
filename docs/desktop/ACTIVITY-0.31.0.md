# 0.31.0：实时动作与生成速度

状态条使用两行陶土卡片。左侧第一行显示当前动作及工具名，第二行显示操作对象或接收进度；右侧固定显示 tokens/s 和任务总用时。

- 等待服务、推理、回答、生成工具参数、执行工具、工具返回、授权、停止等状态来自真实事件。
- 文件路径、搜索词、命令、MCP 服务与工具名直接可见，无需展开。长内容截断，展开可查看摘要。文件正文和完整参数对象不会塞进状态条。
- 推理阶段只提供收到的字符计数，不展示或编造内部推理内容。工具参数尚未完整返回时明确标注“尚未执行”。
- 主模型委派任务后保留子任务数量；右侧“上一轮”指主模型上一轮生成速度，不冒充子模型速度。

## 速度口径

`eca/activity.py` 为 Chat Completions、Responses 和 Anthropic 共用增量统计。流式阶段按 ASCII 字符 / 4、其他字符 / 1.5 估算 token 数，显示 `≈`。它不是模型专用 tokenizer，不参与费用或预算计算。生成速度是本轮已接收内容的平均速率，不是每秒采样的瞬时速率。

收到服务端输出 token 用量后，用实际计数重新计算，去掉 `≈`。计时窗口为首个到最后一个内容片段，不含请求等待、工具执行及尾部用量包的等待。只有一个片段或窗口不足 250 毫秒时显示 `—`。服务端统计包含不可观测推理时无法可靠校正，也显示 `—`，展开可见原因。

执行工具期间显示“上一轮”，新请求开始后清空旧速度。页面刷新从当前运行快照恢复，不重新发送请求。参数和思考的正文不进入遥测；工具摘要在截断之前先脱敏已知密钥。

## 验证

测试全部使用本地模拟模型和隔离的临时项目，未调用付费 API：

- Python 定向回归：54 项，覆盖计时、估算、真实用量校正、无数据、不可见推理、取消、流节流、协议适配、RPC 脱敏与过期更新。
- 桌面 Node 测试：15 项；TypeScript 与构建检查。
- `activity-design.cjs`：真实组件的深浅主题、360px 窄布局、键盘展开、工具及对象可见性。
- `activity-stream.cjs`：真实 HTTP SSE → Python → Electron → 授权命令执行，验证思考计数、工具准备、操作对象、速度校正、新轮清空、刷新恢复及取消。
- `e2e.cjs`：现有主任务、审批、文件修改、验证、停止、恢复及错误处理流程。

本地命令（PowerShell，仓库根目录；先设置 `TEMP`、`TMP`、`ECA_TEST_TMP` 为 `G:\DevCache\Temp\easy-coding-agents`）：

```powershell
$env:PYTHONPATH = 'tests'
desktop/.venv/Scripts/python.exe -B -m unittest test_activity test_thinking_modes test_desktop_rpc test_anthropic test_v07 test_context_rejection -q
npm.cmd --prefix desktop run build
npm.cmd --prefix desktop test
node desktop/tests/activity-design.cjs
node desktop/tests/activity-stream.cjs
node desktop/tests/e2e.cjs
```

安装包和最终结果：`output/release/desktop/release-0.31.0.json`。测试记录与截图：`output/playwright/activity/`。模拟服务中的速度仅用于功能校验，不代表 DeepSeek 实际性能。干净 Windows 环境验收未进行；预览包未签名。

## 本机安装结果

2026-10-20 已更新到 `G:\Apps\ECA Desktop`，371 个安装文件哈希与打包产物一致，后端握手版本 0.31.0，模型配置文件哈希未改变。安装后使用独立数据目录和本地模拟服务复测：2 次请求、真实授权命令执行、刷新无重放、停止反馈 1 ms、取消完成 59 ms。源码恢复后重新构建，生成的 JavaScript 与此前通过测试的打包产物哈希一致。
