"""Native asynchronous streaming; partial responses are never executed."""
import asyncio
import json
import uuid
from urllib.parse import urlsplit
import httpx
from openai import AsyncOpenAI
from .retry import retryable
from .errors import OutputLimitError


class Provider:
    def __init__(self, settings):
        self.settings = settings
        self.client = None
        self.native = None

    async def complete(self, messages, tools, emit):
        for attempt in range(self.settings.network_retries + 1):
            ident = uuid.uuid4().hex
            self.last_usage = {}
            emit("request_start", {"id":ident})
            emitted = False
            def forward(event, data):
                nonlocal emitted
                if event == "text" and data:
                    emitted = True
                emit(event, data)
            try:
                status = 'failed'
                try:
                    result = await self._complete(messages, tools, forward)
                    self.last_usage = result[1]
                    status = 'complete'
                    return result
                except asyncio.CancelledError:
                    status = 'cancelled'
                    raise
                finally:
                    emit("request_end", {"id":ident,"usage":self.last_usage,"status":status})
            except Exception as exc:
                if emitted or not retryable(exc) or attempt == self.settings.network_retries:
                    raise
                delay = min(2 ** attempt, 8)
                emit("notice", f"Transient model request failure. Retry {attempt + 1}/{self.settings.network_retries} in {delay}s; no tools have run for this request.")
                await asyncio.sleep(delay)

    async def _complete(self, messages, tools, emit):
        if self.settings.api_format == "anthropic":
            from .anthropic import AnthropicProvider
            if self.native is None:
                self.native = AnthropicProvider(self.settings)
            return await self.native.complete(messages, tools, emit,
                usage_callback=lambda usage: setattr(self, 'last_usage', dict(usage)))
        if not self.settings.api_key:
            raise ValueError("Missing API key. Set ECA_API_KEY, OPENAI_API_KEY or MODELSCOPE_API_KEY in the environment/.env.")
        if self.client is None:
            # Loopback model servers must not be routed through an OS HTTP proxy.
            local = urlsplit(self.settings.base_url).hostname in {"localhost", "127.0.0.1", "::1"}
            self.client = AsyncOpenAI(api_key=self.settings.api_key, base_url=self.settings.base_url,
                                      timeout=self.settings.request_timeout, max_retries=0,
                                      http_client=httpx.AsyncClient(trust_env=not local))
        if self.settings.api_format == "responses":
            from .responses import complete
            return await complete(self.client, self.settings, messages, tools, emit,
                                  lambda usage: setattr(self, 'last_usage', usage))
        kwargs = {"model": self.settings.model, "messages": [{k: v for k, v in m.items() if k in {"role", "content", "tool_calls", "tool_call_id"}} for m in messages], "stream": True,
                  "max_tokens": self.settings.max_output_tokens}
        if self.settings.reasoning_effort:
            kwargs["reasoning_effort"] = self.settings.reasoning_effort
        if tools:
            kwargs["tools"] = tools
        if self.settings.stream_usage:
            kwargs["stream_options"] = {"include_usage": True}
        stream = await self.client.chat.completions.create(**kwargs)
        content, calls, usage, finish = "", {}, {}, None
        try:
            async for chunk in stream:
                if chunk.usage:
                    usage = chunk.usage.model_dump()
                    self.last_usage = usage
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
        if finish == 'length':
            raise OutputLimitError()
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
        if self.native:
            await self.native.close()
        if self.client:
            await self.client.close()
