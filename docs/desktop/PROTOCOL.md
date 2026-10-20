# Desktop stdio protocol v1

0.33.0 握手附带 `capabilities: ["sidechat", "concurrent_sessions", "concurrent_projects"]`。`live.side_busy` 表示选中会话的独立侧聊仍在运行；主任务 `busy` 保持原语义。项目和会话都可以在运行中切换，关闭项目要求该项目的所有会话和侧聊空闲。

`snapshot/live` 附带全局 `view_revision`（选中视图递增版本）、`projects`（已打开项目及会话摘要）、`active_sessions`（跨项目运行中会话的状态）、`any_busy` 和 `running_count`。每个项目包含 `id/path/session_id/sessions/running_count`。`project_id` 是规范化真实路径。前端拒绝旧视图响应；后台文本保留在对应运行时，结构变化发送 `sessions_changed` 刷新提示。命令携带明确的 `project_id` 和 `session_id`；取消和回答还须匹配各会话的 `run_id`，不会改变其他会话。live 的增量游标必须同时带这两个 ID，避免跨项目或会话拼接。

`project.open` 对已打开路径只选择其保留的视图，不重建运行时或覆盖模型；对新路径独立加锁，失败时保留原视图。`session.switch` 可通过 `project_id` 直接选中另一已打开项目的会话；省略 `id` 在目标项目新建。`project.close` 只释放指定项目，其他项目继续运行。省略 `project_id` 时沿用当前视图，供旧版单项目调用兼容；新客户端必须显式携带范围。

侧聊新增 `sidechat.open/snapshot/send/cancel/context/model`：都传当前 `session_id`，除 open 外还传分支 `id`，取消额外校验 `run_id`。open 恢复当前主会话关联的分支，不启动请求；send 立即返回运行 ID。snapshot 可传 `message_count`、`stream_run_id`、`stream_id` 和 `stream_offset`，只返回变更消息与 `stream_delta`。事件 `sidechat` 带父会话、分支与运行 ID，不混入主任务事件序列。侧聊仅可执行 read/glob/grep。

桌面主进程另提供限定的 `workspace.*`、`browser.*`、`terminal.*` IPC，要求 `owner` 等于快照返回的 `workspace_owner`（项目与会话组合的 opaque token），不可自行拼接；这些不是 Python HTTP 接口。浏览器网页没有应用 preload；终端原生模块位于单独 utility process。切换会话保留对应资源，后台浏览器隐藏；UI reload 读取现有资源列表，不重建重复进程。`subagent.snapshot` 的 owner 也使用该 token，由主进程转换为 Python 的项目/会话范围。

`python -m eca.desktop_rpc` 或随附的 `eca-backend.exe`。
UTF-8 JSON-RPC 2.0，每行一个对象，stdout 专用于协议，诊断不得包含凭据。
首先发送 `initialize`，参数 `{"protocol":1}`，返回协议与应用版本；不兼容时拒绝操作。
请求 ID 为字符串或整数，结果通过 `result` 返回，错误通过 `error` 返回；禁止从错误推断操作没有发生。

| 方法 | 参数 / 行为 |
|---|---|
| `snapshot` | 当前项目、会话、运行状态、最近 50 条消息、当前输出、待回答项目、变更、用量与验证 |
| `project.open` | `path`，可选 `model` 覆盖；读取现有会话或创建，持有项目独占锁 |
| `project.close` | 仅空闲时释放项目 |
| `session.switch` | `id` 恢复指定会话；省略时新建；后台运行不中断，不重放任务 |
| `session.messages` | `id`、`before` 游标，向前返回最多 50 条历史消息 |
| `session.message` | `id`、整数 `index`，读取一条完整公开消息；可传 `message_ref`，历史变化时拒绝读取过期记录 |
| `live` | 轻量运行状态，不读取历史/变更表；可传上次返回的 `stream_id`、`stream_offset`，返回增量或完整流 |
| `task.start` | 非空 `prompt`，可选 `checks` 命令列表（最多 10 条）、整数 `repair_attempts`（0～3，省略为 0）；参数校验后立即返回 `run_id` 和 `session_id` |
| `task.cancel` | 当前 `run_id`，立即请求取消；终态以后续事件/快照为准 |
| `input.reply` | 待处理 `id`、对应 `run_id`、`value`；授权必须为布尔值，问题回答为字符串 |
| `changes.diff` | 变更 `id`，返回记录差异 |
| `changes.accept` / `changes.undo` | 变更 `id`；空闲时操作，不覆盖后续文件变化 |
| `model.select` | 项目 `profile` 名称，或 `model` 覆盖；仅空闲时允许 |
| `diagnostics` | 当前配置的本地诊断，不发模型请求 |
| `connection.check` | `model`、可选 `root`；发送一条小探针，不发送项目内容 |
| `connection.models` | `model`、可选 `root`；只读取服务的 `/models`，返回 `models`、`partial` 与状态，不生成回答 |

