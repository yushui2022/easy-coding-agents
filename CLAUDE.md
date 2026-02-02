# CLAUDE.md - Long Term Memory & Preferences

## User Preferences
- **Documentation Sync**: 每次修改代码或添加新功能时，必须同步更新 `README.md` 和 `AI_CODER_GUIDE.md`。
- **Memory Usage**: 主动使用 `manage_core_memory` 工具将重要的知识、规则和经验保存到长期记忆 (`CLAUDE.md`) 中。

## Key Decisions
- **Architecture**: 采用 Task-Driven Control Loop 架构 (n0/h2A)。
- **Memory**: 采用三层记忆系统 (Short/Medium/Long Term) + Session Persistence (断点续传)。
- **Platform**: 针对 Windows (PowerShell) 进行深度优化 (ANSI/Encoding/VT100)。
- **UI/UX**: 
    - **Log Beautification**: 使用 Rich Panel 和 JSON Syntax Highlighting 展示工具调用。
    - **Log Suppression**: 强制屏蔽 `httpx`/`httpcore` 日志，仅保留关键业务日志。
    - **Localization**: 核心交互界面全面汉化。
    - **Smart Truncation**: 长文本参数（如代码写入）自动截断显示，避免刷屏。
- **Workspace**: 所有生成文件默认写入 `workspace/` 目录。
