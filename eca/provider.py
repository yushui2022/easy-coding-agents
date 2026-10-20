"""Native asynchronous streaming; partial responses are never executed."""
import asyncio
import json
import uuid
import time
import hashlib
from urllib.parse import urlsplit
import httpx
from openai import AsyncOpenAI
from .retry import retryable
from .errors import OutputLimitError, ContextLimitError, StalledStreamError, context_rejection
from .activity import StreamActivity


class Provider:
    def __init__(self, settings):
        self.settings = settings
        self.client = None
        self.native = None
        self.last_metrics = {}

    async def complete(self, messages, tools, emit):
        for attempt in range(self.settings.network_retries + 1):
            ident = uuid.uuid4().hex
            self.last_usage = {}
            started_at = time.perf_counter()
            self.last_metrics = {}
            emit("request_start", {"id":ident})
            activity = StreamActivity(ident, emit)
            emitted = False
            def forward(event, data):
                nonlocal emitted
                if event == 'model_delta':
                    activity.observe(**data)
                    return
                if event == "text" and data:
                    emitted = True
                    activity.observe(text=data)
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
                    self.last_metrics.update(activity.snapshot(self.last_usage))
                    emit("request_end", {"id":ident,"usage":self.last_usage,"status":status,
                                         'elapsed_ms': round((time.perf_counter()-started_at)*1000), **self.last_metrics})
            except Exception as exc:
                if getattr(exc, 'status_code', None) in {400, 415, 422} and any(
                        any(a.get('mime', '').startswith('image/') for a in m.get('attachments', []))
                        for m in messages):
                    raise ValueError('模型服务拒绝了含图片的请求。请切换到支持图片输入的模型后继续，或新建不含图片的会话。') from None
                if not emitted and context_rejection(getattr(exc, 'status_code', None), getattr(exc, 'body', None)):
                    raise ContextLimitError() from None
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
        deepseek = self.settings.api_format == 'openai' and self.settings.model.lower().startswith('deepseek')
        scope = hashlib.sha256((self.settings.base_url.rstrip('/')+'|'+self.settings.model).encode()).hexdigest()
        payload_messages = []
        for original in messages:
            message = {k: v for k, v in original.items() if k in {'role', 'content', 'tool_calls', 'tool_call_id'}}
            if original.get('attachments'):
                from .attachments import content
                message['content'] = content(original, self.settings.root)
            if deepseek and tools and message['role'] == 'assistant':
                # Provider replay data is scoped to the model and endpoint, never shown as UI prose.
                message['reasoning_content'] = original.get('reasoning_content', '') if original.get('reasoning_scope') == scope else ''
            payload_messages.append(message)
        kwargs = {"model": self.settings.model, "messages": payload_messages, "stream": True,
                  "max_tokens": self.settings.max_output_tokens}
        if self.settings.reasoning_effort:
            kwargs["reasoning_effort"] = self.settings.reasoning_effort
        if self.settings.thinking_mode != 'default':
            if not deepseek:
                raise ValueError('Thinking presets currently require a DeepSeek Chat-compatible model; select service default for other models.')
            fast = self.settings.thinking_mode == 'fast'
            kwargs['extra_body'] = {'thinking': {'type': 'disabled' if fast else 'enabled'}}
            kwargs.pop('reasoning_effort', None)
            if not fast:
                kwargs['reasoning_effort'] = 'low' if self.settings.thinking_mode == 'balanced' else 'high'
        if tools:
            kwargs["tools"] = tools
        if self.settings.stream_usage:
            kwargs["stream_options"] = {"include_usage": True}
        stream = await self.client.chat.completions.create(**kwargs)
        content, calls, usage, finish = "", {}, {}, None
        reasoning = ''
        # A connected stream can stall while the provider keeps the socket warm with
        # empty keep-alive chunks. Only real content resets this clock, so a silent
        # stream fails with a clear message instead of waiting forever.
        idle = max(1, int(self.settings.request_timeout))
        last_content = time.monotonic()
        chunks = stream.__aiter__()
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(chunks.__anext__(), timeout=idle)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    raise StalledStreamError(idle) from None
                if chunk.usage:
                    usage = chunk.usage.model_dump()
                    self.last_usage = usage
                if not chunk.choices:
                    if time.monotonic() - last_content > idle:
                        raise StalledStreamError(idle)
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish = choice.finish_reason
                delta = choice.delta
                produced = False
                thought = getattr(delta, 'reasoning_content', None)
                if isinstance(thought, str) and thought:
                    produced = True
                    emit('model_delta', {'reasoning': thought})
                    if deepseek:
                        reasoning += thought
                if delta.content:
                    produced = True
                    content += delta.content
                    emit("text", delta.content)
                for tc in delta.tool_calls or []:
                    produced = True
                    call = calls.setdefault(tc.index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    if tc.id:
                        call["id"] = tc.id
                    if tc.function:
                        call["function"]["name"] += tc.function.name or ""
                        call["function"]["arguments"] += tc.function.arguments or ""
                        emit('model_delta', {'tool': call['function']['name'],
                                            'arguments': tc.function.arguments or ''})
                if produced:
                    last_content = time.monotonic()
                elif time.monotonic() - last_content > idle:
                    raise StalledStreamError(idle)
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
        if deepseek and reasoning:
            message.update(reasoning_content=reasoning, reasoning_scope=scope)
        if ordered:
            message["tool_calls"] = ordered
        return message, usage

    async def close(self):
        if self.native:
            await self.native.close()
        if self.client:
            await self.client.close()
