import asyncio
import sys
from typing import List, Optional
import questionary
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import Completer, Completion
from core.engine import AgentEngine
from utils.logger import logger, console
from utils.ui import render_splash_screen
from core.config import Config
from tools.base import registry
import re

async def interactive_loop(engine: AgentEngine, session: PromptSession):
    # Wait for engine to initialize (and output logs)
    await engine.ready_event.wait()
    
    # Render Splash Screen
    render_splash_screen()

    # Key Bindings
    bindings = KeyBindings()

    @bindings.add('s-tab')
    def _(event):
        """Toggle Agent Mode."""
        new_mode = engine.toggle_mode()
        # Invalidate UI to refresh toolbar/prompt
        event.app.invalidate()

    class SlashCommandCompleter(Completer):
        def __init__(self):
            self.top = {
                "agent": "管理自定义Agent",
                "exit": "退出程序",
                "create": "创建Agent",
                "list": "列出Agent"
            }
            self.agent_sub = {
                "create": "创建Agent",
                "list": "列出Agent",
                "use": "切换使用Agent",
                "enable": "启用Agent",
                "disable": "禁用Agent",
                "edit": "编辑Agent",
                "delete": "删除Agent",
                "share": "生成分享链接",
                "preview": "预览Agent定义"
            }
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if not text.startswith("/"):
                return
            body = text[1:]
            parts = body.split()
            if len(parts) == 0:
                for key, meta in self.top.items():
                    token = key + (" " if key in ["use", "enable", "disable", "edit", "delete", "share", "preview"] else "")
                    yield Completion(token, start_position=0, display=token, display_meta=meta)
                return
            first = parts[0]
            if len(parts) == 1 and not text.endswith(" "):
                for key, meta in self.top.items():
                    if key.startswith(first):
                        token = key + (" " if key in ["use", "enable", "disable", "edit", "delete", "share", "preview"] else "")
                        yield Completion(token, start_position=-len(first), display=token, display_meta=meta)
                return
            if first != "agent":
                for key, meta in self.top.items():
                    if key.startswith(first):
                        yield Completion(key, start_position=-len(first), display=key, display_meta=meta)
                return
            sub_partial = parts[1] if len(parts) > 1 else ""
            for key, meta in self.agent_sub.items():
                token = key + (" " if key in ["use", "enable", "disable", "edit", "delete", "share", "preview"] else "")
                if token.startswith(sub_partial):
                    yield Completion(token, start_position=-len(sub_partial), display=token, display_meta=meta)
                elif not sub_partial:
                    yield Completion(token, start_position=0, display=token, display_meta=meta)
    slash_completer = SlashCommandCompleter()

    def get_bottom_toolbar():
        mode_color = {
            "Plan": "ansiblue",
            "Code": "ansigreen",
            "Chat": "ansimagenta"
        }.get(engine.mode.value, "white")
        agent = getattr(engine.context, "current_agent", None)
        agent_label = ""
        if agent:
            hex_color = agent.get("color", "#4CAF50")
            agent_label = f' | Agent: <style bg="{hex_color}" fg="white"> @{agent.get("name")} </style> '
        usage_percent = engine.context.memory_manager.get_usage_percent()
        usage_color = "ansigreen" if usage_percent < 50 else ("ansiyellow" if usage_percent < 80 else "ansired")
        usage_label = f' | Context: <style fg="{usage_color}">{usage_percent}%</style> '
        return HTML(f' <b>[Shift+Tab]</b> Mode: <style bg="{mode_color}" fg="white"> {engine.mode.value} </style>{agent_label}{usage_label} ')

    async def handle_agent_create():
        name = await questionary.text("输入Agent名称:").ask_async()
        desc = await questionary.text("输入基础功能描述 (可多行，完成后按Enter):").ask_async()
        palette = [
            "blue", "green", "red", "purple", "orange", "teal", "cyan", "indigo", "Custom Hex (#RRGGBB)"
        ]
        color_choice = await questionary.select("选择颜色标签:", choices=palette).ask_async()
        if "Custom Hex" in color_choice:
            hex_color = await questionary.text("输入16进制颜色码 (如 #4CAF50):").ask_async()
        else:
            hex_color = color_choice
        result = await registry.execute("agent_create", {"name": name, "description": desc, "color": hex_color})
        console.print(result)

    async def handle_agent_command(cmd: str) -> bool:
        """
        Returns True if a command was handled and should not be forwarded to engine.
        """
        if not cmd.startswith("/agent"):
            if cmd.startswith("/"):
                alias = cmd.strip().split()[0][1:]
                agent_aliases = ["create", "list"]
                if alias in agent_aliases:
                    cmd = f"/agent {cmd.strip()[1:]}"
                else:
                    return False
            else:
                return False
        parts = cmd.strip().split()
        if len(parts) == 1 or parts[1] == "help":
            console.print("用法: /agent [create|list|use|enable|disable|edit|delete|share|preview]\n示例: /agent create, /agent use MyAgent, /agent list, /agent preview <id>")
            return True
        sub = parts[1].lower()
        if sub == "create":
            await handle_agent_create()
            return True
        if sub == "list":
            result = await registry.execute("agent_list", {})
            console.print(result)
            return True
        if sub == "use" and len(parts) >= 3:
            ident = " ".join(parts[2:])
            result = await registry.execute("agent_use", {"identifier": ident}, context=engine.context)
            console.print(result)
            return True
        if sub in ["enable", "disable"] and len(parts) >= 3:
            aid = parts[2]
            enabled = sub == "enable"
            result = await registry.execute("agent_update", {"id": aid, "enabled": enabled})
            console.print(result)
            return True
        if sub == "delete" and len(parts) >= 3:
            aid = parts[2]
            result = await registry.execute("agent_delete", {"id": aid})
            console.print(result)
            return True
        if sub == "share" and len(parts) >= 3:
            aid = parts[2]
            result = await registry.execute("agent_share", {"id": aid})
            console.print(result)
            return True
        if sub == "preview" and len(parts) >= 3:
            aid = parts[2]
            result = await registry.execute("agent_preview", {"id": aid})
            console.print(result)
            return True
        if sub == "edit" and len(parts) >= 3:
            aid = parts[2]
            # Simple interactive edit: name/desc/color
            name = await questionary.text("修改名称(留空不变):").ask_async()
            desc = await questionary.text("修改描述(留空不变):").ask_async()
            color = await questionary.text("修改颜色(留空不变，如 #4CAF50 或 blue):").ask_async()
            payload = {"id": aid}
            if name.strip(): payload["name"] = name
            if desc.strip(): payload["description"] = desc
            if color.strip(): payload["color"] = color
            result = await registry.execute("agent_update", payload)
            console.print(result)
            return True
        console.print("未知子命令。输入 /agent help 查看用法。")
        return True

    while engine.running:
        try:
            # Only prompt if engine is idle (input queue empty AND processing queue empty)
            # But here we are the producer. We should wait for user input.
            # The issue is: patch_stdout context might be interfering if we print inside the loop?
            # No, patch_stdout is fine.
            
            # Key fix: Check if we really need input.
            # The engine loop handles autonomy internally.
            # When engine.handle_user_input returns, it means the autonomous loop has FINISHED (stopped or paused).
            # So we are ready for new input.
            
            with patch_stdout(raw=True):
                agent = getattr(engine.context, "current_agent", None)
                agent_tag = ""
                if agent:
                    hex_color = agent.get("color", "#4CAF50")
                    agent_name = agent.get("name")
                    agent_tag = f'<style bg="{hex_color}" fg="white"> {agent_name} </style> '
                prompt_text = HTML(f'{agent_tag}[{engine.mode.value}] ❯ ')
                user_input = await session.prompt_async(
                    prompt_text,
                    key_bindings=bindings,
                    bottom_toolbar=get_bottom_toolbar,
                    completer=slash_completer
                )
            
            if not user_input.strip():
                continue
                
            if user_input.strip().lower() == '/exit':
                engine.stop()
                break
            
            # Handle /agent commands
            if await handle_agent_command(user_input.strip()):
                # After command, refresh UI
                continue
            
            # Handle @Agent shortcut: @Name message
            m = re.match(r"^@([A-Za-z0-9_\-]+)\s*(.*)$", user_input.strip())
            if m:
                ident = m.group(1)
                message = m.group(2) or ""
                result = await registry.execute("agent_use", {"identifier": ident, "context": engine.context})
                console.print(result)
                if not message:
                    continue
                await engine.push_event("user_input", message)
            else:
                await engine.push_event("user_input", user_input)
            
            # Wait for processing to "settle" before showing prompt again?
            # engine.push_event is async but puts into queue.
            # We want to wait until the engine is done processing this batch.
            # But Engine runs in background tasks.
            # We need a way to know "Engine is Idle".
            
            # Simple hack: Sleep a bit to let logs flush? No.
            # The real fix is that input_consumer -> processing_queue -> task_consumer
            # task_consumer calls handle_user_input which AWAITS _run_autonomous_loop.
            # So the task_consumer is BLOCKED until the loop finishes.
            # BUT, main.py is just pushing to queue. It doesn't know when task is done.
            
            # 3. Wait for processing to complete (Non-blocking Join)
            # We want to wait for the queue to be empty, BUT also listen for Ctrl+C.
            # queue.join() is a blocking await that cannot be easily cancelled by KeyboardInterrupt 
            # if it's running in the main loop directly without a task wrapper?
            # Actually, await is cancellable.
            
            try:
                # Create a task for the join operation
                join_task = asyncio.create_task(engine.processing_queue.join())
                await join_task
            except asyncio.CancelledError:
                # This happens if WE cancel it (not likely here)
                pass
            except KeyboardInterrupt:
                # User pressed Ctrl+C during execution
                console.print("\n[bold yellow]⚠️ 检测到中断信号 (Ctrl+C)...[/bold yellow]")
                engine.interrupt()
                
                # Cancel the join task if it's still waiting
                if not join_task.done():
                    join_task.cancel()
                    try:
                        await join_task
                    except asyncio.CancelledError:
                        pass
                
                # Wait a bit for cleanup?
                await asyncio.sleep(0.5)
                console.print("[dim]已返回主菜单。[/dim]\n")
                continue # Back to prompt
            
        except (EOFError):
            await engine.push_event("stop", None)
            break
        except KeyboardInterrupt:
             # This catches Ctrl+C at the prompt level (handled by PromptSession usually, but just in case)
             await engine.push_event("stop", None)
             break

