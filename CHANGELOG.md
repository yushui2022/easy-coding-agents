# Changelog

## 0.34.6 — 上下文构成可见，模型菜单更简洁

- 上下文环移到输入区右侧、模型名左边，展开面板新增各模块占用比例：系统提示、工具定义、你说的话、模型回答、工具结果、历史摘要、进度索引，按占比排序并显示百分比；比例由各部分的字符占比换算到总估算值，仍然只是本地估算。
- 模型选择面板去掉「跟随桌面默认」「沿用项目配置」与「添加或管理连接」三项，只保留模型列表与推理强度；连接管理仍可从左侧「模型与设置」进入。
## 0.34.5 — 思考内容可见，编辑行显示增删行数

- 对话中的助手消息新增可折叠「思考」块：内容来自模型返回的思考文本，折叠时只显示字符数，展开后按只读样式展示；生成过程中以「正在思考」实时追加（后端保留最近 4000 字符）。
- 历史消息的思考文本随快照返回，上限 8000 字符；`reasoning_scope` 等回放字段仍然只在同一模型与端点之间使用，不进入界面数据。
- 执行记录中的写入/编辑行显示 `+n −n`：由本地变更记录的 diff 计算，超过 20000 行时跳过统计而不是给出估算值。
## 0.34.4 — 上下文可见、可压缩，窗口自绘标题栏

- 输入框下方新增上下文占比环：颜色随用量变化（低于 85% 沉稳、85% 起琥珀、95% 起红色），悬停说明是本地估算而非计费。数据由 `ContextBudget` 计算，最多每两秒更新一次。
- 点占比环可展开面板，手动触发上下文压缩（`context.compact`）：任务运行中或未打开项目时明确禁用；压缩由模型生成摘要，原始历史仍保存在磁盘。
- 窗口改为无边框，自绘 34px 标题栏：可拖动、双击最大化、三个窗口控制；关闭仍走原有的任务确认逻辑。窗口控制走受限 IPC，渲染层没有额外权限。
- 模型选择器拍平为紧凑列表：去掉「最近使用／其他模型」分组标题，行高 34px、模型名 13px、服务商名右侧对齐；推理强度压成一行标签 + 5px 滑块 + 六个档位。
## 0.34.3 — 长任务不再看似卡住，侧栏项目名左对齐

- 活动条副标题显示当前阶段已持续时间（准备、等待模型、思考、生成回答、生成参数、执行工具、验证、修复），由本地秒表推进，不依赖后端事件。
- 思考阶段仍不显示原文，改为「持续 N · 已接收 N 个思考字符」；这是既定的隐私与一致性约束。
- 待返回的执行记录显示该步骤已等待时长，超过 20 秒补一句「可能仍在执行」；状态点改为低频脉冲，`prefers-reduced-motion` 下关闭。
- 侧栏项目行改为左对齐：`.project-title` 之前继承了全局按钮的居中样式，文件夹图标和项目名会飘在中间。
- `workspace-e2e.cjs` 新增断言：后端被挂住、完全没有事件时，活动条副标题仍从「持续 0s」走到「持续 1s」。
## 0.34.2 — 每轮对话可复制，附带未签名分发说明

- 主对话与侧聊的每条用户/助手消息下方新增复制按钮：复制消息原文，成功后显示「已复制」约 1.6 秒，失败显示「复制失败」。
- 复制在桌面主进程完成（受限 `eca:copy` 通道，校验受信窗口，拒绝空内容与超过 1 MB 的文本）；渲染进程依旧没有剪贴板、shell 或文件系统权限。
- 样式沿用陶土令牌：11px 次要色文字、hover 浅底、成功后转强调色、键盘有焦点环；用户气泡内左对齐。
- 端到端断言覆盖每类消息各一个按钮、点击后文案变化、主进程读回剪贴板内容与助手原文一致，并在测试后还原剪贴板。
- 新增 [未签名分发说明](docs/desktop/UNSIGNED-DISTRIBUTION.md)：SmartScreen 放行步骤、SHA256 校验、首次配置模型、数据位置、安全边界与误报提交。
## 0.34.1 — 移除验证设置入口与代理域名解析修复

- 移除输入区的「验证」按钮与「验证与自动修复」面板：桌面不再配置验证命令和自动修复次数；核心验证工作流与历史结果仍保留在审查页，普通工具执行记录在对话中查看。
- 审查页检查概览改为提示「可在对话中要求 ECA 运行测试或构建」，不再指向已移除的入口。
- `web_fetch` 支持代理 Fake-IP DNS（198.18.0.0/15）：解析被代理改写时通过 Cloudflare DoH 取回真实公网地址；私有、混合与字面 IP 仍然拒绝，DNS 失败时说明具体原因而非笼统报错。
- 端到端测试按实际展开状态收起审查，移除只服务于已删除面板的步骤；审批模式切换、取消与文件隔离断言保留。

## 0.34.0 — 附件与按需工作区

