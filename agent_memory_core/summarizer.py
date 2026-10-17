from typing import Any, Dict, List, Tuple


ERROR_MARKERS = (
    "Traceback",
    "Error:",
    "Exception",
    "FAILED",
    "AssertionError",
    "ModuleNotFoundError",
    "AttributeError",
    "TypeError",
)


def summarize_text(text: Any, max_chars: int = 700) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "(empty result)"
    lines = raw.splitlines()
    important = [line.strip() for line in lines if any(marker in line for marker in ERROR_MARKERS)]
    selected: List[str] = []
    if important:
        selected.extend(important[-6:])
    else:
        selected.extend(line.strip() for line in lines[:10] if line.strip())
    summary = "\n".join(selected).strip()
    if not summary:
        summary = raw[:max_chars]
    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip() + "..."
    return summary


def classify_tool_result(tool_name: str, args: Dict[str, Any], result: Any) -> Tuple[str, str, str]:
    name = (tool_name or "").lower()
    result_text = str(result or "")
    args_text = " ".join(str(v) for v in (args or {}).values()).lower()
    combined = f"{args_text}\n{result_text}".lower()

    if name in {"read", "smart_search", "grep", "glob"}:
        return "file_read", "GATHERING_CONTEXT", "context gathered"
    if name in {"write", "edit"}:
        return "diff", "EDITING", "code changed"
    if name in {"ask_user", "ask_selection"}:
        return "user_interaction", "UNDERSTANDING", "user responded"
    if name in {"bash", "shell"}:
        if any(term in combined for term in ["pytest", "unittest", "test "]):
            if any(term in combined for term in ["failed", "error", "traceback", "exit code 1"]):
                return "test", "DEBUGGING", "test failed"
            return "test", "TESTING", "test evidence recorded"
        if any(term in combined for term in ["error", "traceback", "exception"]):
            return "command", "DEBUGGING", "command failed"
        return "command", "GATHERING_CONTEXT", "command evidence recorded"
    return "tool", "GATHERING_CONTEXT", "tool evidence recorded"


def extract_files_from_args(args: Dict[str, Any]) -> List[str]:
    files: List[str] = []
    for key in ("path", "file", "filepath", "target_file"):
        value = (args or {}).get(key)
        if isinstance(value, str) and value:
            files.append(value)
    include = (args or {}).get("include")
    if isinstance(include, str) and include:
        files.append(include)
    return files

