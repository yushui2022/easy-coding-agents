=# Easy-Coding-Agent

一个基于 Python 的高性能、任务驱动型自主 AI 编程助手。架构设计深度对标 Claude Code，并针对 Windows 环境进行了极致优化。

## 核心亮点 (Key Features)

*   **自主控制回路 (Autonomous Control Loop)**: 不同于传统的问答式 Agent，本系统采用 **Task-Driven** 架构。Agent 会自动规划任务清单，并自主循环执行，直到所有任务完成，无需人工反复干预。
*   **三层记忆系统 (3-Tier Memory Architecture)**:
    *   **Short-Term (Buffer)**: 实时活跃显存，具备 Token 监控与防溢出机制。
    *   **Medium-Term (AU2 Compressor)**: 智能上下文压缩算法，自动将陈旧对话"脱水"为高维摘要。
    *   **Long-Term (Archivist)**: 基于 `MEMORY.md` 的持久化经验库，自动记录用户偏好与关键决策。
    *   **Session Persistence (会话持久化)**: 自动保存对话快照到 `memory/sessions/`，支持程序重启后的**断点续传**，从此告别"金鱼记忆"。
*   **高性能异步引擎 (Async Engine)**:
    *   **h2A 架构**: 双重缓冲异步消息队列，确保 UI 响应如丝般顺滑。
    *   **wu 流式处理**: 实时流式输出，打字机效果。
*   **Windows 原生优化**:
    *   完美解决 PowerShell 下的 ANSI 颜色乱码问题。
    *   **智能编码适配**: 自动识别系统默认编码 (如 GBK)，防止命令输出乱码。
    *   **Prompt 适配**: 内置 Windows 命令指引，避免使用不兼容的 Bash 语法。
    *   `patch_stdout` 深度集成，确保在输入时日志不会打断提示符。
*   **交互式 CLI (Interactive CLI)**:
    *   **可中断执行**: 支持 Ctrl+C 随时暂停 Agent，回到主菜单，而不会丢失当前上下文。
    *   **Human-in-the-loop**: Agent 可通过 `ask_user` 工具主动向用户提问，或通过 `ask_selection` 展示交互式菜单（支持上下键选择与自定义输入）。
    *   **任务进度条**: 实时显示任务完成度，让等待不再焦虑。
    *   **分阶段执行工作流 (Phased Workflow)**: 采用 "规划 -> 确认 -> 执行 -> 验收" 的严谨流程，拒绝“一步到位”的幻觉，确保每个阶段都在用户掌控之中。
    *   **斜杠命令补全**: 输入 `/` 即可弹出命令下拉列表，支持描述提示与子命令补全。
    *   **自定义 Agent 视觉标签**: 当前激活的 Agent 会显示在输入框前的彩色标签中。
    *   **上下文窗口计数器**: 底部状态栏显示 `Context: XX%`，实时提示当前上下文占用比例（<50% 绿，50–79% 黄，≥80% 红）。

## 最新更新 (Latest Updates - 2026.02.06)

### 1. 交互式选择菜单 (Interactive Selection Menu)
我们引入了类似 Claude Code 的现代化 CLI 交互体验：
*   **键盘操作**: 使用 `↑` / `↓` 箭头键在选项间导航，`Enter` 确认。
*   **智能兜底**: 提供 "自己选择 (Self Choice)" 选项，允许用户在预设选项不满足需求时直接输入自定义指令。
*   **技术实现**: 基于 `questionary` 库构建，通过依赖注入 (`AgentContext`) 集成到核心引擎，确保架构整洁。

### 2. 分阶段规划-确认-执行 (Phased Plan-Confirm-Execute)
为了解决 AI "自作主张" 或 "频繁打断" 的问题，我们重构了 Agent 的行为准则 (`prompts.py`)：
*   **Phase 1: Planning**: 收到复杂指令（如“开发App”）时，Agent 首先生成当前阶段的 Todo List（如仅前端）。
*   **Phase 2: Confirmation**: 必须使用交互式菜单向用户展示规划，并等待确认（"是否开始执行？"）。
*   **Phase 3: Execution**: 获得授权后，Agent 将**自主闭环**执行该阶段的所有任务，期间不再进行微观打断。
*   **Phase 4: Checkpoint**: 阶段完成后，Agent 会汇报成果，并询问是否进入下一阶段（如“前端已完成，继续后端？”）。

### 3. 引擎稳定性增强 (Engine Robustness)
*   **空响应防御**: 修复了 ModelScope API 偶尔返回空数据包导致的无限重试循环问题。增加了显式的错误提示与退避重试机制。
*   **死循环修复**: 解决了交互式工具 (`ask_selection`) 返回结果后，Agent 未能及时触发下一轮动作导致的“提问死循环”。
*   **依赖注入重构**: 移除了 `input_func` 的全局依赖，现在所有交互函数均通过 `AgentContext` 优雅注入，提升了代码的可测试性。

