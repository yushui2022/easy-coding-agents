# 0.34.0 附件与按需工作区

主对话、侧边聊天共用附件输入：点击加号选择文件、拖入文件、粘贴截图。发送前显示图片缩略图、文件名和大小，可单独移除。只有附件也可以发送。草稿按项目、会话和主/侧聊隔离，保存在应用 IndexedDB，刷新后恢复；发送成功后清除草稿。发送记录显示附件名称及大小。

首批支持 PNG、JPEG、WebP 图片，以及 UTF-8 代码和文本文件。每次最多 6 个附件；单张图片 4 MB、单份文本 256 KB、合计 12 MB。PDF、Office、压缩包等二进制文档尚不支持，界面会说明。该限制针对附件上传，并非模型连续输出限制。

图片需要当前模型与接入服务支持视觉输入。应用不会仅凭模型名称宣称视觉能力；接口拒绝图片时明确报错，保留已经提交的会话记录。可以切换到支持图片的模型继续，或新建不含图片的会话。未接入 OCR，不以图片名称或文本替代实际图片。

## 数据与协议

- `task.start`、`sidechat.send` 增加可选 `attachments` 数组：`{name,mime,data}`，其中 data 是用户所选文件的 Base64。后端重复验证数量、大小、类型、编码与图片签名。
- 文件选择依赖浏览器 File API，不给渲染器任意读取本机路径的接口。
- 图片按 SHA-256 保存到当前项目 `.eca/attachments/`，历史仅存描述符；请求前验证内容哈希并加载。文本快照保存在会话中，计入现有上下文预算，不静默截断。
- OpenAI Chat、Responses、Anthropic 三种适配器分别构造原生图片内容块。服务端的模型能力仍由实际接口决定。
- 常规快照只返回附件名称、类型、大小和标识，避免轮询反复传输图片或全文。模型推理时才读取图片数据。
- 附件原文件不被修改；项目 `.eca` 备份应包含 attachments 文件夹。附件快照属于会话数据，不是可随意清理的缓存。
- CSP 只增加本地 `data:`、`blob:` 图片来源；Markdown 继续禁用图片与原始 HTML，不自动加载远程内容。

图片接口格式参考：
[OpenAI Images and vision](https://developers.openai.com/api/docs/guides/images-vision)、
[Anthropic Vision](https://platform.claude.com/docs/en/build-with-claude/vision)。

## 工作区

右侧默认关闭；打开后可选择浏览器、终端或侧聊，子 Agent 仍通过主对话的任务入口查看。审查按需打开并可关闭，内部仅保留文件修改、检查结果两个标签，任务活动和用量改为折叠详情。当前窗口重载保留用户的展开状态和工作区标签。

## 验证

以下测试均使用独立 G 盘临时项目和本地模拟接口，不使用用户 API：

```powershell
$env:TEMP='G:\DevCache\Temp\easy-coding-agents'
$env:TMP=$env:TEMP
$env:ECA_TEST_TMP=$env:TEMP
$env:PYTHONUTF8='1'
$env:PYTHONPATH='tests'
desktop\.venv\Scripts\python.exe -B -m unittest test_attachments test_runtime test_side_chat test_anthropic test_config_provider test_desktop_projects
npm.cmd run build --prefix desktop
npm.cmd test --prefix desktop
node desktop/tests/attachments-e2e.cjs
```

打包版设置 `ECA_TEST_EXE` 为实际 exe 路径，`ECA_TEST_MODE=packaged`。安装版使用原安装路径及 `ECA_TEST_MODE=installed`。报告保存在 `output/playwright/attachments`。干净 Windows、真实服务商视觉能力以及任意第三方代理兼容性未通过本地模拟测试验收。

本轮结果：Python 定向回归 51 项（1 跳过）、Node 15 项、类型检查通过；原有桌面完整流程 13 次本地请求、工作区 4 次、最终打包版附件 3 次请求全部通过，包含深浅主题与窄窗口。2026-10-20 已更新到 `G:\Apps\ECA Desktop`，371 个安装文件哈希与后端 0.34.0 握手通过；安装后附件流程 3 次本地请求通过，无 renderer 错误。模型配置文件安装前后 SHA256 一致。安装证据见 `output/release/desktop/release-0.34.0.json` 和 `output/playwright/attachments/installed.json`。