`model` 可包含 `model`、`base_url`、`api_format`、`api_key`；密钥只通过私有管道进入后端。
Electron renderer 不直接持有该协议连接；主进程限定可调用方法并负责目录选择与凭据。

0.22.0 中 `model.select` 的桌面覆盖在当前项目的后续会话切换中继续生效；传空 `model` 恢复项目配置。CLI 的 Runtime 默认行为保持不变。

Electron 私有 IPC 增加 `config.models`（表单草稿或连接 ID）、`config.default`、`config.remove`；`config.save` 返回保存的连接 ID 和脱敏列表。`model.use` 接收 `choice`（连接 ID、`default` 或 `project`），成功切换后记录项目选择。快照的 `model_selection` 表示实际加载的选择，`settings` 仍是实际运行参数。

偏好格式 schema 2 保存连接列表、默认 ID、项目到选择的映射及最近项目。旧单连接密文直接迁移，渲染进程仅得到已配置状态，不得到密文或解密后的历史密钥。显式填入的新密钥通过私有 IPC 保存；不写入项目 `.env`、TOML 或会话。

通知格式为 `method: "event"`，`params` 包括 `event`、`data`、`seq`、`run_id`、`session_id`。
事件包括 text、turn、tool、result、diff、usage、notice、error、子 Agent 进度、验证结果，以及 input_requested、input_closed、run_finished。
输入请求带独立 ID、类型、正文和操作细节；重复、过期或跨运行回复拒绝。
事件是界面刷新提示，重新加载以 snapshot 为准；没有按事件自动重放工具的机制。

0.25.0 的 `snapshot`、`project.open`、`session.switch`、`session.messages`、`model.select`、`changes.accept/undo` 接受可选 `preview: true`。工具正文与参数预览各最多 2,000 字符，其余消息正文 24,000 字符；消息携带绝对 `message_index`，截取时带 `truncated` 与 `message_ref`，完整内容仍保存在原会话中。`tool_summary` 仅提取真实退出码和超时字段。活动摘要最多 2,000 字符；需要完整工具结果时使用会话消息，不把摘要当完整执行记录。省略 preview 的旧客户端保持完整返回。

快照和轻量状态包含每个后端实例唯一的 `backend_id`，重启后不能沿用前一个实例的 seq。`stream_id` 在任务、轮次、会话和流结束时更换。有效游标返回 `stream_delta`，否则返回 `stream`；`stream_offset` 是 Python Unicode 字符索引，前端必须使用返回值，不能用 JavaScript 字符串长度自行计算。发生敏感值替换时返回完整脱敏流，避免切片破坏脱敏。前端与并发快照合并时还需检查请求时的流游标，避免重复拼接。输入与工具执行不受显示分段限制。

0.24.0 的 `repair_attempts > 0` 要求至少一条检查、非隔离 code 模式。检查失败时在同一运行 ID 内请求模型修复，修复后从第一条命令开始复验。拒绝、超时、取消及不可确认的退出结果不会自动修复；同源码重复失败会提前停止。省略参数的旧客户端保持零修复。

`verification_progress` 推送中间进度，`verification_suite` 保持最终结果事件，快照 `suite` 包含状态、命令、各轮记录、修复预算及停止原因。新任务先清除上一任务的验证状态；通过仅代表所选命令在记录的文件指纹上通过，后续文件变化会过期。`change_impact` 事件及快照同名字段提供 Python 文件工具编辑的语法提示（最多 20 个文件、每文件 8 个符号），不是测试结果或完整调用图；shell/MCP 编辑不在此分析范围。

命令读取与长任务独立，取消和回复无需等待模型响应。EOF 取消活动任务并关闭工具与数据库。
每个会话只能运行一个主任务，同一项目的多个会话可并发。模型切换和撤销要求目标会话空闲；项目切换可在任务运行中进行，关闭项目要求该项目的会话空闲；历史消息允许读取。EOF 取消所有项目的会话并逐一释放项目锁。
项目已被 CLI 占用时返回错误，不接管锁、不自动结束其他进程。
stderr 和错误输出脱敏；项目内容、命令和模型回答仍属于用户敏感数据，不上传到遥测服务。
