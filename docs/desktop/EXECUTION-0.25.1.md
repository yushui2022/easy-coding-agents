# 0.25.1 执行记录

2026-10-19。目标是让用户读清“做了哪些操作、哪些未成功、哪里能查证据”，同时保持长会话的按需加载。

## 参考与取舍

参考 [Pi Web Desktop](https://github.com/isWittHere/pi-web-desktop) 的多步骤过程分组，以及 [PI-Desktop](https://github.com/vastsa/PI-Desktop) 的项目、会话、审查工作区。它们是不同的 Pi 社区桌面项目，不称为一个统一的官方桌面客户端。本次借鉴信息层次与逐层展开，不复制其代码、不引入其运行时或插件体系。

- `transcript-model.ts` 按消息顺序构造展示节点：连续工具调用合并，正文、用户输入及历史缺口断开。会话原始消息和 RPC 不变。
- 每组保留最后三项，以及所有失败、拒绝、中断、无结果和正在查看的操作。其余已返回步骤折叠，可在原位置展开。不会删除工具证据。
- 文件仅在明确属于当前项目时缩短为相对路径；项目外路径和含 `..` 的路径保留。原路径可悬停查看，完整参数保留。
- 超过 160 字符的脚本显示行数和字符数，展开显示原始命令；不从脚本文本猜测执行目的。完整日志按需加载，关闭不挂载大日志 DOM。消息指纹改变时失效已加载内容，新结果不被旧参数快照遮挡。
- 退出码 0 表示该命令完成；普通工具仅表示“已返回”，均不替代右侧任务验证。无结果不冒充成功，停止记录不冒充执行失败。

## 图片读取问题

此前 `read` 直接以 UTF-8 解码 PNG，产生解码错误。现在工具说明和实际执行都明确其只读取文本；图片输入立即返回能力边界，普通非 UTF-8 文件返回可理解的错误。旧记录中 PNG 解码失败也会显示中文解释。

此改动没有增加视觉模型接入、图片查看或浏览器截图验证。不能声称 Agent 已经看过截图，也不能将 Base64 文本当作视觉证据。对于文本形式的 SVG 等文件，仍可读源码，但不代表看过渲染效果。

## 验证方式

所有测试项目、临时文件和模型模拟服务均在 G 盘；不使用 Computer Use，不操作用户当前窗口，不调用付费模型。

```powershell
$env:TEMP = $env:TMP = $env:ECA_TEST_TMP = 'G:\DevCache\Temp\easy-coding-agents'
python -B -m pytest -q -p no:cacheprovider
npm test
cd desktop
npm run build
npm test
node tests/execution-ui.cjs
node tests/e2e.cjs
$env:ECA_TEST_WORKBENCH = '1'
node tests/performance.cjs execution-0251
```

`execution-ui.cjs` 使用独立隐藏 Electron 和合成会话，覆盖 8 次工具调用、真实文本工具拒绝 PNG、失败保留、相对路径、键盘展开、完整日志、已打开记录固定、深浅主题、窄屏与重载。截图是界面测试样本，不是用户生态场景的验证结果。

打包后测试可设置 `ECA_TEST_EXE` 为 `output/release/desktop/win-unpacked/ECA Desktop.exe`。完整 E2E 覆盖模型配置、文件修改、授权、停止、恢复、撤销冲突和检查失败修复。最终测试与打包结果见同目录 `VERIFICATION-0.25.1.md`。
