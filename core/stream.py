import asyncio
from concurrent.futures import ThreadPoolExecutor
from zhipuai import ZhipuAI
from core.config import Config
from utils.logger import logger, console

class StreamHandler:
    """
    Handles real-time streaming response from LLM (wu).
    Uses a separate thread for the synchronous API call and an async queue for consumption.
    """
    
    def __init__(self):
        if not Config.ZHIPU_API_KEY:
            logger.warning("ZHIPU_API_KEY not set. API calls will fail.")
            self.client = None
        else:
            self.client = ZhipuAI(api_key=Config.ZHIPU_API_KEY)
        self.executor = ThreadPoolExecutor(max_workers=1)

    async def chat(self, messages, tools):
        """Async wrapper for ZhipuAI synchronous stream."""
        if not self.client:
            raise ValueError("API Key missing")

        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()

        def _producer():
            try:
                response = self.client.chat.completions.create(
                    model=Config.MODEL_NAME,
                    messages=messages,
                    tools=tools,
                    stream=True,
                    do_sample=True,
                    temperature=0.1
                )
                for chunk in response:
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
                loop.call_soon_threadsafe(queue.put_nowait, None) # Sentinel
            except Exception as e:
                logger.error(f"Stream error: {e}")
                loop.call_soon_threadsafe(queue.put_nowait, None)

        # Start producer in thread
        loop.run_in_executor(self.executor, _producer)

        # Consume from queue
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

    async def render_stream(self, stream_generator):
        """Render stream to console and aggregate full response."""
        full_content = ""
        tool_calls = []
        
        # We print the header once
        console.print(f"\n[bold cyan]AI[/bold cyan] ", end="")
        
        async for chunk in stream_generator:
            delta = chunk.choices[0].delta
            
            # Handle Text
            if delta.content:
                content_chunk = delta.content
                # Simple streaming output
                # For more advanced Markdown rendering, we would need a Live display,
                # but partial markdown is hard to render correctly.
                # Printing raw text is safer for code blocks.
                print(content_chunk, end="", flush=True)
                full_content += content_chunk
                
            # Handle Tool Calls
            if delta.tool_calls:
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
                        if tc.id:
                            tool_calls[index]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls[index]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls[index]["function"]["arguments"] += tc.function.arguments

        print() # Newline
        return full_content, tool_calls