- 主对话与侧聊共用附件入口：点击选择、拖入文件、粘贴截图，发送前显示缩略图与大小并可单独移除；只有附件也能发送。
- 附件草稿按项目、会话和主/侧聊隔离，保存在 IndexedDB，刷新后恢复；发送成功后清除。
- 图片以原生图片内容块传入 OpenAI Chat、Responses 与 Anthropic。每次最多 6 个附件；单张图片 4 MB、文本 256 KB、合计 12 MB；PDF、Office、压缩包暂不支持。
- 图片快照保存在项目 `.eca/attachments/`，文本快照保存在会话中；视觉能力由实际接口决定，拒绝时明确报错。
- 右侧默认收起，审查按需打开且只保留「文件修改」「检查结果」两个标签；任务活动与用量改为折叠详情。

## 0.33.0 — 多项目工作空间

- 左侧按项目分组排列会话，支持折叠、搜索、项目内新建会话与关闭空闲项目。
- 多个项目的主任务和侧聊可同时运行，切换只改变当前查看的内容，原任务继续执行。
- 每个项目仍有独立进程锁与事件路由，后台项目的事件不会覆盖前台界面。

## 0.32.0 — 同一项目内的多会话并发

- 每个会话保留独立的模型连接、任务、流式输出、授权请求、任务草稿、验证设置与子任务。
- 停止按钮只取消当前会话的主任务及其子任务；切换会话不重发请求，也不终止后台任务。
- 窗口退出会检查全部会话，确认停止并退出或收到通信 EOF 后统一清理运行时。没有关窗后继续运行能力。

## 0.31.0 — 实时动作与生成速度

- 输入区上方状态条显示当前动作、工具名、操作对象与接收进度，右侧显示 tokens/s 和任务用时。
- 速度标注为估算，服务端用量返回后校正；工具执行期间明确显示「上一轮」。
- 等待服务、推理、回答、生成工具参数、执行工具、工具返回、授权与停止等状态均来自真实运行事件。

## 0.30.1 — 陶土执行状态

- 把常驻的「正在执行工具」提示改为紧凑单行状态，保留真实运行阶段、累计用时、停止反馈与可展开详情。
- 参数生成阶段明确写「工具尚未执行」；点击停止后立即显示「正在停止并清理」，仍由原取消逻辑完成清理。

## 0.30.0 — 模型选择与推理强度

- 主对话与侧聊共用模型弹层：按模型 ID、连接名或服务商搜索，最近使用或发过请求的连接排在前面，最多保留六个。
- 记录按连接 ID 去重，同名模型的不同连接不会混淆；连接名称显示在模型下方。
- 选择模型后弹层保持打开，可继续调整推理强度；两处可独立设置，档位按模型能力显示。

## 0.29.1 — 侧边聊天陶土界面

- 侧聊改用紧凑上下文卡片、快捷讨论入口与一体式输入区，沿用已有颗粒陶土纹理和深浅主题令牌。
- 模型菜单可键盘操作；不改变主对话首页与子 Agent 入口。

## 0.29.0 — 子 Agent 对话入口

- 主模型调用 `delegate` 或 `delegate_parallel` 时，主对话在对应工具调用位置显示子任务入口：陶土标志、任务名称和状态。
- 点击入口在右侧工作区打开对应标签，主会话继续执行；可查看实时回答、实际工具记录与历史恢复。

## 0.28.3 — 陶土文件夹图标

- 仅在当前项目卡片使用原创燕麦陶色文件夹图标，打开项目、最近项目与输入区项目选择保留灰米色线性图标。
- 材质颗粒在 0.28.2 基础上再放大约 50%；图片为装饰元素，相邻文字继续提供可访问名称。

## 0.28.2 — 颗粒放大

- 陶土纹理显示尺寸放大约 2.2～2.3 倍，使颗粒更明显；表面颜色、布局和操作保持原样。

## 0.28.1 — 陶土颗粒材质

- 将陶土颗粒材质应用到导航、卡片、输入区和模型设置，支持深浅主题，保留 ECA 橙色品牌色。

## 0.28.0 — 聚焦任务的桌面开场

- 新任务页使用居中的项目问句与轻量快捷入口，底部悬浮输入区集中展示项目、权限、模型和发送；统一浅色纸面与深色层次。
- 使用内置生图生成 ECA 原创透明折叠图形，作为本地欢迎插画，不替换原 Logo；文字和按钮均为真实可交互组件。
- 验证与自动修复收进按需展开的面板，Escape 或点击外部收起，保留草稿与原授权逻辑；输入框随内容增长，长内容内部滚动。
- 窄栏保留关键操作，图形、图片来源与提示词随源码保存。本轮按用户选择暂不更新本机安装版。

## 0.27.1 — 新任务区域整理

