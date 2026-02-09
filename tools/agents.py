from tools.base import registry
from typing import Any, Dict, List, Optional
import os
import json
import re
import uuid
import aiofiles
from utils.logger import console

# Persistent storage path
AGENTS_STORE_PATH = os.path.join("memory", "agents.json")
DEFAULT_USER_ID = "local_user"
MAX_AGENTS_PER_USER = 20


def _ensure_store_dir():
    parent = os.path.dirname(AGENTS_STORE_PATH)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


async def _load_store() -> Dict[str, Any]:
    _ensure_store_dir()
    if not os.path.exists(AGENTS_STORE_PATH):
        return {"users": {}}
    try:
        async with aiofiles.open(AGENTS_STORE_PATH, mode="r", encoding="utf-8") as f:
            content = await f.read()
        data = json.loads(content) if content.strip() else {"users": {}}
        if "users" not in data:
            data["users"] = {}
        return data
    except Exception:
        return {"users": {}}


async def _save_store(data: Dict[str, Any]) -> str:
    try:
        async with aiofiles.open(AGENTS_STORE_PATH, mode="w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        return f"Saved: {AGENTS_STORE_PATH}"
    except Exception as e:
        return f"Error saving store: {str(e)}"


def _sanitize_hex_color(color: str) -> str:
    if not color:
        return "#4CAF50"  # default green
    color = color.strip()
    if re.fullmatch(r"#?[0-9a-fA-F]{6}", color):
        return "#" + color.lstrip("#")
    # Allow preset names; fallback if invalid
    presets = {
        "blue": "#2196F3", "green": "#4CAF50", "red": "#F44336", "purple": "#9C27B0",
        "orange": "#FF9800", "teal": "#009688", "cyan": "#00BCD4", "indigo": "#3F51B5",
    }
    return presets.get(color.lower(), "#4CAF50")


def _expand_agent_config(name: str, base_desc: str) -> Dict[str, Any]:
    """Deterministic expansion engine to generate a complete agent definition."""
    keywords = [w.strip().lower() for w in re.split(r"[,\n;]+", base_desc) if w.strip()]

    abilities = [
        "代码搜索与分析",
        "项目结构理解与模块依赖梳理",
        "任务规划与分阶段执行",
        "文件读写与补丁应用",
        "交互式问答与决策确认",
    ]
    # Heuristic boosts based on keywords
    if any(k in keywords for k in ["前端", "react", "web", "ui"]):
        abilities.append("前端组件开发与样式优化")
    if any(k in keywords for k in ["后端", "api", "flask", "fastapi"]):
        abilities.append("后端API设计与实现")
    if any(k in keywords for k in ["测试", "unit", "pytest"]):
        abilities.append("单元测试编写与覆盖率提升")

    behavior_rules = [
        "严格遵循任务驱动闭环，先规划后执行",
        "在执行阶段避免微观打断，必要时使用交互式确认",
        "遵循Windows命令约束与编码规范，避免Bash专属语法",
        "所有生成文件默认写入workspace目录，避免污染根目录",
        "敏感信息不写入日志或代码，不提交秘钥",
    ]

    dialogue_style = {
        "tone": "简洁、专业、协作",
        "format": "结构化要点+必要代码片段",
        "language": "中文为主，代码注释遵循项目规范",
    }

    constraints = [
        "单次回答不超过必要长度，避免长篇堆砌",
        "不对不存在的库或命令做假设，先检索再使用",
        "不在未确认的情况下修改核心系统文件",
    ]

    scenarios = [
        {"title": "快速项目理解", "example": "分析 core 与 tools 目录，输出模块关系图与职责说明"},
        {"title": "特性开发闭环", "example": "根据需求生成Todo并自主执行，完成实现与验证"},
        {"title": "Bug 修复与验证", "example": "定位异常栈，修复代码并提供最小复现与验证结果"},
    ]

    notes = [
        "当任务完成后，提供结果概要与下一步建议",
        "遇到不确定信息时，优先检索代码库并给出证据",
    ]

    return {
        "name": name,
        "role": f"{name} — 定制人格化编程助手",
        "capabilities": abilities,
        "behavior_rules": behavior_rules,
        "dialogue_style": dialogue_style,
        "constraints": constraints,
        "scenarios": scenarios,
        "notes": notes,
        "raw_requirements": base_desc.strip(),
    }


def _render_preview(agent: Dict[str, Any]) -> str:
    """Pretty text preview in structured sections."""
    lines: List[str] = []
    lines.append(f"Agent: {agent.get('name')}")
    lines.append("— 定义预览 —")
    lines.append("能力清单:")
    for cap in agent.get("capabilities", []):
        lines.append(f"- {cap}")
    lines.append("行为准则:")
    for r in agent.get("behavior_rules", []):
        lines.append(f"- {r}")
    ds = agent.get("dialogue_style", {})
    lines.append("对话风格:")
    lines.append(f"- 语气: {ds.get('tone')}")
    lines.append(f"- 格式: {ds.get('format')}")
    lines.append(f"- 语言: {ds.get('language')}")
    lines.append("限制条件:")
    for c in agent.get("constraints", []):
        lines.append(f"- {c}")
    lines.append("使用场景示例:")
    for sc in agent.get("scenarios", []):
        lines.append(f"- {sc['title']}: {sc['example']}")
    lines.append("注意事项:")
    for n in agent.get("notes", []):
        lines.append(f"- {n}")
    return "\n".join(lines)


@registry.register(
    name="agent_create",
    description="Create a custom agent with name, base description, and color. Enforces per-user limit.",
    parameters={
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "color": {"type": "string"},
            "user_id": {"type": "string"},
        },
        "required": ["name", "description", "color"]
    }
)
async def agent_create(name: str, description: str, color: str, user_id: Optional[str] = None) -> str:
    user_id = user_id or DEFAULT_USER_ID
    color = _sanitize_hex_color(color)
    store = await _load_store()
    user_bucket = store["users"].get(user_id, {"agents": []})
    agents = user_bucket["agents"]
    if len(agents) >= MAX_AGENTS_PER_USER:
        return f"Error: 已达到上限，每个用户最多创建 {MAX_AGENTS_PER_USER} 个自定义Agent。"
    # Unique name constraint within user
    if any(a["name"].lower() == name.lower() for a in agents):
        return "Error: 该名称的Agent已存在，请更换名称。"
    agent_id = str(uuid.uuid4())
    definition = _expand_agent_config(name, description)
    record = {
        "id": agent_id,
        "user_id": user_id,
        "name": name,
        "color": color,
        "enabled": True,
        "definition": definition,
    }
    agents.append(record)
    store["users"][user_id] = {"agents": agents}
    await _save_store(store)
    preview = _render_preview(definition)
    return f"Agent 创建成功 (ID: {agent_id})\n颜色: {color}\n\n{preview}"


