# MEMORY.md - Long Term Memory (Project Constitution)

## User Preferences
- **Documentation Sync**: 每次修改代码或添加新功能时，必须同步更新 `README.md` 和 `AI_CODER_GUIDE.md`。
- **Memory Usage**: 主动使用 `manage_core_memory` 工具将重要的知识、规则和经验保存到长期记忆 (`MEMORY.md`) 中。
- **Coding Style**: 
    - 强制使用 Python 3.11+ 类型注解。
    - 核心逻辑必须异步 (Async/Await)。
    - 禁止在主循环使用 `time.sleep`。
    - 日志输出必须使用 `utils.logger` 和 `rich`。

## Optimization Roadmap (逐步优化计划)

### Phase 1: Robustness & Configuration (进行中)
- [x] **Config Refactoring**: 将 `max_turns`, `temperature` 等硬编码移至 `.env`。
- [x] **Startup Validation**: 在启动时检查必要环境变量 (API Keys)，避免运行时崩溃。
- [x] **Error Handling**: 增强 `StreamHandler` 的异常捕获，防止网络抖动导致 Agent 退出。

### Phase 2: Core Architecture Refinement (架构精炼)
- [x] **Dependency Injection**: 移除 `tools/todo.py` 中的全局变量 `_GLOBAL_TASK_MANAGER`，采用更优雅的上下文注入。
- [x] **Search Tool Upgrade**: 增强 `search/engine.py` 的 Fallback 机制，增加文件大小检查，防止读取大文件导致 OOM。
- [x] **Token Management**: 引入 `tiktoken` 或更准确的 Token 计数器，优化内存压缩触发时机。

### Phase 3: UX & Interactivity (体验升级)
- [x] **Non-blocking CLI**: 重构 `main.py` 的交互循环，支持在 Agent 运行时优雅中断 (Ctrl+C)。
- [x] **Progress Indication**: 恢复并优化任务进度条显示，使其不干扰日志输出。
- [x] **Interactive Tools**: 允许工具请求用户输入 (Human-in-the-loop)。
- [x] **Interactive Selection Menu**: 实现类似 Claude Code 的交互式菜单（questionary），支持上下键选择与自定义输入。

## Key Decisions
- **Architecture**: 采用 Task-Driven Control Loop 架构 (n0/h2A)。
- **Memory**: 采用三层记忆系统 (Short/Medium/Long Term) + Session Persistence (断点续传)。
- **Platform**: 针对 Windows (PowerShell) 进行深度优化 (ANSI/Encoding/VT100)。
- **UI/UX**: 
    - **Log Beautification**: 使用 Rich Panel 和 JSON Syntax Highlighting 展示工具调用。
    - **Log Suppression**: 强制屏蔽 `httpx`/`httpcore` 日志，仅保留关键业务日志。
    - **Localization**: 核心交互界面全面汉化。
    - **Smart Truncation**: 长文本参数（如代码写入）自动截断显示，避免刷屏。
    - **Interactive Selection**: 使用 `questionary` 库替代纯文本选项，提供更符合直觉的 CLI 交互体验。
- **Workspace**: 所有生成文件默认写入 `workspace/` 目录。

## Update
### Key Decisions / Legacy Issues
[From Session] Key technical decisions include choosing React.js for the front-end framework and using Figma for detailed UI/UX design. The project structure is divided into frontend, backend, and shared directories.


## Update
### Key Decisions / Legacy Issues
[From Session] Decided to follow a structured plan with clear phases and tasks. Chose to start with HTML and then progress to CSS, ensuring each step is completed before moving on to the next.


## Update
### Key Decisions / Legacy Issues
[From Session] Key technical decisions include using Flask for the backend framework, SQLite for the database, and SQLAlchemy for ORM. The frontend is built with HTML, CSS, and JavaScript.


## Update
### Key Decisions / Legacy Issues
[From Session] The project was divided into phases, starting with frontend planning and then proceeding to execution. The decision to modify the initial plan was made before confirming to proceed with generating the code.