*   **智能代码检索 (Smart Search)**:
    *   **Ripgrep 集成**: 采用 Rust 编写的 `rg` 替代传统 Grep，搜索速度提升 10 倍以上。如果未安装，自动降级为安全的原生 Python 实现（具备 OOM 保护，自动跳过 >1MB 文件）。
    *   **模块化架构**: 采用 Engine/Template/Parser 分离设计，支持平滑扩展。
    *   **多语言模板库**: 内置 Python, JS, TS, Go, Java, C++, Rust 等 7 种语言的 10+ 种常用正则模板 (如 `def`, `class`, `impl`, `assignment` 等)。
    *   **语法感知 (Syntax-Aware)**: 预留 Tree-sitter 接口，支持未来升级为 AST 级精准搜索。

### 4. 记忆系统全面升级 (Memory System Overhaul 2.0)
*   **混合记忆策略 (Hybrid Memory Strategy)**:
    *   **FIFO 滑动窗口**: 优先使用高效的滑动窗口策略（丢弃最旧对话），确保极速响应。
    *   **AU2 兜底**: 仅在必要时触发 LLM 压缩算法，降低幻觉风险。
    *   **32k 上下文**: 默认 Token 限制提升至 32k，适配现代大模型。
*   **Markdown 持久化**: 会话文件从 `.json` 迁移至 `.md`，大幅提升可读性与 Debug 效率。

### 5. 稳定性防护 (Stability Guards)
*   **死循环熔断**: 新增 `Repetitive Tool Call Guard`，智能拦截重复的工具调用。针对交互式工具 (`ask_user`/`ask_selection`) 引入了**智能注意力注入**，防止 Agent 忽略用户回答而陷入提问死循环。
*   **交互式干预**: 当检测到非交互式工具的死循环时，Agent 会主动弹出选择菜单 (Stop/Retry/Skip)，将控制权交还给用户。
*   **空响应重试**: 增强了 API 调用层的鲁棒性，自动处理 ModelScope 偶尔返回的空包。

### 6. 用户体验优化 (UX Improvements)
*   **Session 极速启动**: 优化了会话加载机制，启动时仅读取最近 50 条消息，有效防止因历史记录过长导致的启动卡顿与上下文干扰。
*   **日志智能瘦身**: `session_*.md` 存档文件现已支持智能过滤，仅保留最近 20 条消息，并自动移除冗长的 Tool 输出与 JSON 参数，只保留 User 与 Agent 的核心对话，让日志阅读如聊天记录般清爽。
*   **交互优化**: `ask_selection` 支持 "Self choice" 选项，允许用户直接输入自定义指令。

### 7. 智能搜索使用指南 (Smart Search Guide)

本系统集成了强大的代码搜索工具 `smart_search`，支持以下高级特性：

1.  **场景化模板 (Scenario Templates)**
    无需记忆复杂的正则表达式，直接使用自然语言场景：
    *   `template="def"`: 查找函数定义 (Python/JS/Go 等)
    *   `template="class"`: 查找类/结构体定义
    *   `template="assignment"`: 查找变量赋值
    *   `template="call"`: 查找函数调用
    *   **示例**: `smart_search(query="process_data", template="def", lang="python")`

2.  **语法级范围扩展 (Scope Expansion)**
    基于 **Tree-sitter** 的 AST 解析能力，不仅仅返回匹配的那一行，而是智能返回整个函数或类的代码块。
    *   **参数**: `expand_scope=True`
    *   **效果**: 自动识别并读取匹配行所属的完整函数体。
    *   **示例**: `smart_search(query="Engine", template="class", expand_scope=True)`

3.  **多语言支持**
    目前完美支持: `python`, `javascript`, `typescript`, `go`, `java`, `cpp`, `rust`。

### 8. 模式切换与 UI 升级 (Mode Switching & UI 2.0)
*   **三种专属模式**: 
    *   **Plan Mode**: 专注于架构规划与需求分析，禁止修改代码，确保 "三思而后行"。
    *   **Code Mode**: 全功能开发模式，自主执行复杂任务。
    *   **Chat Mode**: 纯对话模式，用于问答与咨询，避免副作用。
    *   **快捷切换**: 使用 `Shift+Tab` 键在输入框实时切换模式。
*   **Splash Screen**: 重新设计了启动画面，包含 ASCII Logo 与每日 Tips。
*   **动态提示词**: 系统提示词 (System Prompt) 会根据当前模式实时调整，确保 Agent 行为符合预期。
*   **UI 状态栏**: 底部状态栏实时显示当前模式与颜色指示。

### 9. 自定义 Agent 系统 (Custom Agents)
*   **创建与扩写**: 交互式创建界面（名称/描述/颜色），自动扩写为完整 Agent 定义（角色、能力、行为准则、对话风格、限制条件、使用场景、注意事项）。
*   **结构化预览**: 创建后即时展示结构化预览，支持按 ID 再次预览。
*   **调用与管理**: 支持 `/agent` 命令与 `@AgentName` 快捷方式，包含启用/禁用、编辑、删除、分享。
*   **状态可视化**: 底部状态栏与输入框提示均显示当前 Agent 标签与颜色。
*   **使用限制**: 单个用户最多创建 20 个自定义 Agent。

