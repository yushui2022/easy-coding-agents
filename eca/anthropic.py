"""Anthropic Messages adapter using the same durable conversation format as ECA.

Only text and client tool use are supported. Thinking/server-tool blocks are
rejected rather than silently discarding data needed by the next request.
"""
import json
from urllib.parse import urlsplit

import httpx


def messages_payload(messages, tools, settings):
    system, turns = [], []
    for message in messages:
        role, content = message["role"], message.get("content")
        if role == "system":
            if content:
                system.append(content)
            continue
        blocks = []
        if role == "tool":
            role = "user"
            blocks.append({"type": "tool_result", "tool_use_id": message["tool_call_id"],
                           "content": content or ""})
        else:
            if role not in {"user", "assistant"}:
                raise ValueError(f"Unsupported conversation role: {role}")
            if content:
                blocks.append({"type": "text", "text": content})
            for call in message.get("tool_calls", []):
                blocks.append({"type": "tool_use", "id": call["id"],
                               "name": call["function"]["name"],
                               "input": json.loads(call["function"]["arguments"])})
        if not blocks:
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].extend(blocks)
        else:
            turns.append({"role": role, "content": blocks})
    payload = {"model": settings.model, "max_tokens": settings.max_output_tokens,
               "stream": True, "messages": turns}
    if system:
        payload["system"] = "\n\n".join(system)
    if tools:
        payload["tools"] = [{"name": t["function"]["name"],
                             "description": t["function"].get("description", ""),
                             "input_schema": t["function"]["parameters"]} for t in tools]
    return payload


async def sse_events(response):
    """Decode SSE frames, including comments and multi-line data fields."""
    data = []
    async for line in response.aiter_lines():
        if not line:
            if data:
                yield json.loads("\n".join(data))
                data = []
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
    # An unterminated event is not committed: callers require message_stop.


class AnthropicProvider:
    def __init__(self, settings):
        self.settings = settings
        self.client = None

    async def close(self):
        if self.client:
            await self.client.aclose()

    async def complete(self, messages, tools, emit):
        settings = self.settings
        if not settings.api_key:
            raise ValueError("Missing Anthropic API key. Set ANTHROPIC_API_KEY or ECA_API_KEY.")
        if self.client is None:
            local = urlsplit(settings.base_url).hostname in {"localhost", "127.0.0.1", "::1"}
            self.client = httpx.AsyncClient(timeout=settings.request_timeout, trust_env=not local)
        base = settings.base_url.rstrip("/")
        url = base + ("/messages" if base.endswith("/v1") else "/v1/messages")
        blocks, closed, usage = {}, set(), {}
        started = stopped = False
        finish = None
        async with self.client.stream("POST", url,
                headers={"x-api-key": settings.api_key, "anthropic-version": "2023-06-01"},
                json=messages_payload(messages, tools, settings)) as response:
            if response.status_code != 200:
                # Provider bodies can echo request data; avoid persisting secrets.
                raise RuntimeError(f"Anthropic HTTP {response.status_code}; check credentials, model and endpoint.")
            async for event in sse_events(response):
                kind = event.get("type")
                if kind == "error":
                    raise RuntimeError("Anthropic stream reported an error; no tools were executed.")
                if kind == "message_start":
                    if started:
                        raise RuntimeError("Duplicate Anthropic message_start")
                    started = True
                    usage.update(event["message"].get("usage", {}))
                elif kind == "content_block_start":
                    index, block = event["index"], dict(event["content_block"])
                    if not started or index in blocks or finish is not None:
                        raise RuntimeError("Invalid Anthropic block sequence")
                    if block["type"] not in {"text", "tool_use"}:
                        raise RuntimeError("Unsupported Anthropic content block; thinking and server tools are not enabled.")
                    if block["type"] == "text" and block.get("text"):
                        emit("text", block["text"])
                    block["partial_json"] = ""
                    blocks[index] = block
                elif kind == "content_block_delta":
                    index, delta = event["index"], event["delta"]
                    if index not in blocks or index in closed:
                        raise RuntimeError("Invalid Anthropic block delta")
                    block = blocks[index]
                    if delta["type"] == "text_delta" and block["type"] == "text":
                        block["text"] = block.get("text", "") + delta["text"]
                        emit("text", delta["text"])
                    elif delta["type"] == "input_json_delta" and block["type"] == "tool_use":
                        block["partial_json"] += delta["partial_json"]
                    else:
                        raise RuntimeError("Unsupported Anthropic block delta")
                elif kind == "content_block_stop":
                    index = event["index"]
                    if index not in blocks or index in closed:
                        raise RuntimeError("Invalid Anthropic block stop")
                    closed.add(index)
                elif kind == "message_delta":
                    finish = event.get("delta", {}).get("stop_reason") or finish
                    usage.update(event.get("usage", {}))
                elif kind == "message_stop":
                    stopped = True
                    break
                # Ping and future metadata events do not modify content.
        if not started or not stopped or len(closed) != len(blocks) or finish not in {"end_turn", "tool_use", "stop_sequence"}:
            raise RuntimeError(f"Incomplete Anthropic response ({finish or 'disconnected'}); no tools were executed.")
        content, calls, ids = [], [], set()
        for index in sorted(blocks):
            block = blocks[index]
            if block["type"] == "text":
                content.append(block.get("text", ""))
                continue
            call_id, name = block.get("id"), block.get("name")
            if not isinstance(call_id, str) or not call_id or call_id in ids or not isinstance(name, str) or not name:
                raise RuntimeError("Invalid Anthropic tool-call identity")
            ids.add(call_id)
            args = json.loads(block["partial_json"]) if block["partial_json"] else block.get("input", {})
            if not isinstance(args, dict):
                raise RuntimeError("Tool arguments must be an object")
            calls.append({"id": call_id, "type": "function", "function": {
                "name": name, "arguments": json.dumps(args, ensure_ascii=False)}})
        if bool(calls) != (finish == "tool_use"):
            raise RuntimeError("Anthropic stop reason does not match tool calls")
        text = "".join(content)
        if not text and not calls:
            raise RuntimeError("Model returned an empty response")
        message = {"role": "assistant", "content": text or None}
        if calls:
            message["tool_calls"] = calls
        usage["prompt_tokens"] = usage.get("input_tokens", 0)
        usage["completion_tokens"] = usage.get("output_tokens", 0)
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        return message, usage
