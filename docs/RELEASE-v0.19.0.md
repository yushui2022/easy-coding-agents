# 0.19.0 安装与配置验收（2026-10-18）

本版将会话恢复、上下文恢复、Docker 实测、大仓库定位与新增配置/诊断功能一起打包。npm 包仍 `private: true`，未执行 npm publish；本地安装无需 npm 账号。

## 使用

```powershell
npm install -g --prefix G:\DevTools\npm .\easy-coding-agent-cli-0.19.0.tgz --cache G:\DevCache\npm
G:\DevTools\npm\ecs.cmd --setup
G:\DevTools\npm\ecs.cmd --configure
G:\DevTools\npm\ecs.cmd --doctor
# 明确发送一次小请求，可能产生 API 费用：
G:\DevTools\npm\ecs.cmd --doctor --check-api
```

请在目标项目目录执行配置向导。已有 `eca.toml` 保留，需手工编辑；已有 `.env` 不覆盖。向导可仅引用环境变量，也可在新 `.env` 中明文保存隐藏输入的密钥，保存前有提示。向导不会测试连接。默认单 API 行为不变。

## 产物

- `output/release/easy-coding-agent-cli-0.19.0.tgz`
- tarball SHA256：`fc0f12c144fc8957089fc79753efea87a2341b378ecd40b5513df79d7640db00`
- 内置 wheel SHA256：`dca61fe7c58b8e2aba5eebb0da8caccf702ac285db69c07e3932bdfd264159ec`
- 30 个 ECA Python 模块与打包时源码逐字节一致。npm 包仅含白名单文件，不包含项目凭据或会话。

## 验证结果

- Python 全量：280 passed、6 skipped，194.30 秒。Docker/MCP 可选验收本轮未启用。
- npm 启动器：7 passed。
- 配置与诊断专项：15 passed；SOCKS 修复后再次通过。
- Windows 上真实安装 `.tgz` 到独立 G 盘 prefix，新建独立 Python 环境。`ecs.cmd --version` 和 `--setup` 成功。
- 使用安装包运行 `scripts/smoke_installed_cli.py`：配置向导、离线 doctor、显式 API doctor、流式任务、会话列表、工作目录同名模块隔离全部通过。HTTP fixture 接收 1 个非流式探针和 1 个流式任务，无付费 API 请求。见 [机器可读结果](INSTALLED-SMOKE-v0.19.0.json)。
- 本机旧 ModelScope 配置的真实 API 探针返回 HTTP 401；诊断正确分类且未重试。这不是鉴权成功，也没有证明当前凭据可用。

首次独立安装在继承 SOCKS 代理配置时失败：缺少 socksio，HTTP 客户端无法初始化。已将 `httpx[socks]` 加入正式依赖，重新构建、安装并通过完整安装包验收。没有通过删除用户的代理配置掩盖该问题；本地 fixture 使用 NO_PROXY 避免 localhost 经代理转发。

## 边界

网络诊断不读取项目源码、不执行工具、不创建会话、不重试、不跟随重定向；请求输出上限 16 token，25 秒总超时，64 KiB 响应上限。生成内容和供应商错误原文不显示。用量若返回则展示，费用仍未知，不计入任务会话账本。成功仅表示收到对应协议的响应，不证明工具调用或流式能力。具体供应商可能不接受此小预算或参数，需按提示核对。

安装验收仅覆盖本机 Windows；其他平台仍待验收。没有发布 npm registry 或 GitHub Release，也未替换用户已有的全局 ecs 安装。