- 移除欢迎区重复的项目标识，缩小标题、顶部留白和输入框初始高度，统一标题与输入区的阅读宽度。
- 输入框底部使用独立工具栏：左侧合并模型与模式，右侧放置操作权限与发送。权限图标、展开验证和键盘提示采用一致的轻量样式。
- 三个快捷任务改为“快速开始”入口，只填入草稿并聚焦输入框；保留发送、授权、验证和模型选择语义。深浅主题及窄窗口适配。

## 0.27.0 — 桌面视觉统一

- 抽出共享设计令牌，统一深浅主题、界面与阅读字体、控件尺寸、边框、圆角和阴影；保留 ECA 橙色品牌。
- 调整三栏比例，审查栏默认缩窄；单独审查时省去重复的标签行，修改、验证、进度与用量使用紧凑分段导航。拖动宽度、全宽和窄窗口切换保留。
- 优化项目与会话导航、聊天正文、输入区、设置弹窗；共享空状态组件用于修改、计划、侧聊与浏览器。工具行按聊天容器宽度适配。
- 外观调整不改变模型配置、授权、会话或执行逻辑。不增加依赖与网络字体。

## 0.26.1 — 输入区底栏

- 将输入框下方收拢为单行辅助栏：验证入口与快捷键提示；移除重复的模型来源、审批说明。
- 验证设置按需展开，显示已配置检查数量；保留原检查、自动修复与草稿恢复行为。模型来源和审批范围放入对应选择器的提示。
- 统一展开区的字号、间距与深浅主题；窄栏缩减快捷键提示，避免互相遮挡。

## 0.26.0 — 右侧工作区

- 右侧加入独立侧边聊天、浏览器和真实 PowerShell 终端；标签切换保留内容，支持拖动宽度、全宽与窄窗口切换，原修改、验证、进度与用量保留在审查标签中。
- 侧聊带入有时间标记的主任务上下文，支持项目内读取和搜索、独立模型选择与取消、历史恢复和放入主对话草稿；共享项目锁和请求预算，用量进入原计费根。侧聊工具权限由后端强制检查。
- 内嵌浏览器使用独立 WebContentsView，提供网址、导航、项目 HTML/模块预览和页面文字引用。远程页面没有 ECA preload、Node 或模型凭据；项目预览限制目录、真实路径和文件类型。
- 终端通过独立 utility process 承载 node-pty/ConPTY，xterm.js 提供真实输入、中文、ANSI、resize 和 Ctrl+C；日志批量传输并明确截断，终端引用不自动算作验证通过。
- 新增侧聊协议回归与隐藏 Electron 工作区端到端测试。浏览器预览不等于 Agent 自动浏览器操作或视觉验收；独立干净 Windows 机器仍需验收。

## 0.25.1 — 紧凑执行记录

- 连续工具调用合并为一组执行记录，正文、用户输入和历史分页缺口保留边界；较早的已返回操作可折叠，失败、拒绝、未完成和正在查看的记录保持可见。
- 显示项目相对路径，长脚本显示行数与字符数，展开直接读取原始命令；完整结果按需加载，并在新结果到达或历史指纹变化后更新。
- 区分完成、失败、超时、拒绝、中断和未记录结果；工具返回不等同任务验证通过。
- 文本读取工具明确拒绝图片，说明图片或 Base64 无法由文本工具提供视觉证据；非 UTF-8 文件提供可理解的错误。
- 增加分组边界、状态、路径和隐藏 Electron 交互测试。参考 Pi 社区桌面端的多步骤展示方式，沿用 ECA 现有权限和会话协议。

## 0.25.0 — 桌面工作台与长会话响应

- 工作台按项目、会话、对话和结果组织：可折叠导航、会话搜索、独立验证页、合并的工具执行摘要、固定在输入区上方的授权与阶段进度。
- 输入和流式输出不再重新解析全部历史 Markdown；历史工具日志折叠时不挂载，展开后按需加载完整记录，长文本分段显示。原始会话和模型输出额度保持不变。
- 实时状态支持带流 ID 和游标的增量输出，主进程合并高频通知；摘要快照传输有限预览。后端重启、流重置、迟到的历史请求及过期记录有一致性检查。
- 历史最多显示最近 50 条和 150 条已加载记录，收起区域明确标识，可继续向前加载或返回最近记录；浏览历史时不强制滚回底部。
- 增加隔离的真实 Electron 长会话性能测试和完整操作验收，不调用付费模型，不控制用户窗口。

## 0.24.0 — 桌面验收修复与回归检查建议

- 桌面「验证与自动修复」接入现有核心闭环，可选 0～3 次修复，保存每轮检查、失败原因与停止原因。检查命令和次数按项目保留在当前窗口，刷新不丢失。
- 每次任务重置验证状态；通过显示为「所选检查通过」，不会沿用上一任务的绿色结果。拒绝授权、超时、取消及相同代码重复失败不会继续自动修复。
- Python 文件工具修改公开函数、类或数据库事务设置后，向模型和桌面提供有限的回归检查建议；保留调用方、异常路径、资源及事务行为，并检查多步写入中途失败。属于语法提示，不是完整依赖图或正确性保证。
- 评测补齐 SQLite 重复订单回滚与迁移中途失败检查，保留原始失败样本，并新增真实 DesktopRPC 修复复测入口。

