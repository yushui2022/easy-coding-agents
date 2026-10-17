"""Native asynchronous streaming; partial responses are never executed."""
import json
from urllib.parse import urlsplit
import httpx
from openai import AsyncOpenAI


class Provider:
    def __init__(self, settings):
        self.settings = settings
        self.client = None

    async def complete(self, messages, tools, emit):
        if not self.settings.api_key:
            raise ValueError("Missing API key. Set ECA_API_KEY, OPENAI_API_KEY or MODELSCOPE_API_KEY in the environment/.env.")
        if self.client is None:
            # Loopback model servers must not be routed through an OS HTTP proxy.
            local = urlsplit(self.settings.base_url).hostname in {"localhost", "127.0.0.1", "::1"}
            self.client = AsyncOpenAI(api_key=self.settings.api_key, base_url=self.settings.base_url,
                                      timeout=self.settings.request_timeout, max_retries=2,
                                      http_client=httpx.AsyncClient(trust_env=not local))
        kwargs = {"model": self.settings.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
        stream = await self.client.chat.completions.create(**kwargs)
        content, calls, usage, finish = "", {}, {}, None
        try:
            async for chunk in stream:
                if chunk.usage:
                    usage = chunk.usage.model_dump()
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish = choice.finish_reason
                delta = choice.delta
                if delta.content:
                    content += delta.content
                    emit("text", delta.content)
                for tc in delta.tool_calls or []:
                    call = calls.setdefault(tc.index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    if tc.id:
                        call["id"] = tc.id
                    if tc.function:
                        call["function"]["name"] += tc.function.name or ""
                        call["function"]["arguments"] += tc.function.arguments or ""
        finally:
            await stream.close()
        if finish not in {"stop", "tool_calls"}:
            raise RuntimeError(f"Incomplete model response ({finish or 'disconnected'}); no tools were executed.")
        if not content and not calls:
            raise RuntimeError("Model returned an empty response")
        ordered = [calls[i] for i in sorted(calls)]
        ids = set()
        for call in ordered:
            if not call["id"] or call["id"] in ids or not call["function"]["name"]:
                raise RuntimeError("Invalid tool-call identity in model response")
            ids.add(call["id"])
            if not isinstance(json.loads(call["function"]["arguments"]), dict):
                raise RuntimeError("Tool arguments must be an object")
        message = {"role": "assistant", "content": content or None}
        if ordered:
            message["tool_calls"] = ordered
        return message, usage

    async def close(self):
        if self.client:
            await self.client.close()
