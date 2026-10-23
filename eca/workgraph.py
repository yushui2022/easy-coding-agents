"""Validated dependency-aware task plan (a small work graph).

The plan used to be a flat checklist. Each task may now carry an ``id`` and a
``depends_on`` list, so a plan can express real ordering:

* the graph is validated before it is stored: unique ids, known dependency
  references, no self-dependency, no cycles, bounded size;
* a task is *blocked* while any dependency is not ``completed``, and a blocked
  task cannot be reported ``completed`` — that is what stops a plan from
  claiming progress on work whose prerequisite failed or was never done;
* a dependency marked ``failed`` is reported separately, so the fix is to
  repair or drop the prerequisite, not to relabel the dependent.

Task ids are optional: a plan without ids keeps working exactly as before.
"""

from __future__ import annotations

import re

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,31}$")
STATUSES = ("pending", "in_progress", "completed", "failed")
MAX_ITEMS = 50
MAX_DEPENDENCIES = 8
MAX_CONTENT = 500
FIELDS = {"content", "status", "id", "depends_on"}


def validate(items) -> list[dict]:
    """Validate and normalise a submitted plan; return tasks with blocked state.

    Raises ValueError with an actionable message instead of storing a plan that
    cannot be executed in order.
    """
    if not isinstance(items, list):
        raise ValueError("items must be a list of tasks")
    if not items:
        raise ValueError("items must contain at least one task; keep the remaining steps")
    if len(items) > MAX_ITEMS:
        raise ValueError(f"At most {MAX_ITEMS} tasks in one plan; merge steps or work in phases")

    tasks = [_task(index, item) for index, item in enumerate(items, start=1)]
    ids = _unique_ids(tasks)
    _known_dependencies(tasks, ids)
    _reject_cycles(tasks)
    _apply_blocking(tasks)
    _reject_blocked_completion(tasks)
    return [_clean(task) for task in tasks]


def summary(tasks) -> dict:
    """Counts plus the tasks a caller could work on next."""
    counts = {status: 0 for status in STATUSES}
    for task in tasks:
        counts[task["status"]] = counts.get(task["status"], 0) + 1
    ready = [_name(task) for task in tasks
             if task["status"] in {"pending", "in_progress"} and not task.get("blocked")]
    blocked = [_name(task) for task in tasks
               if task["status"] in {"pending", "in_progress"} and task.get("blocked")]
    failed = [_name(task) for task in tasks if task["status"] == "failed"]
    return {"tasks": len(tasks), "counts": counts, "ready": ready, "blocked": blocked, "failed": failed}


def report(tasks) -> dict:
    """Payload returned to the model after a plan update."""
    data = summary(tasks)
    counts = data["counts"]
    note = (f"{data['tasks']} task(s): {counts['completed']} completed, {counts['in_progress']} in progress, "
            f"{counts['pending']} pending, {counts['failed']} failed.")
    if data["failed"]:
        note += (" Failed tasks do not unblock dependents: repair them, or change the dependents' depends_on, "
                 "before continuing with that branch.")
    elif data["blocked"]:
        note += " Blocked tasks cannot be marked completed until their dependencies are completed."
    data["note"] = note
    data["warning"] = "Plan labels are planning state, not proof that work or tests succeeded."
    return data


def _task(index, item) -> dict:
    if not isinstance(item, dict):
        raise ValueError(f"Task {index} must be an object with content and status")
    unknown = set(item) - FIELDS
    if unknown:
        raise ValueError(f"Task {index} has unsupported fields {sorted(unknown)}; allowed: content, status, id, depends_on")
    content = item.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"Task {index} needs non-empty content")
    content = content.strip()
    if len(content) > MAX_CONTENT:
        raise ValueError(f"Task {index} content is longer than {MAX_CONTENT} characters; keep one line per step")
    status = item.get("status")
    if status not in STATUSES:
        raise ValueError(f"Task {index} status {status!r} must be one of: {', '.join(STATUSES)}")
    task = {"content": content, "status": status, "depends_on": _dependencies(index, item.get("depends_on")),
            "_index": index}
    task_id = item.get("id")
    if task_id is not None:
        if not isinstance(task_id, str):
            raise ValueError(f"Task {index} id must be a string")
        task_id = task_id.strip().lower()
        if not ID_PATTERN.match(task_id):
            raise ValueError(f"Task {index} id {task_id!r} must be 1-32 characters of lowercase letters, digits, "
                             "'.', '_' or '-', starting with a letter or digit")
        task["id"] = task_id
    return task


