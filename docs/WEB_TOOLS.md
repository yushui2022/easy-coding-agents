# 网页读取、网页搜索与浏览器接入

源码提供 `web_fetch` 和 `web_search`。只配置原来的模型 API 仍能正常编码，网页读取无需额外密钥；搜索是可选配置。

本次为源码升级，尚未重打包或替换全局安装的 `ecs`。开发环境可在项目目录运行 `python -m eca` 使用当前源码。

## 本轮验证

- 全量回归 302 passed、6 skipped（191.25 秒）；全量开始后补充的取消/Agent 调用链路和压缩响应检查，由最终网页专项 13 passed 覆盖。
- 直接联网读取 `https://example.com` 和 Python 官方 asyncio 文档成功，来源和正文截断标记正确；记录在 `output/web-validation/live-fetch.json`。
- 搜索测试使用模拟服务响应，覆盖请求参数、密钥头、授权拒绝/配置缺失提示及错误正文省略。没有实际搜索服务密钥，因此未做真实搜索验收。
- 浏览器为接入说明，没有真实浏览器操作验收；六项可选 Docker/MCP 测试仍跳过。

## 网页读取

示例请求：“读取 https://docs.python.org/3/library/asyncio.html，根据官方说明解释任务取消。”

工具每个 URL 都请求授权，重定向也重新授权；只接受公共 HTTPS 地址的 443 端口，不接受 URL 内嵌用户名密码。DNS 检查后连接固定 IP，TLS 仍验证原域名。最多三次重定向、45 秒总时限、1 MiB 响应；请求 identity 编码并拒绝压缩响应，避免解压时突破内存限制。正文默认最多 12,000 字符，可请求 500–20,000。拒绝超大响应，不把截断下载伪装成完整页面。

支持 HTML、纯文本、Markdown 和 JSON。HTML 移除 script/style 等内容并转为文本，保留来源 URL 和正文截断标记。它不是浏览器，不执行 JavaScript，不登录、不自动携带 Cookies，不读取 PDF 或截图。当前直连，不使用环境代理。

网页和搜索结果统一标记为不可信参考数据。提示词标记不等于能防御所有提示注入，外部操作仍执行原有权限检查。Docker 离线模式、隔离子 Agent 禁用这两个主机联网工具。

## 可选搜索

在项目 `eca.toml` 增加独立的顶层配置：

```toml
[web]
search_provider = "brave"
search_api_key_env = "BRAVE_SEARCH_API_KEY"
```

将 Brave Search API 密钥放入同名进程环境变量，或项目已忽略的 `.env`；不要写入 TOML。模型 API 密钥不能替代搜索密钥。

用户示例：“搜索 Python asyncio 官方文档，再读取相关链接。”每次搜索先授权，查询会发送到 Brave，可能产生搜索服务费用；该费用目前不纳入模型 token 费用账本。返回标题、链接和摘要，默认五条，最多十条。HTTP 错误不返回服务商响应正文，不自动重试；密钥缺失会明确说明。

实现依据：[Brave 官方接口](https://api-dashboard.search.brave.com/app/documentation/web-search/get-started)。本轮没有可用的搜索服务凭据，搜索接口通过模拟响应验证，不能声称已通过真实付费搜索验收。

## 浏览器：Playwright MCP 配置示例

复用现有 `mcp_list` / `mcp_call` 接口接入 [微软 Playwright MCP](https://github.com/microsoft/playwright-mcp)。这是可选配置示例，本轮没有安装或执行真实浏览器，不自动修改用户配置。

Windows 示例使用已安装的 Edge，依赖和临时文件放 G 盘：

```powershell
$env:npm_config_cache = 'G:\DevCache\npm'
$env:ECA_BROWSER_TEMP = 'G:\DevCache\Temp\easy-coding-agents\browser'
New-Item -ItemType Directory -Force $env:ECA_BROWSER_TEMP
npm install --prefix G:\DevTools\eca-browser @playwright/mcp
```

安装后记录实际版本，以便复现。ECA 的 Python 运行环境须安装可选 MCP 依赖，参见项目已有 MCP 安装说明。添加：

```toml
[mcp_servers.browser]
transport = "stdio"
command = "node"
args = ["G:/DevTools/eca-browser/node_modules/@playwright/mcp/cli.js", "--browser", "msedge", "--isolated", "--headless", "--output-dir", "G:/DevCache/Temp/easy-coding-agents/browser"]
env = { TEMP = "ECA_BROWSER_TEMP", TMP = "ECA_BROWSER_TEMP" }
timeout = 60
```

`env` 是目标变量到现有环境变量名称的映射，不是直接填写目录值。启动 ECS 的终端须设置 `ECA_BROWSER_TEMP`。Linux/macOS 需调整浏览器、路径及临时目录。

启动自己的开发服务后，可以要求：“列出 browser MCP 工具，打开 localhost 页面，检查页面文本与控制台错误。”每次 MCP 操作仍需授权。`--isolated` 使用临时浏览器会话，不继承日常浏览器登录状态，也不是 OS 安全沙箱。

当前 MCP 桥接保留文本和结构化结果，省略图片内容。因此可支持基于页面结构的操作接入，但不能宣称模型已经能直接看截图或完成视觉对比。本轮也未新增自动启动开发服务器的后台进程管理。