async def main():
    try:
        Config.validate()
    except ValueError as e:
        console.print(f"[bold red]Configuration Error:[/bold red] {e}")
        return

    # Initialize shared PromptSession
    session = PromptSession()

    # Define async input provider
    async def async_input(prompt_text: str) -> str:
        """
        Callback for Agent to request input.
        Uses the same PromptSession to ensure thread safety and history.
        """
        # Ensure prompt text ends with space if needed
        if not prompt_text.endswith(" "):
            prompt_text += " "
            
        console.print(f"\n[bold yellow]❓ Question:[/bold yellow] {prompt_text}")
        with patch_stdout(raw=True):
            # We use a distinct prompt symbol for agent questions
            return await session.prompt_async("  ➜ ")

    async def async_selection(question: str, options: List[str]) -> str:
        """
        Callback for Agent to request selection.
        Uses questionary for interactive menu.
        """
        console.print(f"\n[bold yellow]❓ {question}[/bold yellow]")
        
        try:
            # questionary.select uses prompt_toolkit internally.
            # We use ask_async() for non-blocking execution
            choice = await questionary.select(
                "请选择一个选项 (使用上下键选择，回车确认):",
                choices=options,
                style=questionary.Style([
                    ('qmark', 'fg:#E91E63 bold'),
                    ('question', 'bold'),
                    ('answer', 'fg:#2196f3 bold'),
                    ('pointer', 'fg:#673ab7 bold'),
                    ('highlighted', 'fg:#673ab7 bold'),
                    ('selected', 'fg:#cc5454'),
                    ('separator', 'fg:#cc5454'),
                    ('instruction', ''),
                    ('text', ''),
                    ('disabled', 'fg:#858585 italic')
                ])
            ).ask_async()
            
            # Check for self-choice keywords
            if "自己选择" in choice or "Self Choice" in choice or "Custom Input" in choice:
                return await async_input("请输入您的自定义指令:")
            
            return choice
            
        except Exception as e:
            logger.error(f"Selection error: {e}")
            return str(e)

    # Inject input provider into Engine
    engine = AgentEngine(input_func=async_input, selection_func=async_selection)
    
    # Run engine background task and interactive loop concurrently
    # We use create_task for engine.start() because it runs forever until stopped
    engine_task = asyncio.create_task(engine.start())
    
    try:
        await interactive_loop(engine, session)
    finally:
        engine.stop()
        # Cancel the engine task if it's still running
        if not engine_task.done():
            engine_task.cancel()
            try:
                await engine_task
            except asyncio.CancelledError:
                pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
