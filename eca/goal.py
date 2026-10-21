"""Session goal: one objective plus explicit acceptance criteria.

The criteria are planning state written by the model through the goal_update
tool. A "done" label is a claim, not verification: tests, tool output and the
user's own review still decide whether the work is actually correct.
"""

TEXT_LIMIT = 2000
CRITERIA_LIMIT = 20
CRITERION_LIMIT = 400
STATUSES = {"active", "done", "abandoned"}


def clean(text, criteria):
    """Validate a goal supplied by the user and return the stored shape."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("目标不能为空。")
    if len(text) > TEXT_LIMIT:
        raise ValueError(f"目标请控制在 {TEXT_LIMIT} 字以内。")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("至少需要一条验收标准。")
    if len(criteria) > CRITERIA_LIMIT:
        raise ValueError(f"验收标准最多 {CRITERIA_LIMIT} 条。")
    items = []
    for value in criteria:
        label = value.get("text") if isinstance(value, dict) else value
        if not isinstance(label, str) or not label.strip():
            raise ValueError("每条验收标准都需要文字内容。")
        if len(label) > CRITERION_LIMIT:
            raise ValueError(f"单条验收标准请控制在 {CRITERION_LIMIT} 字以内。")
        done = value.get("done") is True if isinstance(value, dict) else False
        items.append({"text": label.strip(), "done": done})
    return settle({"text": text.strip(), "criteria": items, "status": "active"})


def progress(goal):
    criteria = (goal or {}).get("criteria") or []
    return sum(1 for item in criteria if item.get("done")), len(criteria)


def settle(goal):
    """Recompute status from the criteria; an explicit abandon stays abandoned."""
    if not goal or goal.get("status") == "abandoned":
        return goal
    done, total = progress(goal)
    goal["status"] = "done" if total and done == total else "active"
    return goal


def public(goal):
    """Copy that the UI may render without touching session state."""
    if not goal:
        return None
    return {"text": goal.get("text", ""), "status": goal.get("status", "active"),
            "criteria": [{"text": item.get("text", ""), "done": bool(item.get("done"))}
                         for item in goal.get("criteria") or []]}


def update(goal, updates, status=None):
    """Apply 1-based criterion updates coming from the model."""
    if not goal:
        raise ValueError("当前会话还没有设定目标。")
    if not isinstance(updates, list) or len(updates) > CRITERIA_LIMIT:
        raise ValueError("Invalid goal update.")
    total = len(goal.get("criteria") or [])
    for item in updates:
        if not isinstance(item, dict) or set(item) - {"index", "done"}:
            raise ValueError("Each update needs an index and a done flag.")
        index = item.get("index")
        if type(index) is not int or not 1 <= index <= total:
            raise ValueError(f"Criterion index must be 1-{total}.")
        if type(item.get("done")) is not bool:
            raise ValueError("The done flag must be true or false.")
        goal["criteria"][index - 1]["done"] = item["done"]
    if status is not None:
        if status not in STATUSES:
            raise ValueError("Invalid goal status.")
        goal["status"] = status
    return settle(goal)


def prompt(goal):
    """System-prompt block for an active goal, or an empty string."""
    if not goal or goal.get("status") != "active":
        return ""
    done, total = progress(goal)
    lines = [f"Session goal: {goal['text']}",
             f"Acceptance criteria ({done}/{total} marked done; numbering matches goal_update):"]
    for number, item in enumerate(goal.get("criteria") or [], 1):
        lines.append(f"{number}. [{'done' if item.get('done') else 'open'}] {item['text']}")
    lines.append("Work until every criterion is satisfied, or report a genuine blocker with what you tried. "
                 "Record real progress with goal_update instead of prose; do not mark a criterion done to look finished. "
                 "A done label is not proof: tests, command output and file state still decide. "
                 "Ask the user only when a decision is genuinely theirs to make.")
    return "\n" + "\n".join(lines) + "\n"
