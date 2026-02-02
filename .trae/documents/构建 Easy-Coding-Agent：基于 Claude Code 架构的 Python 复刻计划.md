我将为您构建 `easy-coding-agent`，一个基于 Python 的高性能 AI 编程助手，完全对标您描述的 Claude Code 架构，并接入智谱清言 API。

项目将采用模块化设计，将您提到的核心概念映射为具体的 Python 实现：

## 1. 核心架构设计 (Architecture)

我们将项目拆分为以下核心模块，对应您提到的技术点：

*   **`core/engine.py` (对应 n0 & h2A)**:
    *   **核心执行框架**: 基于 `asyncio` 的事件循环，实现非阻塞的主控逻辑。
    *   **双重缓冲队列**: 使用 `asyncio.Queue` 实现 `ActionQueue` (用户指令/工具结果) 和 `ResponseQueue` (模型输出)，确保高吞吐和零延迟响应。
*   **`core/stream.py` (对应 wu)**:
    *   **流式生成器**: 封装智谱 API 的 `stream=True` 模式，实现打字机效果的实时代码输出。
    *   **解析器**: 实时分离文本内容与工具调用指令。
*   **`core/memory.py` (对应 wU2)**:
    *   **上下文压缩器**: 实现基于滑动窗口 + 摘要的压缩策略。
    *   **"8段式"模拟**: 将长历史记录分段总结（如：用户意图、关键决策、文件变更等），保留最近对话的完整性，确保压缩比和上下文连贯性。
*   **`tools/` (全场景工具链)**:
    *   `filesystem.py`: 增强版 `Read`/`Write`，支持大文件分页读取。
    *   `search.py`: 封装 `glob` 和 `grep` (支持正则)，提供无需 RAG 的精准搜索。
    *   `shell.py`: 安全的 `Bash` 命令执行器。
    *   `web.py`: 简单的 `WebFetch` 实现。
*   **`input/parser.py` (输入转换)**:
    *   **AST 引导**: 在 System Prompt 中植入思维链（CoT）模板，引导模型先生成 `<plan>` 或 `<logic_tree>`，再生成代码，模拟 AST 逻辑闭环。

## 2. 技术选型 (Tech Stack)

*   **语言**: Python 3.10+
*   **异步框架**: `asyncio`
*   **LLM SDK**: `zhipuai` (智谱清言官方 SDK)
*   **UI/交互**: `rich` (用于漂亮的终端输出), `prompt_toolkit` (用于多行输入和命令历史)
*   **环境**: Windows (兼容)

## 3. 实施步骤 (Implementation Steps)

我们将分阶段完成构建：

### Phase 1: 基础框架搭建
1.  创建项目结构与虚拟环境。
2.  安装依赖 (`zhipuai`, `rich`, `prompt_toolkit` 等)。
3.  实现 **n0 主循环** 和 **h2A 异步消息队列** 的骨架代码。

### Phase 2: 工具链实现
1.  移植并增强 `nanocode` 中的基础工具 (`read`, `write`, `edit`)。
2.  实现 `grep` 和 `glob` 搜索工具。
3.  实现 `bash` 命令执行工具。

### Phase 3: 智谱 API 接入与流式处理 (wu)
1.  集成 `zhipuai` SDK。
2.  实现流式响应解析与 `rich` 终端实时渲染。
3.  实现 AST 风格的 System Prompt 设计。

### Phase 4: 记忆管理与压缩 (wU2)
1.  实现消息历史管理器。
2.  开发上下文压缩算法（自动触发摘要）。

### Phase 5: 整合与测试
1.  将所有模块串联。
2.  进行实际代码生成测试，验证逻辑闭环。

现在，我将开始执行 **Phase 1: 基础框架搭建**。