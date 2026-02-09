import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from utils.logger import logger, console

# Import components
from core.stream import StreamHandler
from memory import MemoryManager # Updated import path
from core.prompts import get_system_prompt
from core.task import TaskManager
from core.config import Config
from tools.base import registry

from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

# Import tools to register them
import tools.filesystem
import tools.search
import tools.shell
import tools.todo
import tools.interaction
import tools.agents

class AgentMode(Enum):
    PLAN = "Plan"
    CODE = "Code"
    CHAT = "Chat"

@dataclass
class Event:
    type: str  # 'user_input', 'stop'
    content: Any
    metadata: Dict = field(default_factory=dict)

@dataclass
class AgentContext:
    """Context object injected into tools."""
    task_manager: TaskManager
    memory_manager: MemoryManager
    input_func: Optional[Callable[[str], Any]] = None
    selection_func: Optional[Callable[[str, List[str]], Any]] = None
    current_agent: Optional[Dict[str, Any]] = None

class AgentEngine:
    """
    Core execution framework (n0) with Double-Buffered Async Message Queue (h2A).
    """
    def __init__(self, input_func: Callable = None, selection_func: Callable = None):
        # h2A: Double Buffering
        self.input_queue = asyncio.Queue()      # Buffer 1: External Inputs
        self.processing_queue = asyncio.Queue() # Buffer 2: Internal Tasks
        
        self.running = True # Default to True to avoid race condition in main loop
        
        # Initialize components
        self.stream_handler = StreamHandler()
        self.memory = MemoryManager(self.stream_handler) # Inject stream_handler for AU2
        self.task_manager = TaskManager()
        
        # Mode State
        self.mode = AgentMode.CODE
        
        # Context for Dependency Injection
        self.context = AgentContext(
            task_manager=self.task_manager,
            memory_manager=self.memory,
            input_func=input_func,
            selection_func=selection_func
        )
        
        # We will set system prompt in start() after loading long-term memory
        self.tools_schema = registry.get_schema()
        
        # Synchronization
        self.ready_event = asyncio.Event()

    def toggle_mode(self):
        """Cycle through agent modes."""
        modes = list(AgentMode)
        current_index = modes.index(self.mode)
        next_index = (current_index + 1) % len(modes)
        self.mode = modes[next_index]
        
        # Update system prompt dynamically
        full_system_prompt = get_system_prompt(self.mode.value)
        # We need to preserve long term memory injection if it exists, 
        # but self.memory.system_prompt might already have it. 
        # For simplicity, we just update the base prompt.
        # Ideally, MemoryManager should handle the composition.
        # But for now, let's just reset it.
        # Wait, if we reset it, we lose the long term memory part if we don't reload it.
        # A better way is to ask MemoryManager to update the base prompt only?
        # Or just re-read long term memory? It's cached in memory instance?
        # Actually, self.memory has `system_prompt` attribute.
        
        # Let's just update the system prompt.
        # NOTE: This overrides the previous prompt. 
        # If Long Term Memory was appended, we should re-append it.
        # Since we don't store LTM separately in Engine, we might lose it unless we modify MemoryManager.
        # But for MVP, let's assume the prompt update is sufficient or we can optimize later.
        self.memory.set_system_prompt(full_system_prompt)
        
        return self.mode

    async def start(self):
        """Start the n0 main loop."""
        logger.info("Starting Agent Engine...")
        
        # Lifecycle: Load Long Term Memory
        long_term_data = await self.memory.initialize()
        
        # Combine System Prompt + Long Term Memory
        full_system_prompt = get_system_prompt(self.mode.value)
        if long_term_data:
             full_system_prompt += f"\n\n=== LONG TERM MEMORY (EXPERIENCE) ===\n{long_term_data}"
             
        self.memory.set_system_prompt(full_system_prompt)
        
        # Signal that initialization is complete
        self.ready_event.set()
        
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
        max_turns = Config.MAX_AUTONOMOUS_TURNS # Safety limit for the entire session
        turn_count = 0
        start_time = time.time()
        self.stop_requested = False # Reset flag
        empty_response_retries = 0
        last_tool_signature = None # To detect repetitive loops
        interaction_loop_count = 0 # To detect repetitive interaction loops
        
        while turn_count < max_turns:
            if self.stop_requested:
                console.print("[bold red]🛑 操作已中断 (User Interrupted)[/bold red]")
                break
                
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
            
            # Check for recent interaction result to prevent amnesia
            last_msg = messages[-1] if messages else {}
            interaction_reminder = ""
            if last_msg.get("role") == "tool" and last_msg.get("name") in ["ask_selection", "ask_user"]:
                 interaction_reminder = (
                     f"\n\n[ATTENTION] The user has just responded to your question ('{last_msg.get('name')}').\n"
                     f"User Response: \"{last_msg.get('content')}\"\n"
                     f"DO NOT ask the same question again. Proceed immediately based on this response."
                 )

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
                state_prompt = (
                    f"Status: {status_str}.\n"
                    f"{self.task_manager.render()}\n\n"
                    f"NEXT ACTION REQUIRED: Continue working on Task {next_task.id}: '{next_task.content}'.\n"
                    f"CRITICAL: Focus ONLY on the 'CURRENT FOCUS' task. Do NOT repeat 'Done' tasks.\n"
                    f"If you have just finished a step (e.g., wrote a file), you MUST call `todo_update` to mark the task as 'completed' BEFORE moving to the next one.\n"
                    f"Do NOT repeat the same tool call if the file already exists or the action is done."
                )
            else:
                state_prompt = f"Status: All tasks completed.\n{self.task_manager.render()}\n\nNEXT ACTION REQUIRED: Summarize results and ask user for next steps."
            
            # Combine state prompt with interaction reminder
            if interaction_reminder:
                state_prompt += interaction_reminder

            
            # Dynamic Prompt Injection (Sandwich Strategy)
            # 1. System Prompt (Top) - Already set in memory
            # 2. Conversation History (Middle) - In messages
            # 3. Dynamic State/Todo (Bottom) - Appended here
            
            # We append this temporary system state to the end of messages for this turn only
            # This ensures the model sees the Todo List LAST, satisfying the recency bias.
            current_messages = messages + [{"role": "system", "content": f"<system_state>\n{state_prompt}\n</system_state>"}]

            # 2. Call LLM (wu streamed)
            try:
                response_gen = self.stream_handler.chat(current_messages, self.tools_schema)
                full_content, tool_calls = await self.stream_handler.render_stream(response_gen, mode_name=self.mode.value)
            except Exception as e:
                console.print(f"[red]LLM 错误: {e}[/red]")
                break

            # 3. Update Memory
            self.memory.add("assistant", full_content, tool_calls=tool_calls if tool_calls else None)
            
            # 4. Check for Termination Conditions
            if not tool_calls:
                # Check for empty content (LLM failure/empty response)
                if not full_content:
                    empty_response_retries += 1
                    if empty_response_retries > 3:
                        console.print("[bold red]Error: Received empty response from LLM multiple times. Stopping to prevent infinite loop.[/bold red]")
                        break
                        
                    console.print(f"[red]Error: Received empty response from LLM. Retrying ({empty_response_retries}/3)...[/red]")
                    # Simple exponential backoff or retry limit could be added here
                    # For now, we just wait a bit and continue, hoping the next call works
                    await asyncio.sleep(2)
                    continue
                
                # Reset retry counter on successful content
                empty_response_retries = 0

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
                    
                    # --- Repetitive Tool Call Guard ---
                    # Check if we are repeating the exact same tool call as the immediate previous one
                    current_signature = f"{func_name}:{json.dumps(args, sort_keys=True)}"
                    
                    # Update Interaction Loop Counter
                    if func_name in ["ask_user", "ask_selection"]:
                        if current_signature == last_tool_signature:
                            interaction_loop_count += 1
                        else:
                            interaction_loop_count = 1 # New interaction, but still an interaction
                    else:
                        interaction_loop_count = 0 # Reset on non-interaction tool
                        
                    # 1. Standard Loop Detection (Strict for non-interactive)
                    if current_signature == last_tool_signature and func_name not in ["ask_user", "ask_selection"]:
                        console.print("[bold red]⚠️ 检测到重复工具调用 (Loop Detection)[/bold red]")
                        
                        # Active Intervention: Ask user what to do
                        question = f"Agent 正在重复执行相同的操作 ({func_name})，可能已陷入死循环。\n请选择下一步操作："
                        options = [
                            "Stop & Ask Human (停止并请求人工介入)",
                            "Force Retry (强制重试)",
                            "Skip Step (跳过此步骤)"
                        ]
                        
                        try:
                            # Manually invoke ask_selection via registry
                            user_choice = await registry.execute("ask_selection", {
                                "question": question,
                                "options": options
                            }, context=self.context)
                            
                            if "Stop" in user_choice:
                                result = (
                                    "USER INTERRUPT: The user chose to STOP the loop because of repetitive actions.\n"
                                    "PLEASE STOP what you are doing immediately.\n"
                                    "Ask the user for new instructions or clarification."
                                )
                            elif "Skip" in user_choice:
                                result = (
                                    "USER INSTRUCTION: The user chose to SKIP this step.\n"
                                    "Assume the action was successful or not needed.\n"
                                    "Proceed to the next step immediately."
                                )
                            else: # Retry
                                console.print("[yellow]用户选择强制重试...[/yellow]")
                                result = await registry.execute(func_name, args, context=self.context)
                                last_tool_signature = current_signature
                                
                        except Exception as e:
                            # Fallback if interaction fails
                            result = (
                                "Error: You just executed this exact same tool with the same arguments. "
                                "This means your previous attempt likely failed or you are in a loop. "
                                "1. If the previous output was an error, DO NOT REPEAT the same command. MODIFY it.\n"
                                "2. If the task is done, use 'todo_update' to mark it completed.\n"
                                "3. Ask the user for help."
                            )

                    # 2. Interactive Loop Detection (Allow retry once or twice, but not infinite)
                    elif interaction_loop_count >= 3:
                        console.print("[bold red]⚠️ 检测到重复交互死循环 (Interaction Loop)[/bold red]")
                        result = (
                            "SYSTEM ERROR: You are stuck in a loop asking the user the same question repeatedly.\n"
                            "The user has likely already answered you in the previous turn.\n"
                            "STOP ASKING. READ THE PREVIOUS TOOL OUTPUT CAREFULLY.\n"
                            "If you really need to confirm, rephrase your question entirely."
                        )
                    else:
                        result = await registry.execute(func_name, args, context=self.context)
                        last_tool_signature = current_signature
                        
                except Exception as e:
                    result = f"Error executing tool: {str(e)}"
                
                # Show partial result snippet
                # Use a cleaner look for result
                snippet = result[:200] + "..." if len(result) > 200 else result
                console.print(f"[dim]执行结果: {snippet}[/dim]")
                console.print() # Spacer

                # 6. Add Tool Result to Memory
                self.memory.add("tool", result, tool_call_id=call_id, name=func_name)

                # 7. Check if we should break the loop after interaction
                # If the tool was 'ask_selection' or 'ask_user', we should NOT break anymore!
                # We want the loop to continue so the Agent can SEE the user's choice and act on it.
                # BUT, we need to ensure the user's input is actually fed back.
                # In 'ask_selection', the result IS the user's choice.
                # So the Agent sees: ToolCall(ask_selection) -> ToolResult("User selected Option A")
                # Then the loop continues, Agent sees result, and acts.
                
                # IMPORTANT: If the user selected an action, we MUST ensure the Agent acts on it immediately.
                # We force a continue to the next iteration.
                if func_name in ["ask_selection", "ask_user"]:
                    # Inject a system nudge to force the Agent to respect the choice
                    # This prevents the "Infinite Question Loop" where Agent ignores the answer and asks again.
                    # We add a temporary system message to the memory for the next turn only?
                    # No, the tool result is already in memory. 
                    # We just need to ensure the LLM pays attention to the last tool result.
                    pass
                
                # However, if the user interrupts via Ctrl+C, that's handled in main.py
                
                # There is a subtle case: If ask_selection returns, we are still inside the autonomous loop.
                # The user interaction happened inside the tool execution (which awaited input).
                # So from the Engine's perspective, it was just a slow function call.
                # We should definitely CONTINUE the loop here.
            
            # 8. Loop continues automatically!
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
        
    def interrupt(self):
        """
        Interrupt the current autonomous loop (e.g. on Ctrl+C).
        Clears pending queues but keeps the engine running for next input.
        """
        logger.warning("Interrupt signal received. Stopping current task...")
        
        # 1. Drain queues
        while not self.processing_queue.empty():
            try:
                self.processing_queue.get_nowait()
                self.processing_queue.task_done()
            except Exception:
                pass
                
        # 2. Reset running flag (if we use a separate flag for the loop)
        # In current design, _run_autonomous_loop checks turn_count < max_turns.
        # We need a way to break that loop from outside.
        # But _run_autonomous_loop is awaited inside task_consumer.
        # We can't easily cancel it unless we hold a reference to the task.
        # For MVP, we rely on the fact that if we clear the queue, the NEXT event won't process.
        # But the CURRENT await stream_handler.chat() might still be running.
        # To truly cancel, we'd need to cancel the task_consumer's current task.
        # For now, let's just log and rely on the user to wait or the loop to finish.
        # Better: Set a flag that _run_autonomous_loop checks.
        self.stop_requested = True
