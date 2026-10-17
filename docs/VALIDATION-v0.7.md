# v0.7 验证记录

日期：2026-10-17。环境：Windows、Python 3.11。所有模型请求均使用本地 fixture / MockTransport；没有调用付费模型 API。

## 测试范围

- 并发屏障验证两个子任务真正重叠运行，快照包含未提交代码、不复制 `.env`；父文件在显式合并前不变。
- 合并冲突拒绝、导入修改撤销、子会话恢复保持原工作区、禁止递归与外部进程、父取消传播和状态持久化。
- Git 忽略规则、当前工作树脏文件内容；当前仓库快照实测 117 个文件、约 1.3 MB（文档后续变动会改变该数字）。
- 并行写入审批串行化，审批前确实展示对应 diff。
- MCP 真实 stdio/本地 HTTP fixture、持久连接复用/关闭、资源/模板/提示词操作；保留 schema、拒绝、超时、取消与凭据遮盖回归。
- LSP 真实 Content-Length stdio 帧、initialize/didOpen/query/shutdown/exit、UTF-16 位置、拒绝主动 applyEdit、拒绝启动、服务粒度的一次性授权。
- Responses reasoning 项与工具 ID 配对、未完成响应拒绝；OpenAI SDK + httpx MockTransport 的 SSE 请求/响应与账本费用核对。
- 原有恢复、修改日志、权限、记忆、Chat Completions/Anthropic、CLI 集成测试。

## 已执行结果

- 收尾全量：138 passed, 1 skipped（238.51 秒）。该次收集后补充的并行审批修正另以专项组验证，未将两次计数冒充同一次全量结果。
- 首轮全量：135 passed, 1 skipped（227.39 秒）。
- SDK/授权补充后的扩展组：15 passed（71.22 秒）。
- 最终并行审批修正后的 v0.7 专项：10 passed（31.53 秒）。
- `git diff --check` 通过；运行时 Python 文件全部通过 AST 解析。

全量命令：

```powershell
$env:PYTHONUTF8='1'
$env:ECA_TEST_TMP='G:\DevCache\Temp\easy-coding-agents\tests'
$env:TEMP='G:\DevCache\Temp\easy-coding-agents'
$env:TMP=$env:TEMP
python -B -m pytest -q -p no:cacheprovider --basetemp G:\DevCache\Temp\easy-coding-agents\pytest-v070-final
```

## 不能从这些测试推断的能力

没有真实付费 Responses 模型评测、真实大型项目语言服务器评测、Linux/macOS 执行验证或 OS 沙箱逃逸测试。LSP 测试使用最小协议 fixture；特定服务器 capability、索引性能和 pull diagnostics 支持仍需集成验证。没有 OAuth、Git worktree、自动冲突解决或完整 MCP 扩展支持。

GitHub Actions 仍是 `docs/ci-workflow.yml` 模板，本轮没有启用自动 CI。