@registry.register(
    name="agent_list",
    description="List all custom agents for a user.",
    parameters={
        "properties": {
            "user_id": {"type": "string"}
        },
        "required": []
    }
)
async def agent_list(user_id: Optional[str] = None) -> str:
    user_id = user_id or DEFAULT_USER_ID
    store = await _load_store()
    agents = store.get("users", {}).get(user_id, {}).get("agents", [])
    if not agents:
        return "暂无自定义Agent。"
    lines = []
    for a in agents:
        status = "启用" if a.get("enabled") else "禁用"
        lines.append(f"{a['id']} | @{a['name']} | {status} | {a.get('color', '#4CAF50')}")
    return "\n".join(lines)


@registry.register(
    name="agent_preview",
    description="Render structured preview of an agent by id.",
    parameters={
        "properties": {"id": {"type": "string"}, "user_id": {"type": "string"}},
        "required": ["id"]
    }
)
async def agent_preview(id: str, user_id: Optional[str] = None) -> str:
    user_id = user_id or DEFAULT_USER_ID
    store = await _load_store()
    agents = store.get("users", {}).get(user_id, {}).get("agents", [])
    target = next((x for x in agents if x["id"] == id), None)
    if not target:
        return "Error: 未找到指定Agent。"
    return _render_preview(target["definition"])