def _dependencies(index, raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
        raise ValueError(f"Task {index} depends_on must be a list of task ids")
    if len(raw) > MAX_DEPENDENCIES:
        raise ValueError(f"Task {index} has more than {MAX_DEPENDENCIES} dependencies; split the step instead")
    deps = []
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Task {index} depends_on entries must be non-empty task ids")
        value = value.strip().lower()
        if value not in deps:
            deps.append(value)
    return deps


def _label(task) -> str:
    return f"{task['_index']} ({task['id']})" if task.get("id") else str(task["_index"])


def _name(task) -> str:
    return task.get("id") or task["content"]


def _unique_ids(tasks) -> dict:
    ids = {}
    for task in tasks:
        task_id = task.get("id")
        if not task_id:
            continue
        if task_id in ids:
            raise ValueError(f"Duplicate task id {task_id!r} used by tasks {ids[task_id]} and {task['_index']}; "
                             "depends_on must name exactly one task, so ids have to be unique")
        ids[task_id] = task["_index"]
    return ids


def _known_dependencies(tasks, ids) -> None:
    known = ", ".join(sorted(ids)) or "none (no task defines an id)"
    for task in tasks:
        for dep in task["depends_on"]:
            if dep == task.get("id"):
                raise ValueError(f"Task {_label(task)} depends on itself; remove it from depends_on")
            if dep not in ids:
                raise ValueError(f"Task {_label(task)} depends on unknown id {dep!r}. Known ids: {known}. "
                                 "Add that id to the task it refers to, or drop the dependency")


def _reject_cycles(tasks) -> None:
    by_id = {task["id"]: task for task in tasks if task.get("id")}
    state = {}  # id -> 1 visiting, 2 done
    stack = []

    def visit(task_id):
        mark = state.get(task_id)
        if mark == 2:
            return
        if mark == 1:
            cycle = stack[stack.index(task_id):] + [task_id]
            raise ValueError("Circular dependency: " + " -> ".join(cycle) +
                             ". A plan must be executable in order, so remove one link")
        state[task_id] = 1
        stack.append(task_id)
        for dep in by_id[task_id]["depends_on"]:
            if dep in by_id:
                visit(dep)
        stack.pop()
        state[task_id] = 2

    for task_id in sorted(by_id):
        visit(task_id)


def _apply_blocking(tasks) -> None:
    status_of = {task["id"]: task["status"] for task in tasks if task.get("id")}
    for task in tasks:
        waiting = [dep for dep in task["depends_on"] if status_of.get(dep) != "completed"]
        task["blocked_by"] = waiting
        task["failed_by"] = [dep for dep in waiting if status_of.get(dep) == "failed"]
        task["blocked"] = bool(waiting)


def _reject_blocked_completion(tasks) -> None:
    status_of = {task["id"]: task["status"] for task in tasks if task.get("id")}
    for task in tasks:
        if task["status"] != "completed" or not task["blocked"]:
            continue
        detail = ", ".join(f"{dep} ({status_of.get(dep)})" for dep in task["blocked_by"])
        hint = ("Repair the failed prerequisite first, or drop it from depends_on if that step is no longer required."
                if task["failed_by"] else
                "Finish the prerequisite first, or drop it from depends_on if that step is no longer required.")
        raise ValueError(f"Task {_label(task)} cannot be completed while these dependencies are unfinished: "
                         f"{detail}. " + hint)


def _clean(task) -> dict:
    """Public shape: derived keys appear only when they carry information."""
    data = {"content": task["content"], "status": task["status"]}
    if task.get("id"):
        data["id"] = task["id"]
    if task["depends_on"]:
        data["depends_on"] = list(task["depends_on"])
    if task.get("blocked"):
        data["blocked"] = True
        data["blocked_by"] = list(task["blocked_by"])
        if task["failed_by"]:
            data["failed_by"] = list(task["failed_by"])
    return data