## 0.23.0 — 响应进度、快速模式与桌面审批档位

- 输入区新增逐次确认、自动编辑、完全访问。运行中可切换并放行对应的待审批操作；问题仍需回答，取消继续向子任务传播。
- 完全访问由用户明确开启，仅本次打开项目有效；不提升系统权限，不取消文件冲突、路径、只读模式和已有沙箱检查。命令与外部工具仍可能有项目外效果。
- DeepSeek 桌面连接默认使用快速响应，提供均衡、深入和服务默认选项；CLI 默认仍沿用服务行为。
- 实时显示等待模型、思考字符数、工具参数生成、执行阶段与耗时。细粒度更新不读取历史、差异和用量表。
- 按模型与端点保存 DeepSeek 思考回放字段，避免连续工具请求缺失必要字段；不向界面或其他提供商传递思考原文。


## 0.22.1 — 回车发送与自动获取模型

- 桌面任务输入改为 Enter 发送、Shift+Enter 换行，保留 Ctrl/Cmd+Enter；中文输入法确认、按键连发不会误提交任务。
- 选择服务商、输入密钥后自动获取模型列表，直接选择并保存；保留刷新、错误提示及手动模型 ID 入口。
- 编辑地址或协议清空未保存密钥；切换连接或关闭设置后忽略旧模型列表响应，避免错误覆盖当前列表。
- 修复项目恢复未完成时发送按钮提前可用的问题，加载期间显示等待状态并阻止提交。

## 0.22.0 — 桌面模型连接管理

- 从单一配置升级为多个具名模型连接，各自加密保存密钥；自动保留并迁移旧版连接。
- 输入框提供模型选择器。默认采用桌面默认连接，可为项目指定连接或明确选择沿用项目配置，选择保存在桌面偏好中。
- 修复切换会话重新读取旧模型的问题；桌面连接覆盖历史 CLI 模型选择时保持项目权限和隔离设置。
- 提供 DeepSeek、OpenAI、Anthropic、Ollama 与自定义服务地址模板，支持获取可用模型列表或手填模型 ID，不硬编码默认模型 ID。
- 同地址更换模型复用密钥；更换地址或协议需重新输入。临时密钥、加密不可用、本机免密钥与删除引用保护均有验证。
- 新增不显示窗口的隔离 Electron 测试模式，避免开发测试抢占用户桌面。

## 0.21.1 — 桌面任务入口与界面修复

- 未选择项目也能输入任务；草稿在界面刷新、取消选择项目后保留。选择项目后需明确发送，不自动执行。
- 未打开项目时显示已保存的桌面模型，当前项目继续显示实际生效的模型与配置来源。
- 简化欢迎页，统一控件、字体和深浅主题；详情栏可收起，窄窗口通过弹窗查看修改、进度与用量。
- 设置、差异与诊断使用原生模态焦点管理，支持 Escape 和关闭后返回原控件；初始窗口适配屏幕工作区域。
- 增加输入、草稿、项目选择、焦点、窄窗口和文字对比度的真实 Electron 回归验证。

## 0.21.0 — ECA Desktop Windows 预览版

- 新增 Electron/React 桌面工作台、双向 stdio 协议及 CLI/桌面共用的任务运行时。
- 模型配置与系统加密凭据、项目会话、授权与提问、取消、差异审查、冲突保护、验证和用量展示。
- 新增随附 Python 的 Windows 安装包构建、依赖锁定和本地模拟 API 端到端测试。
- 修正桌面进程启动 Git 快照时继承标准输入/控制台导致的阻塞；验证快照计算移出异步事件循环；无 Git 时使用完整文件枚举。
- npm 增加 `eca` 命令，保留 `ecs`。独立干净 Windows、非管理员及升级/卸载矩阵以桌面验收报告为准，不因打包成功宣称全部通过。

## Unreleased — 持续执行与模型输出额度

- 主 Agent 默认不限响应轮数和输出截断恢复次数，显式正整数上限继续有效，Ctrl+C 可中断。
- 已知官方 DeepSeek 模型采用模型对应的输出/上下文默认值，配置与命令行显式值优先。
- 添加四个额度命令行选项；子 Agent 仍保留自己的轮数限制。

## 0.20.0 — 安装包整合与发布验收

- 整合下列 Skills、LSP、协作验收、后台进程及联网源码升级，统一 npm/Python 版本。
- 增加发布包白名单、摘要及模块校验；独立安装验证覆盖会话恢复。
- 加入 Windows/Linux CI 发布检查（尚待远端运行）；本机全局 ecs 已升级。
- 验证与已知边界见 docs/RELEASE-0.20.0.md；仍为本地分发，未发布 npm registry。

## Unreleased — Skills、LSP 重命名与协作验收

