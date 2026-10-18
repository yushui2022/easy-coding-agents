# SQLite 维护任务真实基线 — 2026-10-18

使用 DeepSeek `deepseek-flash`、`https://api.deepseek.com/v1`。三个任务各独立运行三次，串行执行；无人工修补、无人工补充需求。模型别名不等于冻结权重版本。

## 结果与契约修正

| 批次 | 套件 | 总验收 | 外部业务断言 | 首次公开验证 | 工作流修复轮次 | 模型请求 | 任务累计耗时 |
|---|---|---:|---:|---:|---:|---:|---:|
| 原契约 | v2 | 1/9 | 7/9 | 9/9 | 0 | 79 | 342.33 秒 |
| 明确契约 | v3 | 9/9 | 9/9 | 9/9 | 0 | 69 | 298.39 秒 |

原批次 8 项修改了原测试文件，违反评测的字节不变条件；检查发现 9 项原有 test_purchase 方法的语法树均保留一致，主要是追加测试。原任务仅说保留测试、添加回归测试，约束不够明确。另有 2 次批量任务采用 body["items"]，外部验收传入列表，而原任务未明确请求体形状。

v3 仅澄清任务说明：现有测试文件字节不变，新增测试使用新的 test_*.py；dispatch(db, "batch", items) 的 body 直接是列表，并明确空列表返回值。外部验收断言未修改，生产运行时未修改。修正后在全新目录重新执行完整九次；原报告不覆盖、不改判。两批不能合并为单一成功率，也不能把差异归因于运行时升级。

## v3 各次结果

| 任务 | 通过 | 秒 | 请求 | 首次公开验证 | 工作流修复轮次 |
|---|---|---:|---:|---|---:|
| shop_idempotency-01 | True | 32.7 | 9 | True | 0 |
| shop_cancel-01 | True | 30.67 | 9 | True | 0 |
| shop_batch-01 | True | 34.97 | 8 | True | 0 |
| shop_idempotency-02 | True | 37.53 | 7 | True | 0 |
| shop_cancel-02 | True | 23.36 | 5 | True | 0 |
| shop_batch-02 | True | 30.55 | 6 | True | 0 |
| shop_idempotency-03 | True | 28.22 | 6 | True | 0 |
| shop_cancel-03 | True | 46.39 | 12 | True | 0 |
| shop_batch-03 | True | 34.0 | 7 | True | 0 |

每次调用 verified_run；首次验证指初始 Agent 任务结束后固定 unittest 命令通过，不表示模型在任务内部没有测试和修正。两批均未触发额外工作流修复，不能用此数据证明真实修复成功率。v3 有一次 shell 操作被白名单拒绝，模型后续自行完成；无人工介入。

## 配置、用量与复现

两批配置相同：每次 Agent 运行最多 24 轮，输出上限 4096 tokens，任务总超时 600 秒，显式验证和最多 1 次工作流修复，单任务各轮共享墙钟预算。默认上下文预算 32768 tokens，备用字符预算 100000；无价格配置。

```powershell
python -B benchmark/agent_eval.py --model deepseek-flash --cases shop_idempotency shop_cancel shop_batch --repeats 3 --verify --repair-attempts 1 --max-turns 24 --timeout 600
```

| 批次 | 未缓存输入 tokens | 缓存读取 tokens | 输出 tokens | 缺失用量请求 | 费用 |
|---|---:|---:|---:|---:|---|
| v2 | 100041 | 291968 | 50587 | 0 | unknown |
| v3 | 97408 | 238336 | 40280 | 0 | unknown |

上述为供应商报告用量；未核实配置价格，不估算账单。耗时为任务累计值，含外部验证，不含全部 fixture 初始化；不是严格速度对照。

## 原始证据

- [v2 原报告](../output/agent-eval/run-20261018T074609Z-17eb0b93/report.md)
- [v3 原报告](../output/agent-eval/run-20261018T075307Z-03c5f376/report.md)
- v2 源码 SHA256：`802f002629b7a4c1c1614b61d451a0f84aed35e4aac2e3bd947fe9a044674b8e`
- v3 源码 SHA256：`e06591be946f048616952135dd2b36ed0de43a71c3ffe32b9ac04e81f59ff1cd`
- 两批均确认运行结束源码指纹未变；各目录保留 manifest.json、report.json、逐项结果、工作目录、source-snapshot.zip 和 environment.json。Git 工作区含未提交升级，不能只用旧 HEAD 复现。输出默认被 Git 忽略，公开文档不依赖原始产物可在线访问。

## 边界与下一步

这是三个合成 Python/SQLite 多模块任务，不是完整前后端、生产大仓库、并发压力或对抗性安全验证。每项三次仅是小样本。宿主执行权限不等于沙箱。未对比 Pi/OpenCode。

本轮项目离线测试 3 passed，未改运行时，因此未重跑全量或重新打包。下一步应增加明确契约的更难任务，例如数据库迁移、已有用户改动、跨模块依赖，以及真实触发验证失败的场景；保留首次失败后再决定改运行时哪部分。
