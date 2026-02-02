from tools.base import registry
from core.task import TaskManager

# We need a way to access the global task manager instance.
# Since tools are stateless functions, we'll inject the manager later or use a singleton pattern.
# For simplicity in this architecture, we will rely on the Engine to inject the manager 
# or use a global instance if we must. 
# However, a cleaner way is to let the Engine handle the state and these functions just operate on it.
# But `registry.register` expects standalone functions.
# Let's use a global variable pattern for the active manager, set by the Engine on startup.

_GLOBAL_TASK_MANAGER = None

def set_global_task_manager(manager: TaskManager):
    global _GLOBAL_TASK_MANAGER
    _GLOBAL_TASK_MANAGER = manager

@registry.register(
    name="todo_add",
    description="Add a new task to the todo list.",
    parameters={
        "properties": {
            "content": {"type": "string", "description": "Task description"}
        },
        "required": ["content"]
    }
)
def todo_add(content: str) -> str:
    if not _GLOBAL_TASK_MANAGER:
        return "Error: Task manager not initialized."
    task_id = _GLOBAL_TASK_MANAGER.add_task(content)
    _GLOBAL_TASK_MANAGER.print_summary()
    return f"Task added with ID: {task_id}"

@registry.register(
    name="todo_update",
    description="Update the status of a task.",
    parameters={
        "properties": {
            "task_id": {"type": "string", "description": "ID of the task to update"},
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "skipped"], "description": "New status"}
        },
        "required": ["task_id", "status"]
    }
)
def todo_update(task_id: str, status: str) -> str:
    if not _GLOBAL_TASK_MANAGER:
        return "Error: Task manager not initialized."
    if _GLOBAL_TASK_MANAGER.update_task(task_id, status):
        _GLOBAL_TASK_MANAGER.print_summary()
        return f"Task {task_id} updated to {status}."
    return f"Error: Task {task_id} not found."

@registry.register(
    name="todo_list",
    description="List all tasks and their status.",
    parameters={
        "properties": {},
        "required": []
    }
)
def todo_list() -> str:
    if not _GLOBAL_TASK_MANAGER:
        return "Error: Task manager not initialized."
    return _GLOBAL_TASK_MANAGER.render()