- 项目/用户 SKILL.md 加载、按任务选择和显式 `/skill` 调用，保留工具授权限制。
- LSP 重命名预览、UTF-16 位置校验、全目标冲突检查、逐文件修改日志及修改后诊断。
- 根会话共享请求额度（含重试与摘要），串行委派可附验收命令，失败交回主 Agent。
- 增加单模型与 Worker-first 配对评测入口；未据机制测试声称真实模型成功率提升。

## Unreleased — 会话内后台进程

- 新增五个 `process_*` 工具与 `/run`、`/jobs`、`/logs`、`/stop` 命令，可在模型后续回合继续使用开发服务。
- 启动前展示命令并请求主机执行授权；Docker 和子 Agent 禁用。日志有界，最多四个并发任务，默认存活 600 秒，正常关闭时清理。
- 日志匹配与真实健康检查明确区分；不支持崩溃恢复、跨会话重连或脱离父进程的守护服务。源码功能尚未更新到全局安装包。

## 0.19.0 — 首次配置、连接诊断与新版安装包

- 新增 `ecs --configure` 单 API 配置向导：保留已有配置，支持环境变量和可选的隐藏密钥输入，保存前确认，不把密钥写入 TOML。
- 新增显式 `ecs --doctor --check-api`，支持三种协议的一次有界请求，区分鉴权、限流和连接问题，不显示服务商响应原文、不自动重试。
- npm/Python 版本统一升至 0.19.0，安装包包含下述恢复、上下文、Docker 实测与大仓库定位改动。包仍为本地分发，未发布 npm registry。
- 实际独立安装暴露 SOCKS 代理依赖缺失，正式加入 `httpx[socks]`，并为缺失代理支持提供脱敏错误。
- 全量 280 passed、6 skipped；npm 启动器 7 项通过，配置/诊断专项 15 项通过。真实默认 API 探针返回 401，未把鉴权失败记为连通成功。

## Unreleased — 大仓库关联定位

- 全量回归 273 passed、6 skipped（179.27 秒）；最后补充根路径拒绝后，定位专项 7 项再次通过。跳过为未开启的 Docker/MCP 可选验收，本轮未调用模型 API。
- 新增 `code_relations` 与 `/related SYMBOL`：返回定义、Python 调用/导入位置和测试文件标识；明确同名、别名、动态调用及语法版本限制。
- `code_search`、`repo_map` 支持相对目录/文件筛选，增量索引报告复用、读取量、删除量和解析降级。
- 修复全文索引逐文件按路径删除造成的重复扫描，改为事务内读取 rowid 后定点删除，并增加关系表路径索引。
- 增加重命名、删除、真实分支切换、目录边界和语法降级回归；DeerFlow 4,014 文件仓库三项定位任务通过，详见 [定位验收](docs/REPOSITORY_NAVIGATION.md)。仍未验证模型驱动的大仓库跨文件修改成功率。

## Unreleased — 真实隔离验收与取消状态

- 开启全部 Docker 实测后的全量回归：271 passed、1 skipped（174.79 秒）；5 项真实容器测试通过，无遗留 ECA 容器，未调用模型 API。
- Windows/WSL2 上完成真实容器边界、超时和取消清理专项；通过 inspect 核对资源限制，增加 NoNewPrivs 验证和缺失镜像拒绝执行测试。
- 沙箱取消明确记录 `cancelled`，与独立清理状态一起持久化；引擎不可用时提示 Windows 开始菜单启动，不自动启动或重置 Docker。
- 修复验收脚本对 Docker 错误大小写和非 root 路径访问拒绝的误判。环境、首次失败和复测证据见 [Docker 验收](docs/DOCKER_ACCEPTANCE.md)。

## Unreleased — 供应商上下文恢复与隔离验收

- 明确的 HTTP 上下文超限拒绝触发一次缩小预算和压缩恢复；保留失败请求账本与完整历史，不重放工具。
- 新增显式开启的真实 Docker 验收，覆盖文件/网络/用户权限边界、超时与取消清理；默认不拉取镜像。
- 离线全量 266 passed、5 skipped，其中 3 项为未开启的真实 Docker 验收，不能算作隔离验收通过。

## Unreleased — 长任务恢复

- 最终全量回归 261 passed、2 skipped；本轮未调用真实模型 API。

- 每次持久化保存有界任务检查点，包含需求摘录、任务状态、近期观察与验证日志位置。
- 恢复后的首次运行核对曾读写文件，报告变化、缺失、未核实文件及过期验证和不确定操作；不自动执行命令。
- 新增 `/checkpoint`；恢复信息参与上下文预算，保留旧文件哈希以继续阻止覆盖用户修改。
- 增加模型超时、上下文预算失败、文件变化及真实子进程退出回归。详见 [恢复说明](docs/SESSION_RECOVERY.md)。

## Unreleased — v0.19 验证与修复升级

