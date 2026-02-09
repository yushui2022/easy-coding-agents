from tools.base import registry
from core.task import TaskManager
from typing import Any

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
def todo_add(content: str, context: Any) -> str:
    if not hasattr(context, 'task_manager'):
        return "Error: Invalid context (missing task_manager)."
    
    manager: TaskManager = context.task_manager
    task_id = manager.add_task(content)
    manager.print_summary()
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
def todo_update(task_id: str, status: str, context: Any) -> str:
    if not hasattr(context, 'task_manager'):
        return "Error: Invalid context (missing task_manager)."
        
    manager: TaskManager = context.task_manager
    if manager.update_task(task_id, status):
        manager.print_summary()
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
def todo_list(context: Any) -> str:
    if not hasattr(context, 'task_manager'):
        return "Error: Invalid context (missing task_manager)."
        
    manager: TaskManager = context.task_manager
    return manager.render()
