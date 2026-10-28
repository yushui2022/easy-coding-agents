# 找方向（scout）：从一堆公司里扫出可复刻的产品

版本 1.19.0。模式 id `scout`，界面标签 **找方向**。姊妹模式是 **商业**（`venture`，判断一个已有方向值不值得做）。

## 为什么需要第二个模式

商业模式的输入是"一个方向"，输出是"这个方向可行 / 不可行"。但真实场景常常相反：手上没有方向，需要先看一批。让六阶段流程去做这件事，它只会把自己刚编出来的那个想法再论证一遍——证据很充分，前提是它自己挑的。

找方向模式的输入是"我们的能力边界"，输出是"20 多个别人已经在卖、小团队能复刻的产品"，然后才收敛到 3–7 个。

## 四阶段

| 阶段 | id | 进入条件 | 交付物 |
|---|---|---|---|
| 立标准 | `criteria` | 无 | `criteria.md`：什么叫小团队（几个人、几周）、坚决不做的类型、什么算"已经有人付费" |
| 扫样本 | `sweep` | `criteria.md` | `sources.jsonl` + `candidates.jsonl`，广度优先，先不评判 |
| 筛与排除 | `screen` | 12 个候选 | 继续补到 20+、覆盖 8+ 类别，并写 `excluded.md`（至少 5 条） |
| 候选清单 | `shortlist` | 20+ 候选 / 8+ 类别 / 5+ 排除 | `shortlist.md` + `shortlist.json`：3–7 个，各带一个最小实验 |

回退允许，必须带 `note`（某类别被高估、某个被排除的其实有人付费）。

## 反惯性：靠拒绝，不靠劝说

模型被问"给点想法"时永远给出同一批东西：AI 套壳聊天、Notion 模板、通用 CRM、记账、番茄钟。这个模式用四条硬规则把这条路堵死：

1. **每类最多 3 个**（`MAX_PER_CATEGORY`）。第 4 个同类候选会被 `scout_candidate` 直接拒绝，并把当前分布打回来：
   `Category '本地服务' already has 3 candidates (本地服务 3). This mode exists to leave the obvious pool…`
2. **清单门槛**：`scout_shortlist` 要求 20+ 候选、8+ 类别、5+ 条排除记录，缺哪条点名哪条。
3. **排除清单是必填产物**（`scout_exclude` → `excluded.md`）：把自己第一反应想到的东西写下来，并说清为什么不值得做。同一想法重复登记会被去重。
4. **每个候选的两条"不舒适字段"**：`why_not_obvious`（为什么它不是第一反应那个）和 `risk`（它最可能怎么死）。缺了就不算候选。

另外 `price` / `buyer` / `replicable` / `effort`（days·weeks·months）都是必填——没有价格和买家的东西不是候选，是爱好。

## 候选记录长什么样

```json
{"id":"a1","name":"门店回访","company":"某中小公司","category":"本地服务",
 "what":"自动回访未接来电","buyer":"门店老板","price":"¥99/月",
 "replicable":"一个人两周能搭","effort":"weeks","moat":"线下关系",
 "risk":"平台改规则就断供","why_not_obvious":"不起眼但每月都要做",
 "sources":["s1"]}
```

`candidates.jsonl` 是全集（20+），`shortlist.md` 是结论（3–7）。

## 工具

| 工具 | 作用 |
|---|---|
| `scout_stage(stage, note)` | 推进/回退阶段，闸门读磁盘 |
| `scout_doc(name, content, append)` | 只允许 `criteria.md`、`notes.md` |
| `scout_source(id, kind, url, title, published, note)` | 登记页面，https，kind ∈ product / pricing / marketplace / review / community / report / other |
| `scout_candidate(...)` | 登记候选，强制类别配额与来源校验 |
| `scout_exclude(idea, why, category)` | 记一条被放弃的想法，同时重写 `excluded.md` |
| `scout_shortlist(picks)` | 3–7 个候选 + 每个的第一个实验；门槛不满足就拒绝 |

`.eca` 对 `write`/`edit` 是保护路径，只能走这些工具。

## 联网与权限

- `web_search` / `web_fetch` 由模式预先同意，不再逐页询问。
- 项目保持**只读**：只多六个 `scout_*` 工具，没有 write / edit / shell。
- 只读公开页面：不执行 JS、不登录、不碰内网。

## 界面

模式菜单：编码 / 计划 / 目标 / 网络调研 / 科研 / 商业 / **找方向** / 对话。
输入框上方四阶段条，右侧 `候选 N · 类别 N · 排除 N · 清单 未出|已出`，点文件图标展开 `.eca/scout` 制品清单与大小。阶段条只读。

## 边界

- 登记页面 = "这条记录存在"。它不证明公司健康、不证明还在卖、不证明我们复刻得出来。
- "可复刻"是模型根据公开信息（产品页、定价页、评价）做的判断，**没有读对方代码、没有查资质**。
- 价格是页面上写的标价，没算折扣、年付、隐藏费用。
- 20 个候选不等于 20 个机会：`shortlist` 只是"下一步该测什么"，不是"这些能赚钱"。
- 访谈、投放、付费注册、发布仍需单独授权。

## 验证

- `tests/test_scout.py`：11 项，覆盖只读工具集、criteria 门槛、来源校验、类别配额拒绝第 4 个、工期枚举、12 候选才能筛、清单门槛逐条点名、3–7 且必须是已登记候选、排除清单去重写 md、提示词带配额规则。
- `desktop/tests/scout-mode-e2e.cjs`：隐藏窗口 + 本地模拟模型，13 次本地请求，证明模式可选、阶段条读真实状态、越级被拒、配额拒绝第 4 个、排除落盘、清单门槛一次点名三个缺口。
- 均为 0 次付费 API。