- 全量 257 passed、2 skipped；迁移实测 3 次完成均通过，另有 1 次中断未完成。完整边界见 [验证记录](docs/VALIDATION-v0.19.md)。

- 新增同源码同诊断重复失败停止、检查回归标记、命令日志关联和 CLI 停止原因。
- suite v4 增加旧数据库迁移任务，共 14 项；历史 v3 实测单独保留。
- 前期固定任务扩展至 13 项：新增 SQLite 订单幂等、取消恢复库存、整批事务回滚，检查跨连接持久化与原有行为。
- 评测接入实际验证工作流，记录首次验证结果和全部修复轮次。
- suite 升至 3，明确测试文件保护和 batch 请求体契约；运行时和 npm 包仍为 v0.18.0。
- DeepSeek 三任务各三次：v2 原契约 1/9；明确契约后 v3 为 9/9、69 次请求，无人工修补；原失败保留，非运行时能力提升对照。见 [实测记录](docs/BASELINE-SQLITE-2026-10-18.md)。
- 用法和边界见 [升级说明](docs/UPGRADE-v0.19.md)。

## 0.18.0 — 2026-10-18

- 新增 10 项固定编码任务评测，复用已有验收并加入接口迁移、用户改动保护、读取失败恢复、压缩与配置解析。
- 自动生成任务结果与总体 JSON/Markdown 报告，保存源码指纹、参数、请求用量、费用完整性与失败项。
- 真实模型运行显式启动；默认离线测试只检查评测器。取消后保留已完成结果与未运行计数。
- 首轮 DeepSeek Flash 基线 10/10、87 次请求、0 次人工介入；单次小型场景结果，未进行竞争产品对照，费用未知。
- 评测器专项 6 passed、npm 7 passed。全量首跑 249 passed、2 skipped、1 项 MCP 测试启动时序失败；改为事件同步后 MCP 模块 9 项复测通过，生产 MCP 代码未改动。
- 用法与真实基线见 [v0.18](docs/UPGRADE-v0.18.md)。

## 0.17.0 — 2026-10-18

- 新增 `edit_many`：同一原文件上预检所有替换，拒绝重叠与依赖前序结果的替换，一次写入与撤销。
- 编辑支持唯一完整多行片段的行尾空白容错；保留缩进、内部空格与标点，支持 `match_mode=exact` 关闭容错。
- 会话保留最近读取/保存文件的字节摘要，拒绝覆盖已检测到的外部修改；审批后继续检查文件是否变化。
- 编辑失败提供有限的候选行与附近文本，供模型定向重读。
- Python 回归 244 passed、2 skipped；npm 启动器 7 passed，本地 v0.17 tgz 构建及源码一致性校验通过。
- 使用方法、边界与验证记录见 [v0.17](docs/UPGRADE-v0.17.md)。

## 0.16.0 — 2026-10-18

- 上下文加入 token 预算、输出/安全预留和完整请求预检；实际输入用量用于向上校准，模型档案分别配置窗口。
- 摘要输入保留需求与旧检查点，以合法 JSON 节选大段观察；失败保留历史与旧摘要。
- 新增 `/context` 本地估算，计费继续使用 `/usage` 的供应商用量。
- Python 回归 231 passed、2 skipped；npm 启动器 7 passed，v0.16 本地 tgz 构建及源码一致性校验通过。
- 使用方法、估算边界与验证记录见 [v0.16 升级说明](docs/UPGRADE-v0.16.md)。

## 0.15.0 — 2026-10-18

- 新增 npm 本地分发包与 `ecs` 启动命令，携带版本匹配的 Python wheel，首次运行创建独立环境。
- Python 包新增 `ecs` 入口，保留 `eca`；启动器透传原有参数、工作目录与退出码。
- 提供 `--setup`、无需初始化的 `--version`、摘要校验、初始化锁和 G 盘优先缓存。
- npm 安装阶段不执行 postinstall。此版仍需 Node.js 20+ 和 Python 3.11+，未公开发布 registry。
- Python 全量 222 passed, 2 skipped；Node 7 项通过，Windows 实际 tgz 安装与启动通过。
- [安装方式](docs/NPM_INSTALL.md) · [验证记录](docs/UPGRADE-v0.15.md)。

## 0.14.0 — 2026-10-17

- 显式 `--worker-first PROFILE`：先由已启用的 Worker 执行，再运行用户指定检查。
- 普通检查失败时，按已有 `--repair-attempts 0..3` 预算交给当前主模型修复，再检查；默认零次。
- Worker 未完成、取消、超时或未知检查结果不自动接手重跑。持久记录 Worker、检查轮次与接手原因。
- 全量 222 passed, 2 skipped；25 个运行时模块与安装包一致。用法及共享目录边界见 [v0.14](docs/UPGRADE-v0.14.md)。

## 0.13.0 — 2026-10-17

