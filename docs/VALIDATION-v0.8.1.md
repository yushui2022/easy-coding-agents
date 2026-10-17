# v0.8.1 验证记录

环境：Windows、Python 3.11；日期：2026-10-17。全部测试使用离线或本地协议 fixture，没有调用付费模型。

## 本轮覆盖

- 单文件删除、差异展示、接受与撤销；BOM 和 CRLF 原样恢复。
- 计划模式、拒绝审批、受保护路径、目录和二进制文件限制。
- 审批期间修改文件时拒绝删除；用户重建文件时拒绝撤销覆盖。
- 删除空文件的展示；删除完成但状态未提交时的 prepared 恢复。
- 数据库记录失败时不删除；文件占用导致 unlink 失败时保留记录并恢复状态。
- 作用域规则先于删除；隔离子任务删除清单、父目录冲突检查、合并与撤销。
- 不将任意缺失的子目录文件推断为可合并的删除。

## 执行记录

- 初轮删除及 v0.7 回归：16 passed。
- 后增失败恢复测试的 mock 调用错误已修正；修正后删除专项：8 passed，13.52 秒。
- 最终全量回归：160 passed, 1 skipped（171.55 秒），最终运行时代码与修正后的测试全部纳入本次运行。
- `git diff --check`、运行时 AST 解析与改动文件凭据模式检查通过。
- wheel 构建成功，全部 21 个运行时 Python 文件与工作目录逐字节一致。

最终全量命令：

```powershell
$env:PYTHONUTF8='1'
$env:ECA_TEST_TMP='G:\DevCache\Temp\easy-coding-agents\tests'
$env:TEMP='G:\DevCache\Temp\easy-coding-agents'
$env:TMP=$env:TEMP
python -B -m pytest -q -p no:cacheprovider --basetemp G:\DevCache\Temp\easy-coding-agents\pytest-v081-final
```

安装包：`output/release/easy_coding_agent-0.8.1-py3-none-any.whl`，81482 字节。SHA256：`86bcebea4c2ce374e0b36f726f71ba4fdf05e4fef729208a154b595c2e45bb2b`。

本轮未在 Linux/macOS 测试；未做真实模型、大型语言服务器或操作系统沙箱验证。删除撤销仅恢复文件内容，多文件合并不具有事务原子性。既有协议验证范围见 [v0.8 记录](VALIDATION-v0.8.md)。
