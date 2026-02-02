# Easy-Coding-Agent

一个基于 Python 的高性能、任务驱动型自主 AI 编程助手。架构设计深度对标 Claude Code，并针对 Windows 环境进行了极致优化。

## 核心亮点 (Key Features)

*   **自主控制回路 (Autonomous Control Loop)**: 不同于传统的问答式 Agent，本系统采用 **Task-Driven** 架构。Agent 会自动规划任务清单，并自主循环执行，直到所有任务完成，无需人工反复干预。
*   **三层记忆系统 (3-Tier Memory Architecture)**:
    *   **Short-Term (Buffer)**: 实时活跃显存，具备 Token 监控与防溢出机制。
    *   **Medium-Term (AU2 Compressor)**: 智能上下文压缩算法，自动将陈旧对话"脱水"为高维摘要。
    *   **Long-Term (Archivist)**: 基于 `CLAUDE.md` 的持久化经验库，自动记录用户偏好与关键决策。
    *   **Session Persistence (会话持久化)**: 自动保存对话快照到 `memory/sessions/`，支持程序重启后的**断点续传**，从此告别"金鱼记忆"。
*   **高性能异步引擎 (Async Engine)**:
    *   **h2A 架构**: 双重缓冲异步消息队列，确保 UI 响应如丝般顺滑。
    *   **wu 流式处理**: 实时流式输出，打字机效果。
*   **Windows 原生优化**:
    *   完美解决 PowerShell 下的 ANSI 颜色乱码问题。
    *   `patch_stdout` 深度集成，确保在输入时日志不会打断提示符。

## 项目结构 (Architecture)

*   **`core/`**: 核心引擎
    *   `engine.py`: **n0 主循环**，负责调度任务与工具。
    *   `task.py`: **任务管理系统**，Agent 的"良心"与"导航仪"。
    *   `stream.py`: **wu 流式处理器**。
*   **`memory/`**: 记忆系统
    *   `short_term.py`: 短期记忆 Buffer。
    *   `medium_term.py`: AU2 压缩算法实现。
    *   `long_term.py`: 长期记忆文件管理。
    *   `session_store.py`: 会话序列化与持久化存储。
    *   `sessions/`: 存放历史会话 JSON 文件。
*   **`tools/`**: 工具链
    *   `filesystem.py`, `shell.py`, `search.py`: 基础能力。
    *   `todo.py`: 任务管理工具。
*   **`workspace/`**: **(New)** 默认的输出目录，用于存放 Agent 生成的临时代码或文件，避免污染根目录。
*   **`AI_CODER_GUIDE.md`**: **(New)** 专为 AI 开发者准备的架构指南与交接手册。

## 快速开始 (Quick Start)

1.  **环境准备**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **配置 API**:
    复制 `.env.example` 为 `.env`，填入您的智谱 API Key。

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
