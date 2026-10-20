# 0.29.0 子 Agent 界面验收

2026-10-20，在本机 Windows x64 完成。模型请求全部发往本地 HTTP 测试服务，付费 API 调用为 0。使用独立临时项目和隐藏 Electron 窗口，没有操作用户现有项目。

## 已通过

- 子任务与桌面协议测试共 25 项；另有真实 HTTP CLI 测试 2 项、桌面 Node 测试 14 项；TypeScript 检查与构建通过。
- 串行委派、三个并行子任务与排队、实时回答、实际文件写入、拒绝授权、子任务错误和主任务停止传播。
- 主对话入口高度不超过 40 CSS px；显示任务名、陶土标志与状态。没有重复的委派执行提示，也没有保存后的回答再次出现在流式区域。
- 点击入口打开右侧内容，不切换主会话；返回主对话或关闭标签不停止子任务；重新加载和重新打开项目不重放模型请求。
- 六种陶土图片均正常加载；深浅主题、窄窗口和 Markdown 表格在流式输出及完成后均正常显示。
- 开发、打包和真实安装目录分别通过子任务全流程，每次测试 20 个本地模型请求，渲染异常为 0。
- 打包版的侧聊、浏览器、真实 PowerShell 终端、资源清理、弹层与窄窗口回归通过。该次联合测试输入处理 P95 约 0.10 ms，侧聊取消确认 11 ms，没有检测到长任务。这是本机测试场景数据，不代表所有真实模型和大型会话的响应速度。
- NSIS 更新至 `G:\Apps\ECA Desktop`。371 个程序文件与构建产物哈希一致；后端握手版本为 0.29.0；原模型配置文件 SHA-256 保持不变。安装后再次通过上述子任务全流程。

## 产物

- 安装包：`output/release/desktop/ECA-Desktop-0.29.0-x64-Setup.exe`，161,426,773 字节。
- SHA-256：`7ce87ed8b068b443b600a2d1735df0919fac1f6e1ab2a367166f8b5002a55078`。
- 子任务报告：`output/playwright/subagents/report-development.json`、`report-packaged.json`、`report-installed.json`。
- 截图：同目录的 `running-light.png`、`running-dark.png`、`returned-light.png`、`compact.png`。
- 工作区报告：`output/playwright/workspace-packaged-report-0.29.0.json`。
- 安装日志与发布元数据：`output/release/desktop/install-0.29.0.log`、`release-0.29.0.json`。

## 未覆盖

安装包仍为未签名预览版；尚未在干净 Windows 虚拟机上验证。这轮使用确定性模拟模型验证通信和操作流程，不评价真实大模型的任务分解或编码质量。子任务“已返回”也不代表它的修改已经由主 Agent 验收、合并。
