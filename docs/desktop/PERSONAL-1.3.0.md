# 设置分区、个人与全局（1.3.0 → 1.4.0）

设置对话框原来只有「模型连接」一页。1.3.0 加了个人与全局，1.4.0 把它拆成三个独立页面。

## 现在的结构

左栏顶部是四个并列分区，各自独立成页、各自保存：

| 分区 | 内容 | 存到哪 | 生效 |
|---|---|---|---|
| 模型连接 | 连接列表 + 编辑区（原有） | `preferences.json` | 立即 |
| 外观主题 | 跟随系统 / 浅色 / 深色 | `<数据目录>/theme.json` | 立即 |
| 个人信息 | 称呼、身份、关于我、回答偏好 | `<数据目录>/profile.json`（0600） | 下一轮对话 |
| 全局指令 | AGENTS.md 正文 | `<数据目录>/AGENTS.md`（0600） | 下一轮对话 |

数据目录默认 `G:\Data\ECA\Desktop`（可用 `ECA_DESKTOP_DATA_HOME` 覆盖），**不写进任何项目**。三个页面在 `desktop/src/renderer/PersonalSettings.tsx`，`ModelSettings.tsx` 只负责外壳与模型连接。

## 个人信息

视觉上是资料页：顶部圆形头像（取称呼首字）+ 称呼 + 身份，下面「关于我」「回答偏好」两个自由文本。

`profile.json` 的字段与提示词的对应：

```json
{"name": "小明", "role": "后端工程师", "about": "在做 ECA", "style": "先给结论"}
```

```
The user prefers to be called 小明.
Their role: 后端工程师
About the user: 在做 ECA
How they want answers: 先给结论
```

1.3.0 只有一个 `notes` 字段，旧文件仍能读成「关于我」，不需要手工迁移。

## 后端怎么拿到

主进程在启动后端之前设置两个环境变量，`RpcClient` 继承 `process.env`：

```
ECA_USER_PROFILE   = <数据目录>/profile.json
ECA_GLOBAL_AGENTS  = <数据目录>/AGENTS.md
```

`eca/usercontext.py` 的 `blocks()` 在**每次构建系统提示词**时重新读取，所以改完对下一轮生效，不用重启应用。

注入顺序（`agent.system_prompt()`）：项目 `AGENTS.md` → 项目 `MEMORY.md` → **用户 profile → 全局指令** → 模式与目标的附加段。两者冲突时项目的表述更靠前。

### 读取的边界

- 上限：称呼 80、身份 120、关于我 2000、回答偏好 1000、全局指令 20000 字；超长截断而不是报错。
- profile 的**原始文件**读取上限 64 KB：按字段上限去截 JSON 本身会让整个文件解析失败、字段一起丢。这条是实测踩出来的。
- 符号链接、缺失文件、坏 JSON、字段类型不对，一律当「没设置」，不抛错、不阻断对话。
- 这两份内容是用户自己写的，可信级别等同项目 `AGENTS.md`：影响措辞与偏好，**不能**改变审批档位、不能绕过工具层检查、不能在 Docker 或只读模式里放开什么。

## 主进程接口

```
personalization.get   → {name, role, about, style, instructions}
personalization.save  → 同样的结构（已按上限截断后的值）
```

都在 `action()` 里本地处理。保存时：profile 四个字段全空则删除文件，全局指令去空白后为空也删除文件——避免留空文件被当成「有设置」。

## 验证

- `tests/test_usercontext.py` 8 项：四字段各自成句、旧 `notes` 兼容、缺失/坏 JSON/符号链接被忽略、超长截断、类型错误不崩、与项目 `AGENTS.md` 共存且项目在前、内容进入系统提示词。
- 定向 Python 回归 117 项通过、2 跳过；TypeScript 构建、桌面单测 15 项通过。
- 隐藏窗口端到端：逐个分区操作——切到外观主题点「深色」并读回 `theme()`、在个人信息填四项并保存、在全局指令填正文并保存；校验 `profile.json` 与 `AGENTS.md` 落盘；之后**每个**模型请求的系统消息里都含称呼、身份、回答偏好与全局指令。
- 未验证：macOS/Linux；手改这两个文件后是否同样即时（每轮重读，理论上成立，但没跑过）。
