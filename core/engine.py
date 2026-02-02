import asyncio
import json
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from utils.logger import logger, console

# Import components
from core.stream import StreamHandler
from memory import MemoryManager # Updated import path
from core.prompts import get_system_prompt
from core.task import TaskManager
from tools.base import registry

from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

# Import tools to register them
import tools.filesystem
import tools.search
import tools.shell
import tools.todo

@dataclass
class Event:
    type: str  # 'user_input', 'stop'
    content: Any
    metadata: Dict = field(default_factory=dict)

class AgentEngine:
    """
    Core execution framework (n0) with Double-Buffered Async Message Queue (h2A).
    """
    def __init__(self):
        # h2A: Double Buffering
        self.input_queue = asyncio.Queue()      # Buffer 1: External Inputs
        self.processing_queue = asyncio.Queue() # Buffer 2: Internal Tasks
        
        self.running = True # Default to True to avoid race condition in main loop
        
        # Initialize components
        self.stream_handler = StreamHandler()
        self.memory = MemoryManager(self.stream_handler) # Inject stream_handler for AU2
        self.task_manager = TaskManager()
        tools.todo.set_global_task_manager(self.task_manager)
        
        # We will set system prompt in start() after loading long-term memory
        self.tools_schema = registry.get_schema()

    async def start(self):
        """Start the n0 main loop."""
        logger.info("Starting Agent Engine...")
        
        # Lifecycle: Load Long Term Memory
        long_term_data = await self.memory.initialize()
        
        # Combine System Prompt + Long Term Memory
        full_system_prompt = get_system_prompt()
        if long_term_data:
             full_system_prompt += f"\n\n=== LONG TERM MEMORY (EXPERIENCE) ===\n{long_term_data}"
             
        self.memory.set_system_prompt(full_system_prompt)
        
        try:
            await asyncio.gather(
                self.input_consumer(),
                self.task_consumer()
            )
        except asyncio.CancelledError:
            logger.info("Engine stopped.")

    async def input_consumer(self):
        """Consumer for Buffer 1: Ingests raw events."""
        while self.running:
            try:
                event = await self.input_queue.get()
                # Pass to processing queue
                await self.processing_queue.put(event)
                self.input_queue.task_done()
            except Exception as e:
                logger.error(f"Error in input_consumer: {e}")

    async def task_consumer(self):
        """Consumer for Buffer 2: Executes Logic."""
        while self.running:
            try:
                event = await self.processing_queue.get()
                
                if event.type == "user_input":
                    await self.handle_user_input(event.content)
                elif event.type == "stop":
                    self.running = False
                    self.processing_queue.task_done()
                    return

                self.processing_queue.task_done()
            except Exception as e:
                logger.error(f"Error in task_consumer: {e}")
                # Ensure we mark task as done even on error to prevent deadlocks
                try:
                    self.processing_queue.task_done()
                except ValueError:
                    pass

    async def handle_user_input(self, content: str):
        self.memory.add("user", content)
        # Start the autonomous loop
        await self._run_autonomous_loop()

    async def _run_autonomous_loop(self):
        """
        The Core Control Loop (n0): Task-Driven Autonomous Execution.
        This replaces the simple request-response model.
        """
        max_turns = 30 # Safety limit for the entire session
        turn_count = 0
        start_time = time.time()
        
        while turn_count < max_turns:
            turn_count += 1
            
            # Show elapsed time for long running tasks
            elapsed = time.time() - start_time
            if elapsed > 2.0: # Only show if it's taking a bit of time
                mins, secs = divmod(int(elapsed), 60)
                time_str = f"{mins}分 {secs}秒" if mins > 0 else f"{secs}秒"
                console.print(f"[dim]生成中... (已耗时: {time_str})[/dim]", end="\r")
            
            # 1. Context Construction with State Injection
            # This call will implicitly handle overflow and AU2 compression if needed
            messages = await self.memory.get_context()
            
            # Removed explicit progress bar call here as requested
            # if self.task_manager.tasks:
            #    self.task_manager.print_progress()

            # Inject System State (The "Conscience" of the Agent)
            state_prompt = ""
            if not self.task_manager.tasks:
                state_prompt = "Status: Idle. Waiting for user input or task planning."
            elif self.task_manager.has_unfinished_tasks():
                next_task = self.task_manager.get_next_pending()
                # Determine precise status for the prompt
                status_str = "Working" if next_task.status == "in_progress" else "Pending"
                state_prompt = f"Status: {status_str}. \n{self.task_manager.render()}\n\nNEXT ACTION REQUIRED: Continue working on Task {next_task.id}: '{next_task.content}'. Use available tools to make progress."
            else:
                state_prompt = f"Status: All tasks completed.\n{self.task_manager.render()}\n\nNEXT ACTION REQUIRED: Summarize results and ask user for next steps."
            
            # We append this temporary system state to the end of messages for this turn only
            # In a real implementation, we might want to handle this more elegantly in MemoryManager
            # For now, we just append a system message that won't be saved to history permanently 
            # (or we save it, but wU2 will compress it later)
            current_messages = messages + [{"role": "system", "content": f"<system_state>\n{state_prompt}\n</system_state>"}]

            # 2. Call LLM (wu streamed)
            try:
                response_gen = self.stream_handler.chat(current_messages, self.tools_schema)
                full_content, tool_calls = await self.stream_handler.render_stream(response_gen)
            except Exception as e:
                console.print(f"[red]LLM 错误: {e}[/red]")
                break

            # 3. Update Memory
            self.memory.add("assistant", full_content, tool_calls=tool_calls if tool_calls else None)
            
            # 4. Check for Termination Conditions
            if not tool_calls:
                # If LLM didn't call any tools:
                # - If tasks are pending/in_progress: It might be a "thinking" step or a refusal.
                #   We MUST NOT break the loop if we want full autonomy. We inject a prod.
                # - If tasks are done: It's offering a summary. We stop and wait for user.
                # - If no tasks: It's chatting. We stop.
                
                if self.task_manager.has_unfinished_tasks():
                     # Autonomy Guard: Don't let it stop if work remains.
                     # But prevent infinite loops if it refuses to act.
                     # We can just continue; the next iteration will inject the State Prompt again.
                     # To be safe, we can add a small system nudge to the history (optional), 
                     # but the state prompt at top of loop is usually enough.
                     
                     # Check if it's asking a question? (Hard to know).
                    # For now, we assume "Full Auto" means keep going until done.
                    console.print("[dim]自动继续: 任务尚未完成...[/dim]")
                    continue 
                else:
                     # No active tasks, so we yield to user.
                     break
            
            # 5. Execute Tools
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                args_str = tc["function"]["arguments"]
                call_id = tc["id"]
                
                # Beautify Tool Call Log
                try:
                    args = json.loads(args_str)
                    
                    # Create a display version of args
                    display_args = args.copy()
                    
                    # Truncate 'content' if it's too long (e.g. for write/edit)
                    if "content" in display_args and isinstance(display_args["content"], str):
                        content = display_args["content"]
                        if len(content) > 1000:
                            # Show first few lines + summary
                            lines = content.splitlines()
                            preview_lines = 15 # Show more context (approx 15 lines)
                            preview = "\n".join(lines[:preview_lines])
                            display_args["content"] = f"{preview}\n... ({len(lines)-preview_lines} more lines) ..."
                    
                    # Truncate 'new_str'/'old_str' for edit
                    if "new_str" in display_args and len(display_args["new_str"]) > 1000:
                        display_args["new_str"] = display_args["new_str"][:1000] + "..."
                    
                    # Format as JSON for display
                    # args_pretty = json.dumps(display_args, ensure_ascii=False, indent=2)
                    
                    # Manually format the JSON to keep content multiline
                    # JSON.dumps escapes newlines as \n, which makes it a single line block in Syntax.
                    # We want to show the actual newlines in the log.
                    
                    pretty_lines = ["{"]
                    for k, v in display_args.items():
                        if k == "content" and isinstance(v, str):
                            # Special handling for content: Show as a multiline block
                            pretty_lines.append(f'  "{k}": """')
                            # Indent content lines
                            for line in v.splitlines():
                                pretty_lines.append(f"    {line}")
                            pretty_lines.append('  """,')
                        else:
                            # Standard JSON formatting for other fields
                            val_str = json.dumps(v, ensure_ascii=False)
                            pretty_lines.append(f'  "{k}": {val_str},')
                    
                    # Remove trailing comma from last item if needed (simple hack)
                    if pretty_lines[-1].endswith(","):
                        pretty_lines[-1] = pretty_lines[-1][:-1]
                    pretty_lines.append("}")
                    
                    args_pretty = "\n".join(pretty_lines)
                    
                    # Use a distinct color for tool execution (e.g. blue/cyan instead of default)
                    console.print(Panel(
                        Syntax(args_pretty, "json", theme="monokai", word_wrap=True),
                        title=f"[bold cyan]🛠️ 正在执行: {func_name}[/bold cyan]",
                        border_style="cyan",
                        expand=False
                    ))
                    
                except json.JSONDecodeError:
                    # Fallback if args are not valid JSON
                    console.print(f"[bold red]正在执行 {func_name}({args_str})[/bold red]")
                    args = {}

                try:
                    # args already parsed above
                    if not args and args_str: # Retry parse if failed above? No, flow is linear.
                         args = json.loads(args_str)
                         
                    result = await registry.execute(func_name, args)
                except Exception as e:
                    result = f"Error executing tool: {str(e)}"
                
                # Show partial result snippet
                # Use a cleaner look for result
                snippet = result[:200] + "..." if len(result) > 200 else result
                console.print(f"[dim]执行结果: {snippet}[/dim]")
                console.print() # Spacer

                # 6. Add Tool Result to Memory
                self.memory.add("tool", result, tool_call_id=call_id, name=func_name)
            
            # 7. Loop continues automatically!
            # The LLM will see the tool results in the next iteration's context
            # and decide what to do next based on the updated Todo List state.
            
            # Auto-Save after each turn (Short Term)
            await self.memory.auto_save()

            # Autonomy Guard (Post-Tool):
            # Even if tools were executed, we check if work remains.
            # If tasks are unfinished, we explicitly print "Auto-Continuing" and loop.
            # If we don't do this, the loop relies on the `while turn_count < max_turns` condition,
            # which is correct, BUT we want to be sure we don't break out early for any reason.
            if self.task_manager.has_unfinished_tasks():
                # console.print("[dim]Auto-Continuing: Tasks are still active...[/dim]")
                pass
            else:
                # Tasks done? We might want to stop here or let the LLM say "I'm done" in next turn.
                # Let's let the LLM have the final word (Summary) in the next turn.
                pass

    async def push_event(self, type: str, content: Any, metadata: Dict = None):
        event = Event(type=type, content=content, metadata=metadata or {})
        await self.input_queue.put(event)

    def stop(self):
        # We can't await here because stop() is often called from sync signal handlers
        # But we can try to fire-and-forget or rely on previous auto-saves.
        self.running = False