- 可选 `agent.worker_profiles` 白名单；默认空列表，单 API 使用方式不变。
- 子 Agent 可独立选择模型档案，支持混合模型并行、独立凭据和现有用量归集；不静默回退收费模型。
- `/models` 显示 Worker 是否启用；本地模型需要自行安装并提供兼容工具调用服务。
- 全量回归 216 passed, 2 skipped，25 个运行时模块与 wheel 一致。使用方法和边界见 [v0.13](docs/UPGRADE-v0.13.md)。

## 0.12.0 — 2026-10-17

- 单个标识符搜索优先返回大小写一致的符号定义，附定义行号；旧索引自动补齐符号表。
- 索引扫描支持协作取消，未提交的更新整体回滚，等待后台线程退出后再返回。
- Docker 执行前持久保存容器名称和本地 endpoint；清理结果独立记录，新增只读 `/sandbox` 查看入口。
- 保留未确认清理记录，不自动重放或删除历史容器。Docker 实机隔离仍待验收。
- 全量回归 209 passed, 2 skipped；wheel 的 25 个运行时模块与源码一致。详情见 [v0.12](docs/UPGRADE-v0.12.md)。

## 0.11.0 — 2026-10-17

- 新增可选实验性 Docker Shell 隔离：本地 Linux 引擎、禁网、受限资源、过滤后的只读源码副本、命令写入丢弃、取消清理和容器内超时。
- 后端不可用不回退宿主机；Docker 模式禁用 MCP/LSP，恢复会话保留隔离设置。
- 新增 SQLite FTS5 增量代码索引、Python AST/其他语言词法摘要，提供 code_search/repo_map 工具及 `/search`、`/map`。
- 验收指纹容量提升到 20,000 文件 / 50 MB；超限保持未知。关闭宿主机源码枚举的 Git fsmonitor hook。
- 真实容器验收本机未运行，不能把参数测试视为隔离证明。详见 [v0.11](docs/UPGRADE-v0.11.md)。
- 全量 204 passed, 2 skipped；3,000 文件索引回归通过，wheel 的 25 个运行时模块与源码一致。

## 0.10.0 — 2026-10-17

- `--verify-command` 支持最多 10 项顺序检查，首个失败后停止。
- 新增显式 `--repair-attempts 0..3`：保留原任务要求，失败后有界修复并重跑整组检查。
- 取消、超时、拒绝和未知结果不自动重跑；整组结果要求同一源码指纹。
- 持久记录各轮结果；JSONL 与 `/progress` 显示整组状态，恢复会话不会自动重放。
- 用法与边界见 [v0.10](docs/UPGRADE-v0.10.md)。
- 最终全量回归 188 passed, 1 skipped；安装包 23 个运行时模块与源码逐字节一致。

## 0.9.0 — 2026-10-17

- 最近 12 项文件/命令观察持久保存，压缩后继续提供给模型，新增 `/progress` 汇总入口。
- 三种模型协议识别明确的输出上限；丢弃不完整回复，最多两次要求拆分后续操作，保留原轮数限制与请求账本。
- 新增 `/verify COMMAND` 与 `--verify-command`，复用 Shell 审批、模式限制和日志；失败退出码 3，支持快照失效、无测试和取消状态。
- 使用方法与实际边界见 [v0.9 升级记录](docs/UPGRADE-v0.9.md)。
- 全量离线回归 178 passed, 1 skipped；wheel 的 22 个运行时模块与源码一致。

## 0.8.2 — 2026-10-17

- 修复完整读取 AGENTS.md 后仍重复阻断后续写入的问题，保留同批次、部分读取、截断和规则变更保护。
- 新增 StockFlow 多模块 FastAPI / SQLite 项目验收契约及真实模型构建、修复、恢复运行器。
- 相关规则/删除专项 12 项通过，全量 166 passed, 1 skipped。

## Unreleased

- 新增显式运行的 DeepSeek 在线验收工具，使用独立 Git fixture、外部断言与测试变异检查，覆盖五类编码流程。
- 验收报告记录用量、可选价格快照、运行耗时、子任务状态、工具配对及 Git 暂存区保护。
- 新增离线验收器测试；在线任务不加入默认 pytest 或 CI。

## 0.8.1 — 2026-10-17

- 新增带差异审批与持久记录的单文件 delete 工具，支持删除审阅、接受与字节级撤销。
- 并行子 Agent 返回 deleted 状态；父会话可合并有完成记录的删除，沿用基线冲突检查。
- 拒绝二进制文本变更，补齐空文件删除差异、审批期间修改与删除失败恢复测试。
- 使用范围及限制见 docs/UPGRADE-v0.8.1.md。

## 0.8.0 — 2026-10-17

- 借鉴 Pi 子任务与模型配置、OpenCode LSP/MCP 生命周期设计，保持本项目的审批与隔离边界。
- 新增独立并发上限与排队状态，修复初始化失败影响同批任务及状态读取触发错误恢复的问题。
- 子任务返回失败原因与改动清单；准备失败与取消排队任务均持久记录。
- LSP 改为会话内复用、didChange 同步、push/pull 诊断、版本检查及显式断开，新增 implementation 查询。
- 新增命名模型配置与安全的接口/密钥切换、会话恢复；Responses 推理项仅在同模型/接口复用。
- MCP 真实存活状态、每服务操作队列、取消隔离与下一次明确操作重连。
- 配置、参考资料及未实现边界见 docs/UPGRADE-v0.8.md。


