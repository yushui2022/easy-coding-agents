# 独立 harness 实测

`harness_probe.py` 复用已有合成维护场景和外部验收，真实调用当前 ECA 核心。
默认选择 DeepSeek Flash fast，固定测试命令、无人工修复/提示、独立目录，并保留请求耗时、用量、工具结果和失败记录。

`web_harness_probe.py` 在新目录还原本机玻璃生态页面最初失败的 HTML，再调用真实桌面 RPC 任务路径。
它是该具体任务的重放工具，依赖原项目 `.eca` 中的历史 change 4，不是通用网页生成评测。

凭据输入为 stdin 的一行 JSON（`api_key`、`base_url`、`api_format`），应由可信的本地凭据管理器通过匿名管道提供。
不要把真实凭据放进命令行、源码、报告或重定向到文件。stdout/stderr 应连接有效管道或日志文件。

参数示例（省略私有凭据管道）：

```text
python -B benchmark/harness_probe.py --output G:/Projects/easy-coding-agents/output/harness-probe/NEW-RUN
python -B benchmark/harness_probe.py --output G:/Projects/easy-coding-agents/output/harness-probe/NEW-RETRY --cases shop_batch
python -B benchmark/web_harness_probe.py G:/Projects/easy-coding-agents/output/harness-probe/NEW-WEB
```

输出目录必须是新目录，不会覆盖旧试验。所有缓存/临时文件应指向 G 盘。
网页检查需要本仓库 desktop 的既有 Electron 依赖；使用隐藏的隔离窗口，不控制用户窗口。
网页依赖固定版本 CDN，需要网络，不下载模型或安装新的依赖。

评测须同时报告：原始失败、环境失败、重试、最终外部验收、人工介入、未覆盖行为。
“首次 runtime verification 通过”可能发生在模型已自行运行多次测试之后，不能表述为首稿成功。
费用未配置真实价格时保持未知；取消请求缺失的用量不能当成零。

2026-10-19 的报告见 `output/harness-probe/REPORT-20261019.md`。
本轮发现了迁移成功但旧购买事务回滚失效的漏测；外部契约已升级到 suite 5，原 suite 4 报告保留，复验另存。

0.24.0 又补充迁移中途失败的原子性检查（suite 6）。`desktop_repair_probe.py SOURCE NEW-OUTPUT` 从保留的候选复制 Python 文件，通过真实桌面 RPC 复核原任务；验收脚本在项目外，固定原始测试不变。可选 `--inject-completion` 故意注入一次“提前宣告完成”的初始回答，以稳定触发运行时失败检查；之后的修复全部调用真实 DeepSeek。报告明确标记这次故障注入、真实请求数及各轮结果，不能混算成无辅助首稿成功率。

单独执行外部检查：在候选目录运行 `python -B G:/Projects/easy-coding-agents/benchmark/desktop_repair_probe.py check shop_migration`，无需凭据。`desktop_repair_probe.py` 是当前本机迁移回归的复测工具，不是通用企业基准。
