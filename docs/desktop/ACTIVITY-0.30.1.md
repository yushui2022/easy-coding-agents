# 0.30.1 陶土执行状态

把输入框上方的“正在执行工具 · grep / 进度与已完成修改会保留”改成紧凑的单行状态。保留真实运行阶段、累计用时、停止反馈与可展开详情。

## 交互

- 常见工具使用动作说明，例如 `grep` 为“正在搜索代码”、`shell` 为“正在运行命令”。
- 点击右侧箭头展开当前工具及详情。参数生成阶段明确写“工具尚未执行”，思考和参数字符数来自现有运行事件。
- 点击停止后立即显示“正在停止并清理”，仍由原有取消逻辑完成清理。
- 子 Agent 已有运行入口时不重复显示状态条；准备委派时显示“正在安排子任务”。
- 计时不放入无障碍实时播报区，避免每秒重复播报。详情支持键盘操作，深浅主题及窄布局共用设计令牌。

## 素材与实现

- `desktop/src/renderer/RunActivity.tsx` / `run-activity.css`：真实状态组件，取代主入口中的旧 Activity。
- `desktop/src/renderer/assets/activity/clay-work-loop.png`：内置 `image_gen` 生成的陶土圆环和白陶珠，透明 RGBA PNG，1254 × 1254。原始 alpha 保留，组件以 32 CSS px 显示。
- 素材说明和完整最终提示词在同目录 [README](../../desktop/src/renderer/assets/activity/README.md)。文案、计时、展开按钮均由代码渲染。

## 验证入口

```powershell
$env:TEMP = 'G:\DevCache\Temp\easy-coding-agents'
$env:TMP = $env:TEMP
npm --prefix desktop run build
npm --prefix desktop test
node desktop/tests/activity-design.cjs
```

视觉检查输出在 `output/playwright/activity`，覆盖图片加载、折叠高度、详情、计数、深浅主题、360 px 窗口、委派去重、停止和减少动态效果设置。阶段由独立组件测试提供，不将这些截图当作真实工具调用证据。

`desktop/tests/e2e.cjs` 另外验证真实 Python 后端、本地模型服务和完整桌面流程，并在等待实际 HTTP 响应时检查此状态条及取消能力。截图为 `output/playwright/desktop-activity-waiting.png`。

仍为未签名 Windows 预览版，干净 Windows 环境验收另行记录。

## 本次结果（2026-10-20）

- TypeScript 与构建通过，15 项桌面测试通过。
- 组件视觉及交互检查通过；开发版完整流程完成 13 次本地模型请求，无渲染器错误。
- 打包版和安装版均通过 `activity-smoke.cjs`：图片解码、真实 HTTP 等待反馈、键盘展开、取消和刷新不重放。安装版取消检查耗时 25 ms，仅为此本地模拟等待场景的测量值。
- 已安装至 `G:\Apps\ECA Desktop`，371 个程序文件与构建产物一致，后端版本为 `0.30.1`。安装与测试前后用户模型配置文件哈希一致。
- 测试未调用付费 API，用户项目及运行中的窗口未作为测试对象。

安装包 `output/release/desktop/ECA-Desktop-0.30.1-x64-Setup.exe`，162,991,924 字节。

SHA256：`af6ae625a9cdba2deaf24150aee2f1504a744ef68ba16d7395bb8ab8a8039cd5`。

发布记录：`output/release/desktop/release-0.30.1.json`。
