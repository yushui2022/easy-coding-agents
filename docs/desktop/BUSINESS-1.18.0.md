# 商业模式（venture）：判断一个项目值不值得做

版本 1.18.0。模式 id `venture`，界面标签 **商业**。

## 为什么是模式，不是又一个"调研提示词"

网络调研模式回答"这东西是什么、谁在说它"；科研模式回答"这篇论文成立吗"。它们都不回答"我该不该做这个产品"——那需要另一种证据：谁付钱、付多少、别人卖多少钱、复购从哪来、做完谁维护。所以它有自己的阶段、自己的制品、自己的闸门。

模式与权限是两回事：进入这个模式**不会**提高文件权限。它比 plan 模式只多五个工具，全部用于写 `.eca/business/`。

## 六个阶段

| 阶段 | id | 进入条件（磁盘上必须有） | 交付物 |
|---|---|---|---|
| 定题 | `brief` | 无 | `brief.md`：谁付费、什么任务、现在用什么替代、为什么第一次会买、你的资源边界 |
| 需求与证据 | `market` | `brief.md` | `sources.jsonl`（≥1）、`claims.jsonl`：搜索量/榜单、评论区抱怨、已付费的替代品、谁试过又退出 |
| 竞争与获客 | `competition` | `brief.md` + ≥3 条来源 | `competitors.md`：至少两个具名竞品或替代品、真实价格、为什么用户选他们、为什么可能选我们、获客路径 |
| 商业模型 | `economics` | ≥3 条带证据的断言 + `competitors.md` | `unit.md`：单价、单次交付成本（含时间）、获客成本、毛利、回本周期、首笔收款前的现金缺口 |
| 尽调 | `diligence` | `unit.md` | `diligence.md`：技术、平台与 API 条款、引用的代码许可、税务与收款、支持负担、会直接卡死的那一条 |
| 结论 | `verdict` | 断言 + `unit.md` + `diligence.md` | `verdict.md` + `verdict.json` |

前进必须满足上表；**回退允许，但必须带 `note` 说明原因**（竞品降价、发现反证、目标用户换了）。每次移动写进 `.eca/business/stage.json`，阶段历史进会话状态。

## 结论只有六档

`validate` 值得验证 · `build_small` 值得进入小范围开发 · `narrow` 缩小方向 · `pause` 暂缓 · `misfit` 不适合当前资源 · `stop` 停止该产品假设。

光选档位不够，`business_verdict` 还要求：`summary`、四个问题的答案（`why_buy` / `why_return` / `why_stay` / `margin`）、`falsifier`（什么会翻案）、`risks`（至少一条）、`next_steps`（至少一条，建议是可执行的最小验证实验）。

拒绝的情形（读文件判断，不看模型怎么说）：

- 还有断言停在 `asserted`（必须改成 verified / contradicted / unverified 并说明）
- 来源不足 3 条、带证据的断言不足 3 条
- 缺 `unit.md` 或 `diligence.md`
- 档位或置信度不在枚举里
- 四个问题、翻案、风险、下一步为空

## 工具

| 工具 | 作用 |
|---|---|
| `business_stage(stage, note)` | 推进/回退阶段，闸门在磁盘上 |
| `business_source(id, kind, url, title, published, note)` | 登记一条公开来源，`url` 必须 https，`kind` 限 competitor / community / search / pricing / official / report / other |
| `business_claim(id, claim, status, sources, note)` | 记一条断言，只能引用已登记来源；verified 必须挂来源 |
| `business_doc(name, content, append)` | 写 `brief.md` / `competitors.md` / `unit.md` / `diligence.md` / `evidence.md` |
| `business_verdict(...)` | 写结论；`verdict.md` 只能由它写 |

`.eca` 对 `write`/`edit` 是保护路径，所以制品只能走这些工具，闸门不会被绕过。

## 联网

`web_search` / `web_fetch` 在这个模式里和网络调研模式一样**由模式预先同意**，不再逐页询问——这个模式存在的意义就是读很多页。仍然只读公开 HTTPS 页面：不执行 JS、不登录、不访问内网。要读需要登录的竞品后台，得自己在浏览器里看。

## 界面

- 模式菜单：编码 / 计划 / 目标 / 网络调研 / 科研 / **商业** / 对话
- 输入框上方六阶段条：当前阶段高亮、已完成为勾、回退显示原因；右侧 `源 N · 断言 N/N核 · 反证 N · 结论 未出|…`；点文件图标展开制品清单与大小
- 阶段条**只读**，勾不动——推进只能靠工具，闸门在磁盘

## 边界（不要当成已实现）

- 只做**公开资料**研究。访谈、投放、付费注册、公开发布、联系第三方都是单独动作，需要另外授权；模式不会把它们写成已发生。
- 登记来源 = "这条记录存在"，不等于它支持你的判断。`verified` 指的是"有来源可查"，不是"结论正确"。
- 置信度是模型对证据充分性的判断，不是成功率预测；没有任何历史数据支撑"这个档位有多准"。
- 单位经济里的数字如果是模型的估计，必须在 `unit.md` 里标成估计并给区间；它不会自己去问你的真实成本。
- 反垄断/法律/税务的合规判断不在模型能力范围内，`diligence.md` 只列约束，不能当法律意见。

## 验证

- `tests/test_venture.py`：13 项，覆盖阶段闸门、来源三项约束、断言来源校验、文档白名单、回退需原因、结论拒绝 asserted、四问/风险/翻案必填、枚举封闭、`verdict.md`/`verdict.json` 内容、公共状态与提示词范围。
- `desktop/tests/venture-mode-e2e.cjs`：隐藏窗口 + 本地模拟模型，5 次本地请求证明「模式可选 → 六阶段条 → 越级被拒并点名 brief → 写入后阶段前进 → 制品清单出现 brief.md」。
- 两者均为 0 次付费 API。
