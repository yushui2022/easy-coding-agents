from dataclasses import dataclass, field
from typing import List, Optional
import uuid
from utils.logger import console

@dataclass
class Task:
    id: str
    content: str
    status: str = "pending"  # pending, in_progress, completed, skipped

class TaskManager:
    """
    Manages the dynamic todo list for the agent to keep it on track.
    """
    def __init__(self):
        self.tasks: List[Task] = []

    def add_task(self, content: str) -> str:
        """Add a new task and return its ID."""
        task_id = str(len(self.tasks) + 1)
        task = Task(id=task_id, content=content)
        self.tasks.append(task)
        return task_id

    def update_task(self, task_id: str, status: str) -> bool:
        """Update the status of a task."""
        for task in self.tasks:
            if task.id == task_id:
                task.status = status
                return True
        return False

    def get_tasks(self) -> List[Task]:
        return self.tasks

    def clear(self):
        self.tasks = []

    def get_next_pending(self) -> Optional[Task]:
        """Get the next pending task to execute."""
        # First check if there is an in_progress task
        for task in self.tasks:
            if task.status == "in_progress":
                return task
        # Then check for pending
        for task in self.tasks:
            if task.status == "pending":
                return task
        return None

    def has_pending_tasks(self) -> bool:
        """Strictly pending tasks."""
        return any(t.status == "pending" for t in self.tasks)

    def has_unfinished_tasks(self) -> bool:
        """Pending OR In_Progress tasks."""
        return any(t.status in ["pending", "in_progress"] for t in self.tasks)

    def is_all_completed(self) -> bool:
        if not self.tasks:
            return True
        return all(t.status in ["completed", "skipped"] for t in self.tasks)

    def render(self) -> str:
        """Return a string representation of the todo list for the LLM context."""
        if not self.tasks:
            return "(No active todo list)"
        
        lines = ["Current Todo List:"]
        for task in self.tasks:
            icon = " "
            status_note = ""
            if task.status == "completed":
                icon = "[x]"
                status_note = " (Done - DO NOT REPEAT)"
            elif task.status == "in_progress":
                icon = "[->]"
                status_note = " (CURRENT FOCUS)"
            elif task.status == "skipped":
                icon = "[-]"
                status_note = " (Skipped)"
            else:
                icon = "[ ]"
                status_note = " (Pending)"
            
            lines.append(f"{task.id}. {icon} {task.content}{status_note}")
        return "\n".join(lines)

    def print_summary(self):
        """Print a pretty summary to the console."""
        if not self.tasks:
            return

        # Show progress bar
        self.print_progress() 

        console.print("\n[bold underline]Todo List Status:[/bold underline]")
        for task in self.tasks:
            if task.status == "completed":
                style = "green strike"
                icon = "✔"
            elif task.status == "in_progress":
                style = "yellow bold"
                icon = "➜"
            elif task.status == "skipped":
                style = "dim"
                icon = "-"
            else:
                style = "white"
                icon = "○"
            
            console.print(f"[{style}] {task.id}. {icon} {task.content}[/{style}]")
        console.print()

    def print_progress(self):
        """Print a visual progress bar."""
        if not self.tasks:
            return
        
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks if t.status in ["completed", "skipped"])
        percent = (completed / total) * 100
        
        # Visual Bar Construction
        width = 40
        filled = int(width * (completed / total))
        # Gradient colors for the bar
        color = "red"
        if percent > 30: color = "yellow"
        if percent > 70: color = "green"
        if percent == 100: color = "bold green"
        
        bar_chars = "━" * filled
        empty_chars = "─" * (width - filled)
        
        console.print(f"\nTask Progress: [{color}]{bar_chars}[/{color}][dim]{empty_chars}[/dim] [bold]{int(percent)}%[/bold] ({completed}/{total})")