## 0.7.0 — 2026-10-17

- 新增有数量/轮数/超时限制的并行子任务，独立源码快照、冲突检查与可撤销文件合并。
- 隔离子任务在执行层禁用 Shell/MCP/LSP 与递归委派，恢复后保持隔离。
- MCP 连接所有者任务、显式断开、资源/模板读取和提示词获取，保留逐次审批与无重放原则。
- 新增 Responses 流式协议、reasoning 项回传和请求用量统计；支持可选 reasoning_effort。
- 新增经审批的 stdio LSP 定义、引用、悬停、符号及 pull diagnostics 查询。
- 边界：无 OS 沙箱、OAuth、Git worktree 合并或 LSP 自动重命名。见 docs/UPGRADE-v0.7.md。


## 0.6.0 — 2026-10-17

- Add optional official-SDK MCP stdio/Streamable HTTP tool discovery and invocation with per-operation approval, bounded timeouts, schema validation and no automatic replay.
- Add bounded child agents with independent durable sessions, sequential execution, inherited file/Shell approvals and parent mode ceilings. Children cannot delegate or invoke MCP.
- Persist each model request attempt, including retries, cancellation, compaction and child work. Normalize provider cache usage and calculate Decimal subtotals from per-request price snapshots; unknown or incomplete usage/prices remain explicit.
- Add `/mcp`, `/agents`, `/usage`, headless `--usage`, and server-scoped `--allow-mcp`.

## 0.5.2 — 2026-10-17

- Pass max_output_tokens to OpenAI-compatible requests, matching the native provider's output cap.
- Tell the model its remaining response budget and encourage direct reads, batched independent reads and timely final reporting; no additional summary request is added.
- Warn on repeated identical tool observations while still executing fresh calls; preserve JSON results and the existing repetition stop guard.
- Label recognized unittest/pytest zero-test output as no_tests, preserve the actual exit code, and exclude it from successful-command memory. This is a bounded-output heuristic, not a universal test-runner parser.

## 0.5.1 — 2026-10-17

- Replace configuration-only doctor output with structured, read-only local readiness checks and actionable warnings.
- Keep session listing and file review/undo available with malformed model configuration; avoid initializing state when listing an empty project.
- Reject unknown agent options, invalid key-variable types, invalid endpoint ports and credential-bearing query/fragment URLs.

## 0.5.0 — 2026-10-17

- Integrate existing memory-core SQLite/FTS through a source-qualified CLI adapter; package the core with ECA.
- Capture successful test-command evidence with session/action provenance and bounded project fingerprints; exclude stale records from new-session context.
- Add `/memory`, `/remember`, `/forget` and optional automatic-memory opt-out.
- Load hierarchical AGENTS.md rules before file edits; defer mutations until rules have reached a subsequent model request.
- Keep legacy research databases isolated and assistant claims out of automatic project memory.

## 0.4.0 — 2026-10-17

- Persist before/after snapshots before file-tool writes; review, accept and undo individual edits without resetting the Git index or overwriting later edits.
- Add interactive and headless review commands; undo updates conversation context and supports interrupted write/undo records.
- Automatically summarize older context while retaining recent complete tool exchanges and the full archive.
- Add bounded, cancellable transient model retries before text output, persisted stop reasons and `/continue`.
- Keep shell side effects outside file undo; document snapshot scope and model usage costs.

## 0.3.0 — 2026-10-17

- Native Anthropic Messages streaming and normalized tool-use history, selected by config/environment/CLI.
- Strict completion checks before tools execute; output budget, usage, credential isolation and protocol diagnostics.
- Native protocol fixtures plus real HTTP CLI execution and cross-process session recovery tests.
- Preserve upstream memory research and legacy entry point; test both runtimes together.
- CI template retained under docs because current GitHub credentials lack workflow scope.

## 0.2.0 — 2026-10-17

- New `eca` package and CLI; original application retained as `legacy_main.py`.
- Native async streaming with complete-response validation and local endpoint proxy bypass.
- SQLite sessions and tool journal, project isolation and exclusive process lock.
- Code/Plan/Chat tools enforced at dispatch; explicit file and shell approvals.
- Atomic file writes, unique edits, conflict checks, bounded search and command output.
- Awaited cancellation and subprocess cleanup, repetition and turn limits.
- Session/model/profile/mode/permission commands, context summary, Git diff and Markdown export.
- Headless tasks and JSONL events; installable wheel and Windows/Linux CI configuration.
- Offline regression tests and real localhost HTTP streaming CLI integration test.

See docs/UPGRADE-v0.2.md for migration, preserved history and limitations.