@registry.register(
    name="agent_update",
    description="Update basic fields or full definition of an agent.",
    parameters={
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "color": {"type": "string"},
            "enabled": {"type": "boolean"},
            "user_id": {"type": "string"},
            "definition": {"type": "object"},
        },
        "required": ["id"]
    }
)
async def agent_update(id: str, name: Optional[str] = None, description: Optional[str] = None, color: Optional[str] = None, enabled: Optional[bool] = None, definition: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None) -> str:
    user_id = user_id or DEFAULT_USER_ID
    store = await _load_store()
    agents = store.get("users", {}).get(user_id, {}).get("agents", [])
    idx = next((i for i, x in enumerate(agents) if x["id"] == id), None)
    if idx is None:
        return "Error: 未找到指定Agent。"
    rec = agents[idx]
    if name:
        # prevent duplicate names
        if any(x["name"].lower() == name.lower() and x["id"] != id for x in agents):
            return "Error: 该名称已被其他Agent使用。"
        rec["name"] = name
    if description:
        rec["definition"] = _expand_agent_config(rec["name"], description)
    if color:
        rec["color"] = _sanitize_hex_color(color)
    if enabled is not None:
        rec["enabled"] = bool(enabled)
    if definition:
        rec["definition"] = definition
    agents[idx] = rec
    store["users"][user_id] = {"agents": agents}
    await _save_store(store)
    return "Agent 更新成功。"


@registry.register(
    name="agent_delete",
    description="Delete an agent.",
    parameters={
        "properties": {"id": {"type": "string"}, "user_id": {"type": "string"}},
        "required": ["id"]
    }
)
async def agent_delete(id: str, user_id: Optional[str] = None) -> str:
    user_id = user_id or DEFAULT_USER_ID
    store = await _load_store()
    agents = store.get("users", {}).get(user_id, {}).get("agents", [])
    new_agents = [x for x in agents if x["id"] != id]
    if len(new_agents) == len(agents):
        return "Error: 未找到指定Agent。"
    store["users"][user_id] = {"agents": new_agents}
    await _save_store(store)
    return "Agent 已删除。"


@registry.register(
    name="agent_share",
    description="Generate a share link for an agent.",
    parameters={
        "properties": {"id": {"type": "string"}, "user_id": {"type": "string"}},
        "required": ["id"]
    }
)
async def agent_share(id: str, user_id: Optional[str] = None) -> str:
    user_id = user_id or DEFAULT_USER_ID
    store = await _load_store()
    agents = store.get("users", {}).get(user_id, {}).get("agents", [])
    target = next((x for x in agents if x["id"] == id), None)
    if not target:
        return "Error: 未找到指定Agent。"
    # Simple pseudo link schema for sharing
    link = f"easy-coding-agent://agent/{target['id']}"
    return f"分享链接: {link}"


@registry.register(
    name="agent_use",
    description="Activate an agent by id or name, updating system prompt persona.",
    parameters={
        "properties": {"identifier": {"type": "string"}, "user_id": {"type": "string"}},
        "required": ["identifier"]
    }
)
async def agent_use(identifier: str, user_id: Optional[str] = None, context: Any = None) -> str:
    user_id = user_id or DEFAULT_USER_ID
    store = await _load_store()
    agents = store.get("users", {}).get(user_id, {}).get("agents", [])
    target = next((x for x in agents if x["id"] == identifier or x["name"].lower() == identifier.lower()), None)
    if not target:
        return "Error: 未找到指定Agent。"
    if not target.get("enabled", True):
        return "Error: 该Agent已被禁用，无法使用。"
    # Compose persona block
    persona = target["definition"]
    persona_block = [
        "=== ACTIVE CUSTOM AGENT:START ===",
        f"Name: {persona.get('name')}",
        f"Role: {persona.get('role')}",
        "Capabilities: " + ", ".join(persona.get("capabilities", [])),
        "Behavior Rules: " + "; ".join(persona.get("behavior_rules", [])),
        "Constraints: " + "; ".join(persona.get("constraints", [])),
        "Dialogue Style: " + json.dumps(persona.get("dialogue_style", {}), ensure_ascii=False),
        "=== ACTIVE CUSTOM AGENT:END ===",
    ]
    persona_text = "\n".join(persona_block)
    # Update system prompt via context.memory_manager
    if context and hasattr(context, "memory_manager"):
        # Append to existing system prompt
        current_sp = context.memory_manager.get_system_prompt()
        # Remove previous active agent block if exists
        new_sp = re.sub(
            r"=== ACTIVE CUSTOM AGENT:START ===.*?=== ACTIVE CUSTOM AGENT:END ===",
            "",
            current_sp,
            flags=re.S
        ).strip()
        new_sp = f"{new_sp}\n\n{persona_text}".strip()
        context.memory_manager.set_system_prompt(new_sp)
        # Also attach current agent metadata onto context for UI display (optional)
        setattr(context, "current_agent", {"id": target["id"], "name": target["name"], "color": target.get("color", "#4CAF50")})
    return f"已切换到自定义Agent @{target['name']} (ID: {target['id']})"
