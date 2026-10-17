# StockFlow 较大项目验收

让 ECA + DeepSeek 从需求契约构建一个多模块 FastAPI / SQLite 库存订单服务。
这不是将已有答案拷贝进测试目录；业务实现、项目自身测试和 README 由被测 Agent 编写。
外部验收脚本在另一个目录，模型没有获得修改验收脚本的文件权限。

## 内容

- `stockflow_requirements.md`：冻结的接口和业务要求。
- `stockflow_contract.py`：外部 HTTP 契约测试，覆盖权限、严格类型、并发库存、幂等、回滚、取消、审计、CSV 和跨实例持久化。
- `stockflow_run.py`：真实模型构建、最多三轮外部反馈修复、报告及原会话续跑。

项目依赖需预先安装：FastAPI、Pydantic v2、httpx、pytest、uvicorn，以及 Git。
默认项目目录 `G:\Projects\eca-stockflow`；首次运行要求目录不存在，避免覆盖已有项目。

```powershell
python -B benchmark/stockflow_run.py --project G:\Projects\eca-stockflow
# 中断后从原有文件及会话继续：
python -B benchmark/stockflow_run.py --project G:\Projects\eca-stockflow --resume
```

密钥从 `DEEPSEEK_API_KEY` 或隐藏输入提示读取，不写入源码。费用默认未知；使用
`--rates '{"input":"0.15","output":"0.6","cache_read":"0.003","currency":"USD"}'`
可明确传入核实过的每百万 Token 价格快照。示例仅对应 2026-10-17 的 Flash 非高峰价，
不能作为长期价格配置。[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)

本项目验收默认 `--context-chars 400000`，单位是字符，不是 Token；原 100000 字符
配置在此次较长任务中出现频繁压缩、重复读取。这个设置只属于较大项目验收，不改变 ECA
通用默认值。实际轮数、压缩和用量保存在 `.eca` 请求账本里。

报告位于 ECA 的 `output/stockflow/<UTC时间>/`。每阶段保存外部和自身测试 JUnit XML，
检查外部至少 30 项、自身至少 20 项且没有失败、错误或跳过；另检查至少八个有内容的业务模块、
文档/依赖配置和规则文件未被修改。满足数量门槛不代表测试全面，仍需看用例覆盖。

## 执行边界

只自动批准固定的项目 pytest 命令，文件操作采用 accept-edits。没有提供操作系统沙箱；
测试代码仍以当前用户权限运行。本场景应只运行在专用目录中，不应混入私人凭据或业务数据。
它验证工程集成与编码流程，不模拟生产网络、备份、限流、OAuth、支付或高可用部署。

外部测试使用 [FastAPI TestClient](https://fastapi.tiangolo.com/tutorial/testing/)；并发要求
围绕 [SQLite 事务](https://www.sqlite.org/lang_transaction.html) 的原子性和写锁行为检查。
仅能证明本次用例中的结果，不能外推为任何并发规模下都正确。