### 10. 命令行体验增强 (CLI Productivity)
*   **斜杠命令补全**: 输入 `/` 即显示命令下拉框，支持描述提示与子命令补全。
*   **命令别名**: 支持 `/create` 与 `/list` 作为 `/agent` 的快捷入口。

## 项目结构 (Architecture)

*   **`core/`**: 核心引擎
    *   `engine.py` ([core/engine.py](core/engine.py)): **n0 主循环**，负责调度任务与工具。包含双缓冲队列与自主执行逻辑。
    *   `task.py` ([core/task.py](core/task.py)): **任务管理系统**，Agent 的"良心"与"导航仪"。
    *   `stream.py` ([core/stream.py](core/stream.py)): **wu 流式处理器**，支持指数退避重试 (Exponential Backoff) 与网络异常保护。
    *   `config.py` ([core/config.py](core/config.py)): **配置中心**，负责环境变量加载与启动时校验 (Startup Validation)。
*   **`memory/`**: 记忆系统
    *   `short_term.py` ([memory/short_term.py](memory/short_term.py)): 短期记忆 Buffer。
    *   `medium_term.py` ([memory/medium_term.py](memory/medium_term.py)): AU2 压缩算法实现。
    *   `long_term.py` ([memory/long_term.py](memory/long_term.py)): 长期记忆文件管理 (基于 `MEMORY.md`)。
    *   `session_store.py` ([memory/session_store.py](memory/session_store.py)): 会话序列化与持久化存储 (Markdown 格式)。
    *   `sessions/` ([memory/sessions/](memory/sessions/)): 存放历史会话 Markdown 文件。
*   **`tools/`**: 工具链
    *   `search/` ([tools/search/](tools/search/)): **(New)** 智能搜索模块。
        *   `api.py` ([tools/search/api.py](tools/search/api.py)): 工具注册入口。
        *   `engine.py` ([tools/search/engine.py](tools/search/engine.py)): 底层搜索实现 (Ripgrep + Fallback)。
        *   `templates.py` ([tools/search/templates.py](tools/search/templates.py)): 多语言正则模板库。
        *   `parser.py` ([tools/search/parser.py](tools/search/parser.py)): Tree-sitter 语法分析器。
    *   `filesystem.py` ([tools/filesystem.py](tools/filesystem.py)), `shell.py` ([tools/shell.py](tools/shell.py)): 基础能力。
    *   `todo.py` ([tools/todo.py](tools/todo.py)): 任务管理工具。
    *   `interaction.py` ([tools/interaction.py](tools/interaction.py)): **(New)** 交互式工具 (`ask_user`)。
    *   `agents.py` ([tools/agents.py](tools/agents.py)): **(New)** 自定义 Agent 管理与调用工具。
*   `utils/`
    *   `logger.py` ([utils/logger.py](utils/logger.py)): 日志模块。
    *   `ui.py` ([utils/ui.py](utils/ui.py)): **(New)** UI 渲染模块 (Splash Screen, Tips)。
*   **`workspace/`** ([workspace/](workspace/)): **(New)** 默认的输出目录，用于存放 Agent 生成的临时代码或文件，避免污染根目录。
*   **`AI_CODER_GUIDE.md`** ([AI_CODER_GUIDE.md](AI_CODER_GUIDE.md)): **(New)** 专为 AI 开发者准备的架构指南与交接手册。
*   **`MEMORY.md`** ([MEMORY.md](MEMORY.md)): **(New)** 项目的“宪法”与长期记忆库，记录用户偏好与关键架构决策。

## 快速开始 (Quick Start)

1.  **环境准备**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **配置 API**:
    复制 `.env.example` 为 `.env`，并填入必要的配置：
    ```ini
    MODELSCOPE_API_KEY=ms-xxxxxxxx
    MODEL_NAME=Qwen/Qwen2.5-Coder-32B-Instruct
    
    # 可选配置
    MAX_HISTORY_TOKENS=32000 # 默认提升至 32k 以适配复杂任务
    MAX_AUTONOMOUS_TURNS=30  # Agent 自主运行的最大轮数
    LLM_TEMPERATURE=0.1      # 模型的创造力 (0.0-1.0)
    ```

3.  **运行**:
    *   **推荐**: 双击 `run_agent.bat` (已包含 Windows 编码修复)。
    *   或者终端运行: `python main.py`

## 使用指南 (Usage)

启动后，您可以直接用自然语言下达复杂指令，例如：

> "帮我分析 core 目录下的代码结构，并生成一份详细的 API 文档到 docs 目录中。"

Agent 将会自动：
1.  **规划**: 生成 Todo List (读取文件 -> 分析代码 -> 生成文档)。
2.  **执行**: 自动逐步执行每个任务。
3.  **记忆**: 如果对话过长，自动压缩上下文；如果有些偏好（如"不要用中文写注释"），它会记住并写入长期记忆。

## 贡献 (Contributing)

如果您是 AI 开发者，请务必先阅读 [AI_CODER_GUIDE.md](AI_CODER_GUIDE.md) 以了解核心架构与扩展规范。
