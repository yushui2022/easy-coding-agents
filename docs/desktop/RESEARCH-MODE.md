# 科研模式（scholar）

七阶段 CS 科研工作流：**选题 → 检索 → 精读 → 复现 → 实验 → 写作 → 汇报**。

这个模式的价值不在提示词说了什么，而在**制品是否真的存在**。报告被拒绝，是因为文件里
的事实对不上 `.eca/research/` 里的登记，而不是因为模型没被要求。

## 与"网络调研"的区别

| | 网络调研 `research` | 科研 `scholar` |
|---|---|---|
| 工具权限 | 只读（`READ_ONLY`） | 可写、可跑命令（`WORKING`） |
| 产出 | 对话里的答案 | `.eca/research/` 下的文件 |
| 状态 | 无 | 七阶段状态机 + 回退历史 |
| 约束 | 提示词 | 工具层闸门 + 提示词 |

## 制品（项目内，跟着项目走）

```
.eca/research/
  proposal.md           选题契约：候选课题、研究缺口、RQ、假设、方法草案、可行性、风险、伦理
  search-log.jsonl      检索协议：查询词、时间、命中（research_doc append）
  sources.jsonl         已登记来源：id、kind、url、标题、年份、作者、抓取时间、是否在线核验
  reading/<id>.md       阅读卡：主张、方法、实验、基线、数字、局限、复现线索
  evidence-matrix.csv   claim ↔ source ↔ 支持/反驳 ↔ 强度
  claims.jsonl          claim ledger：asserted / verified / contradicted / unverified
  claim-to-artifact.json 每个 claim 指向的数据、脚本、commit、run id
  runs/<id>.json        run manifest：命令、退出码、metrics、outcome、是否与论文一致
  deviations.md         论文数值 vs 实测数值的每一处不一致
  report.md             正文，事实句带 [src:ID]
  slides/outline.md     汇报大纲
```

`.eca` 对 `read`/`write`/`edit`/`delete` 是**受保护路径**（那里还有会话数据库）。因此这些
文件只能由 `research_doc` 写，且文件名在白名单内；`reading/<id>.md` 还要求该 source 已登记
——不然就能给一篇谁都没取过的论文建阅读卡。

## 六个工具

| 工具 | 作用 | 拒绝什么 |
|---|---|---|
| `research_stage` | 推进/回退阶段 | 缺前置制品不许前进；回退必须给原因 |
| `research_source` | 登记来源，`verify=true` 走 Crossref / arXiv 公开元数据 API | 核验失败不许标记 verified |
| `research_doc` | 写白名单内的研究文档 | 其他路径、未登记来源的阅读卡 |
| `research_claim` | 写 claim ledger | 无证据不许 verified；引用未登记 source、或只引用未在线核验的 source |
| `research_run` | 记录一次运行 | `matches_paper=false` 必须给 note |
| `research_report` | 校验 `report.md` / `slides/outline.md` | 未登记引用、无证据的 verified、仍是 asserted 的 claim、未记录的偏差 |

阶段闸门（`REQUIRES`）：

| 目标阶段 | 要求 |
|---|---|
| 选题 | 无 |
| 检索 | `proposal.md` |
| 精读 | `proposal.md` + 至少一个来源 |
| 复现 | 至少一个来源 + 至少一张阅读卡 |
| 实验 | 至少一张阅读卡 |
| 写作 | 至少一个带证据的 claim |
| 汇报 | `report.md` |

## 复现结论只有四档

`reproduced` / `partial` / `incomparable` / `uncertain`。没有"证明了论文正确"这一档：
跑通只说明"这套环境下产生了接近的数字"。

## 界面

- 模型菜单里多一项 **科研**。
- 输入框上方一条阶段条：7 步，当前高亮，已完成的打勾；右侧是 `源 N/N核 · 断言 N/N核 · 运行 N`；
  点右侧文件图标展开 `.eca/research` 的制品清单（文件名 + 大小）。
- 阶段条**只读**：推进与回退都由模型通过 `research_stage` 完成，界面不会替它打勾。
- 回退过的话，阶段条上会显示回退原因（来自 `stage.json` 的历史）。

## 阶段历史

推进和回退都写进会话状态；每次移动还会镜像到 `.eca/research/stage.json`，所以把研究目录
拷给别人时，对方能看到这份工作停在哪一步、为什么回退过。

## 边界（这些不是待办，是设计）

- 登记成功 = 这条记录真实存在，**不等于**它支持你的论点；后者只能由人判断。
- 复现成功 ≠ 结论成立。
- 不判断伦理审批、数据授权、受试者合规。
- 不自动批量执行论文附带的未知脚本；下载来的 artifact 先审再跑。
- 离线/无代理时 `verify=true` 会失败，那是对的：宁可让来源停在未核验，也不填猜测的标题。
