import asyncio
import sys
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from core.engine import AgentEngine
from utils.logger import logger, console
from core.config import Config

async def interactive_loop(engine: AgentEngine):
    session = PromptSession()
    console.print("[bold green]Easy-Coding-Agent[/bold green] initialized.")
    console.print(f"Model: [cyan]{Config.MODEL_NAME}[/cyan] | API: [cyan]ZhipuAI[/cyan]")
    console.print("Type '/exit' to quit.\n")

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
                user_input = await session.prompt_async("❯ ")
            
            if not user_input.strip():
                continue
                
            if user_input.strip().lower() == '/exit':
                engine.stop()
                break
                
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
            
            # If we show prompt immediately, it interleave with the running agent logs.
            # We need to block here until the agent is "done" with the current request.
            
            await engine.processing_queue.join() 
            # This waits until processing_queue is empty and all tasks done.
            # task_consumer marks task_done() AFTER handle_user_input returns.
            # So this effectively waits for the whole autonomous loop to finish!
            
        except (EOFError, KeyboardInterrupt):
            await engine.push_event("stop", None)
            break

async def main():
    Config.validate()
    engine = AgentEngine()
    
    # Run engine background task and interactive loop concurrently
    # We use create_task for engine.start() because it runs forever until stopped
    engine_task = asyncio.create_task(engine.start())
    
    try:
        await interactive_loop(engine)
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
