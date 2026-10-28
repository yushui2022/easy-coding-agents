# 文档附件与磁盘错误

两件事都属于"边界条件"：模型能读到什么，以及机器说不行的时候人能不能听懂。

## 一、文档附件（`eca/documents.py`）

### 支持

| 类型 | 抽取方式 | 标记 |
|---|---|---|
| PDF | `pypdf`，逐页 `extract_text()` | `[PDF：N 页]`、`[第 k 页]` |
| Word `.docx` | 标准库 zip + `word/document.xml` 的 `w:p`/`w:t` | `[Word 文档]` |
| Excel `.xlsx` | `xl/workbook.xml` 表名 + 各 `sheetN.xml` 单元格（含共享字符串） | `[Excel 工作簿：N 个工作表]`、`[工作表 <名>]` |
| PowerPoint `.pptx` | `ppt/slides/slideN.xml` 的 `a:p`/`a:t`，按页序 | `[PowerPoint：N 页幻灯片]`、`[第 k 页]` |

再加上原有的 PNG/JPEG/WebP 图片与 UTF-8 文本、代码。

### 为什么是"抽文本"而不是"当图片发"

图片里的字**不能引用、不能 diff、不能事后核对**。抽成文本后，模型读到的东西就是会话里留着的东西，
科研模式里还能被 `[src:ID]` 引用。所以文档附件只会产生**一个文本块**，不会额外产生 `image_url`。

### 限制（写死的，不是建议）

- 单个文档 **8 MB**；附件总数仍受 **12 MB / 6 个**限制。
- 抽取文本 **12 万字符**，超出会写 `[已截断：只保留前 …]`。
- PDF 最多 400 页；Excel 每表最多 2000 行、最多 20 个表；文档内部单个 XML 解压后最多 60 MB（防 zip 炸弹）。
- 后缀和字节都要对：改名成 `.pdf` 的 zip 会被拒，损坏的 zip 会说"已损坏"。
- **扫描件没有文本层**：会明确提示改用图片 + 支持看图的模型，不会假装读到了内容。
- 不支持旧版 `.doc` / `.xls` / `.ppt`（要另存为新格式）。

### 原文不入库

抽取在附件边界完成一次，结果进会话历史；`.eca/attachments/` 只存图片快照，文档不会留下二进制副本。

## 二、磁盘与权限错误（`eca/fsguard.py`）

`describe(error, action, target)` 把 errno 翻成一句能照做的话，并保留路径：

| errno | 说法 |
|---|---|
| `ENOSPC` | 磁盘空间不足——释放空间或换磁盘后重试 |
| `EDQUOT` | 超出磁盘配额 |
| `EACCES` / `EPERM` | 没有权限 / 被系统拒绝（不是提权，而是查占用与只读） |
| `EROFS` | 所在磁盘是只读的 |
| `ENOENT` / `ENOTDIR` / `EISDIR` | 路径不存在 / 路径中间不是目录 / 目标是目录 |
| `EMFILE` / `ENFILE` | 打开的文件过多 |
| `EBUSY` / `ENAMETOOLONG` / `EXDEV` | 被占用 / 路径太长 / 跨磁盘不允许 |
| 其它 | 保留系统报错原文，并写明"这不是模型或任务的问题" |

接入点：

- `tools.atomic_write`（模型写/改文件的底层）
- `tools.execute`（工具抛 `OSError` 时转成人话，而不是把 errno 丢给模型）
- `attachments.prepare`（图片快照写入）
- `research.write_doc` 与制品写入
- `Store.__init__`（打开项目会话库；同时修了"目录建失败却把项目锁一起漏掉"的 bug）

`fsguard.check_target(path)` 可以在写入前预检剩余空间，目前供测试与将来的上传路径使用。
