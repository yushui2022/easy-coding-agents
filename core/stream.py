import asyncio
from concurrent.futures import ThreadPoolExecutor
from core.config import Config
from utils.logger import logger, console
from typing import Optional
from openai import OpenAI

class StreamHandler:
    """
    Handles real-time streaming response from LLM (wu).
    Uses a separate thread for the synchronous API call and an async queue for consumption.
    """
    
    def __init__(self):
        self.client: Optional[object] = None
        if not Config.api_key():
            logger.warning(f"{Config.provider_label()} API key 未配置，无法调用模型 API")
        else:
            self.client = OpenAI(base_url=Config.base_url(), api_key=Config.api_key())
            logger.info(f"LLM provider initialized: {Config.provider_label()} / {Config.MODEL_NAME}")
        self.executor = ThreadPoolExecutor(max_workers=1)

    async def chat(self, messages, tools):
        """Async wrapper for OpenAI-compatible streaming chat."""
        if not self.client:
            raise ValueError("API Key missing")

        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()

        def _producer():
            retries = 3
            backoff = 1
            
            for attempt in range(retries):
                try:
                    response = self.client.chat.completions.create(
                        model=Config.MODEL_NAME,
                        messages=messages,
                        tools=tools,
                        stream=True,
                        temperature=Config.LLM_TEMPERATURE
                    )
                    for chunk in response:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
                    loop.call_soon_threadsafe(queue.put_nowait, None) # Sentinel
                    return # Success, exit function
                    
                except Exception as e:
                    if attempt < retries - 1:
                        logger.warning(f"Stream error (attempt {attempt+1}/{retries}): {e}. Retrying in {backoff}s...")
                        import time
                        time.sleep(backoff)
                        backoff *= 2
                    else:
                        logger.error(f"Stream failed after {retries} attempts: {e}")
                        loop.call_soon_threadsafe(queue.put_nowait, None)

        # Start producer in thread
        loop.run_in_executor(self.executor, _producer)

        # Consume from queue
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

    async def complete(self, messages, tools=None):
        """Non-streaming chat call for hidden guard/repair passes."""
        if not self.client:
            raise ValueError("API Key missing")

        loop = asyncio.get_running_loop()

        def _call():
            payload = {
                "model": Config.MODEL_NAME,
                "messages": messages,
                "stream": False,
                "temperature": Config.LLM_TEMPERATURE,
            }
            if tools:
                payload["tools"] = tools
            response = self.client.chat.completions.create(**payload)
            message = response.choices[0].message
            tool_calls = []
            for tc in getattr(message, "tool_calls", None) or []:
                tool_calls.append({
                    "id": getattr(tc, "id", "") or "",
                    "type": getattr(tc, "type", "function") or "function",
                    "function": {
                        "name": getattr(getattr(tc, "function", None), "name", "") or "",
                        "arguments": getattr(getattr(tc, "function", None), "arguments", "") or "",
                    },
                })
            return message.content or "", tool_calls

        return await loop.run_in_executor(self.executor, _call)

    async def render_stream(self, stream_generator, mode_name: str = None):
        """Render stream to console and aggregate full response."""
        full_content = ""
        tool_calls = []
        
        # Determine prefix based on mode
        prefix = "AI"
        if mode_name:
             prefix = f"[{mode_name}模式]"
        
        # We print the header once
        console.print(f"\n[bold cyan]{prefix}[/bold cyan] ", end="")
        
        # Debug: Track if we received ANY content
        has_received_content = False

        async for chunk in stream_generator:
            # Safety check for invalid chunks (e.g. ModelScope occasional None choices)
            if not chunk:
                # Debug logging for empty chunks
                # logger.debug("Received empty chunk")
                continue
                
            choices = getattr(chunk, "choices", None)
            if not choices:
                # Debug logging for chunks without choices (e.g. usage info)
                # logger.debug(f"Received chunk without choices: {chunk}")
                continue
                
            # Check if choices[0] is valid
            if len(choices) == 0:
                continue
                
            delta = choices[0].delta
            
            # Handle Text
            if delta.content:
                has_received_content = True
                content_chunk = delta.content
                # Simple streaming output
                # For more advanced Markdown rendering, we would need a Live display,
                # but partial markdown is hard to render correctly.
                # Printing raw text is safer for code blocks.
                safe_chunk = content_chunk.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
                try:
                    print(safe_chunk, end="", flush=True)
                except UnicodeEncodeError:
                    print(safe_chunk.encode("ascii", errors="replace").decode("ascii"), end="", flush=True)
                full_content += content_chunk
                
            # Handle Tool Calls
            if getattr(delta, "tool_calls", None):
                has_received_content = True
                for tc in delta.tool_calls:
                    index = tc.index
                    
                    if index is not None:
                        while len(tool_calls) <= index:
                            tool_calls.append({
                                "id": "", 
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            })
                            
                        # Update fields
                        if getattr(tc, "id", None):
                            tool_calls[index]["id"] = tc.id
                        if getattr(tc, "function", None):
                            if getattr(tc.function, "name", None):
                                tool_calls[index]["function"]["name"] += tc.function.name
                            if getattr(tc.function, "arguments", None):
                                tool_calls[index]["function"]["arguments"] += tc.function.arguments

        print() # Newline
        
        if not has_received_content:
             console.print("[dim yellow](No content received from LLM)[/dim yellow]")
             # Add debug info if full_content is empty
             if not full_content and not tool_calls:
                 logger.warning("RenderStream finished with empty content and no tool calls.")
             
        return full_content, tool_calls
