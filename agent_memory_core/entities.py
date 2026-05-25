import re
from pathlib import Path
from typing import Any, Dict, List, Optional


CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".md",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".txt",
}


def extract_entities(text: Any, args: Optional[Dict[str, Any]] = None, role: str = "") -> List[Dict[str, Any]]:
    raw = str(text or "")
    args = args or {}
    entities: List[Dict[str, Any]] = []

    for key in ("path", "file", "filepath", "target_file", "include"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            entities.append(_entity("file", value.strip(), confidence=0.95))

    cmd = args.get("cmd") or args.get("command")
    if isinstance(cmd, str) and cmd.strip():
        entities.append(_entity("command", cmd.strip(), confidence=0.9))

    for match in re.findall(r"[\w./\\-]+\.[A-Za-z0-9_]+", raw):
        suffix = Path(match).suffix.lower()
        if suffix in CODE_EXTENSIONS:
            entities.append(_entity("file", match, confidence=0.8))

    for match in re.findall(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", raw):
        entities.append(_entity("function", match, confidence=0.85))

    for match in re.findall(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\b", raw):
        entities.append(_entity("class", match, confidence=0.85))

    for match in re.findall(r"([A-Za-z0-9_./\\-]+::test_[A-Za-z0-9_]+|test_[A-Za-z0-9_]+)", raw):
        entities.append(_entity("test", match, confidence=0.9))

    for match in re.findall(r"\b([A-Za-z_]*(?:Error|Exception)|AssertionError|Traceback)\b", raw):
        entities.append(_entity("error", match, confidence=0.9))

    for line in raw.splitlines():
        stripped = line.strip(" `>\t")
        if re.match(r"^(pytest|python|git|npm|pnpm|yarn|uv|ruff|mypy|tox)\b", stripped):
            entities.append(_entity("command", stripped[:220], confidence=0.82))

    lowered = raw.lower()
    if role == "user" and raw.strip():
        entities.append(_entity("goal", raw.strip()[:160], confidence=0.55))

    if any(token in lowered for token in ["prefer", "always", "never", "preference", "偏好", "喜欢", "不要", "总是"]):
        entities.append(_entity("user_preference", raw.strip()[:200], confidence=0.7))

    return _dedupe(entities)


def query_entities(text: str) -> List[Dict[str, Any]]:
    return extract_entities(text)


def _entity(entity_type: str, text: str, confidence: float) -> Dict[str, Any]:
    normalized = normalize_entity(text)
    return {
        "entity_type": entity_type,
        "text": text,
        "normalized": normalized,
        "confidence": confidence,
    }


def normalize_entity(text: str) -> str:
    normalized = str(text or "").strip().replace("\\", "/").lower()
    return " ".join(normalized.split())


def _dedupe(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for entity in entities:
        key = (entity["entity_type"], entity["normalized"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entity)
    return deduped
