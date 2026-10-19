# 0.25.1 执行记录验收

日期：2026-10-19。设计与边界见 [执行记录说明](EXECUTION-0.25.1.md)。

## 检查记录

- TypeScript 检查和 Electron 前端构建通过。
- 桌面 Node 测试 14 项通过，覆盖模型配置、stdio 握手、分组、分页缺口、重复 ID、结果分类、路径边界、异常保留与 PNG 提示。
- npm CLI 测试 7 项通过；0.25.1 分发包结构与内嵌 Python wheel 一致性检查通过。
- Python 聚焦回归：43 通过、1 跳过；全量回归 355 通过、6 跳过，耗时 356.33 秒。
- 新版执行区在真实隐藏 Electron 的开发入口与打包入口均通过：8 项合成操作形成一组，2 项失败保持可见，3 项较早已返回操作收起；收起后高度 297 个逻辑像素。正文和用户消息保留。
- 键盘 Enter 展开、完整大结果加载、正在查看的记录固定、深浅主题、820×880 窄窗口不横向溢出、重载后错误保留均通过；渲染错误为 0。
- 开发版与打包版完整流程均通过，各 13 次本地模拟模型请求、0 次付费调用，覆盖授权允许与拒绝、停止、恢复、撤销冲突、检查失败后的自动修复和后端异常。打包版移除子进程 PATH 中的 Python/Node/Git，使用内置后端。打包版首窗口 541 ms，重开 468 ms；这不是干净机器或冷磁盘启动测试。

## 长会话响应复测

打包版使用原有 240 条消息合成会话和本地流式模型。空闲输入处理 P95 为 0.7 ms，流式期间 0.9 ms（各 41 个事件）；停止按钮即时反馈 1.1 ms，点击派发至本地任务停止 124.9 ms；未观察到超过 50 ms 的渲染长任务。最近消息快照为 46,057 个序列化字符。完整日志、分页缺口、会话搜索、导航和回到最新交互均通过。

输入测量为事件捕获到 React 离散提交后的微任务，不是物理屏幕延迟；停止响应使用 DOM 直接点击，区别于完整 E2E 包含 Playwright 定位等待的 2,033 ms。结果表明此次采样下仍保持低本地处理开销，不证明所有机器和任务无卡顿，不代表模型响应加速。原始记录：`output/performance/execution-0251.json`。

合成会话中的命令成功记录只用于测试显示；不作为用户生态场景的运行证据。PNG 拒绝来自真实 `read` 工具执行。测试使用独立应用数据和项目，不操作用户窗口或用户密钥。

## 发布物

- Windows x64 NSIS：`output/release/desktop/ECA-Desktop-0.25.1-x64-Setup.exe`
- 体积：139,863,583 字节。
- SHA256：`b90e8d128fcdea0b00ab375b99fc7bb0408351c49a3ed77fce11964fa6f291f0`
- 摘要：安装包同目录 `.exe.sha256`。
- CLI：`output/release/easy-coding-agent-cli-0.25.1.tgz`，152,571 字节。
- CLI SHA256：`c7a643b8447856c35fa185e00754d176baa7473107be91c0cd029514a5bc38e5`
- 界面证据：`output/playwright/execution-ui-report.json`、`execution-compact.png`、`execution-expanded.png`、`execution-dark.png`、`execution-narrow.png`。
- 完整流程报告：`output/playwright/desktop-e2e-report-0.25.1.json`、`desktop-packaged-report-0.25.1.json`。

## 本机覆盖安装

用户退出后已通过 NSIS 更新 `G:\Apps\ECA Desktop`。204 个应用与后端文件的哈希与已测试打包产物一致，启动器哈希一致，独立后端握手返回协议 1、版本 0.25.1。`G:\Data\ECA\Desktop\preferences.json` 更新前后哈希完全一致，保留原模型密钥与连接配置；安装临时解压位于 G 盘。记录：`output/release/desktop/installed-0.25.1.json`。

安装后不重复完整测试：此前已通过打包版完整流程，本次逐文件核对安装内容并实际启动后端。

## 尚未验收

干净 Windows、签名和系统级性能验收仍未完成。本轮不宣称模型生成变快，不增加图片视觉理解，也不发布 npm registry 或 GitHub release。
