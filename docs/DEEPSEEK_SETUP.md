# DeepSeek Provider Setup

This project supports DeepSeek through the OpenAI-compatible client.

## Local `.env`

Keep real keys only in `.env`. Do not commit `.env`.

```ini
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_key_here
MODEL_NAME=deepseek-v4-flash
MAX_HISTORY_TOKENS=8000
MAX_AUTONOMOUS_TURNS=10
SIMPLE_TASK_TOOL_BUDGET=2
DEFAULT_TASK_TOOL_BUDGET=12
LLM_TEMPERATURE=0.1
DEBUG=false
```

DeepSeek uses:

```text
base_url = https://api.deepseek.com
```

## Smoke Test

```powershell
python -m pytest tests -q
python -m compileall core tools agent_memory_core memory tests benchmark\coding_memory
```

Then run the CLI:

```powershell
python main.py
```

Ask a small file-grounded question, for example:

```text
请读取 requirements.txt，然后用一句中文总结这个项目依赖。
```

Expected behavior:

- The agent reads the exact requested file.
- For this simple request, it should not start a broad project audit.
- It should answer from current-request evidence, not stale memory.

## Security Note

If an API key was pasted into chat, issue tracker, logs, or Git history, rotate it in the provider console. Removing it from `.env` is not enough after exposure.
