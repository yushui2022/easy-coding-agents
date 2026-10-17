# v0.8 验证记录

日期：2026-10-17。环境：Windows、Python 3.11。测试没有调用付费模型。

## 已验证的变化

- 有界并发队列、单个子任务初始化失败时其余任务继续、排队/运行取消、源码准备失败保留任务状态。
- `Store.peek` 不修改 live session，运行中的子任务不能被合并检查误标记为 interrupted。
- LSP 真实本地 stdio 进程：跨查询复用、didChange 同步、旧版本诊断丢弃、push/pull 区分、缺失诊断返回 pending、无版本报告显式标记、配置变化重启、取消关闭与再次启动。
- 模型配置切换、独立密钥变量与模型参数复位、创建新会话后仍保留选择、CLI 恢复、无密钥/无配置的离线改动审阅。
- Responses 跨模型/接口不回传旧 encrypted reasoning，摘要请求排除 opaque replay 数据但历史原文保留。
- MCP 真实本地 stdio/HTTP fixture：死连接状态、新的明确操作重新连接、取消排队请求不影响运行中的请求。
- 既有用量账本、恢复、文件撤销、模式权限、记忆、CLI 及模型协议测试。

## 执行记录

- 全量：151 passed, 1 skipped（242.96 秒）。全量收集后最后补充的摘要 replay 数据修正，另由下述 11 项专项验证；没有将不同批次计数混为一次全量。

- 原扩展回归：29 passed（69.22 秒）。
- 新增可靠性与 MCP 组：19 passed（81.70 秒）。
- 摘要数据修正后的 v0.8 专项：11 passed（35.48 秒）。
- `python -B -m eca --help` 正常，包含 `--model-profile`。
- Python 运行时 AST 解析与 `git diff --check` 通过；改动文件中未检测到长 `sk-` 凭据模式（模式扫描不等于全面秘密审计）。

全量命令：

```powershell
$env:PYTHONUTF8='1'
$env:ECA_TEST_TMP='G:\DevCache\Temp\easy-coding-agents\tests'
$env:TEMP='G:\DevCache\Temp\easy-coding-agents'
$env:TMP=$env:TEMP
python -B -m pytest -q -p no:cacheprovider --basetemp G:\DevCache\Temp\easy-coding-agents\pytest-v080-final
```

## 范围限制

模型测试使用 FakeProvider、MockTransport 或本地 fixture，不能据此证明真实付费模型跨接口恢复与长任务表现。LSP 使用最小协议进程；本机 PATH 未发现 pyright-langserver/pylsp/clangd，本轮没有安装语言服务器或做真实大型项目索引评测。

未在 Linux/macOS 执行，未实现或验证 OS 沙箱、Git worktree 合并、OAuth、完整 MCP 扩展、LSP 自动重命名。GitHub Actions 仍是文档中的模板，未自动启用。

设计来源与配置见 [v0.8 升级说明](UPGRADE-v0.8.md)。
