# Skills、语义重命名与协作验收（源码新增）

## 可复用 Skills

项目技能放在 `.agents/skills/名称/SKILL.md`，用户技能放在
`~/.ecs/skills/名称/SKILL.md`；可用 `ECS_SKILLS_DIR` 指定用户目录。
项目同名技能优先，跳过符号链接和超过 32 KB 的技能文件。

```markdown
---
description: 检查修改的兼容性和测试覆盖
---
先读取变更及相关测试，列出具体风险；执行检查前遵循正常工具授权。
```

`/skills` 列出技能，`/skill review` 加载，`/skill off` 清除选择。
模型看到名称和描述，可以按任务调用 `skills(name)`；最多激活三个技能。
激活列表随会话保存，内容在下次请求时重新读取。技能不会自动运行脚本、
安装依赖或提高权限；plan/chat、Shell、MCP 和文件审批规则继续生效。
当前支持 SKILL.md 正文及简单的 description 字段，不宣称兼容任意技能生态的
前置工具、附件读取、模板参数或安装格式。外部用户技能引用的附件不会自动加载。

## LSP 语义重命名

配置现有 `[lsp_servers.NAME]` 后，模型可调用：

1. `lsp_rename(server, path, new_name, line, character)` 请求重命名并返回 diff 和 preview_id。
2. `lsp_apply(preview_id)` 检查所有目标文件，展示修改并沿用编辑审批，然后逐文件记录可撤销变更。
3. 应用后请求各文件诊断；pending、unavailable 或 unversioned 不能解释为没有错误，仍应运行测试。

行号从 1 开始，character 是从 0 开始的 UTF-16 位置。引用定位继续使用
`lsp(operation="references", ...)`。plan 模式允许预览但不能应用；Docker
和隔离子 Agent 禁止主机 LSP。只接受已有项目文本文件，拒绝越界 URI、
重叠编辑、未知文档版本、资源创建/删除/移动和注解编辑。

预览前取文件快照，应用前和审批后重新比较；一处冲突会在写入前拒绝整组。
最多 100 个目标文件，快照限 2000 文件/20 MB，单文件 2 MB；保留最新一次预览。
跨文件写入不是文件系统事务：OS 写入失败可能留下部分修改，返回已应用文件，
通过 `/changes` 检查并按文件撤销。程序崩溃、外部并发写入和非版本化服务器
内部索引无法提供原子性保证。没有后台自动回滚。

## 共享请求预算与子任务验收

```toml
[agent]
shared_request_limit = 60
```

默认 0 表示不启用新增限制，仍保留原有 turn/子任务次数限制。
`/budget` 查看额度。主 Agent、串行/并行子 Agent 共用根会话的持久计数，
重试、摘要也计入；恢复会话不重置。达到上限时，在下一次请求发出前阻止。
这是请求次数上限，**不是 token 或金额硬上限**；费用仍由原有 usage/pricing
记录。新版本前的历史请求不补计入这个新计数器。

`delegate` 新增可选 `verify_commands`（1–5 条），仅父子都为 code 模式时可用。
子任务结束后，父 Agent 走正常 Shell 授权执行验收，保留动作记录；零测试、
拒绝、超时和中断不算通过。全部命令成功且源码指纹稳定才标为 passed。
失败会明确交回父 Agent 检查修复，不自动重新委派。验收只证明选定检查的结果，
不能证明原始需求已完全满足。

隔离并行子 Agent 仍不能执行 Shell；应先审查、合并，再在父工作区验收。
父任务取消会停止运行/排队的子任务，等待清理；已经发生的文件或外部副作用
不会自动撤销。需要自动主模型修复时，使用已有 `--worker-first`、
`--verify-command`、`--repair-attempts` 链路，修复同样消耗共享额度。

## 单模型与 Worker-first 对照评测

凭据通过环境变量配置。下面命令会真实调用模型；替换模型名称和端点后运行：

```powershell
python -B -m benchmark.compare_workers --model MAIN_MODEL --base-url MAIN_URL --api-key-env MAIN_API_KEY --worker-model WORKER_MODEL --worker-base-url WORKER_URL --worker-api-key-env WORKER_API_KEY --cases api config user_edits --repeats 3 --verify --repair-attempts 1 --shared-request-limit 60
```

两个方案各自创建独立工作目录，使用相同用例、重复次数、外部验收 oracle
和额度上限，输出原始 report 与 comparison.json。看成功率、耗时、请求数、
token 和已知费用；未知费用不能算零。当前对照不覆盖 compact/resume 用例。
顺序执行、供应商波动和样本规模会影响结果；不能只凭一次成功判断多模型更好。

本轮使用离线固定响应和本地 stdio 协议服务验证机制；未做两个真实模型的
成功率比较，也未宣称多模型优于单模型。源码更新不等于更新全局 ecs 安装包。

2026-10-18 最终全量回归：**322 passed、6 skipped，242.92 秒**。
跳过项为未启用的 Docker/MCP 可选测试。新专项覆盖技能优先级与模式权限、
UTF-16/重叠编辑、跨文件预览与修改日志、审批期间冲突、真实 stdio 交互、
共享额度并发与恢复、重试计数、验收拒绝与取消，以及配对评测调度。
首轮回归暴露空技能目录提示挤占极小上下文，修复后通过最终全量回归。
