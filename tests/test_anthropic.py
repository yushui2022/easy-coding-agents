import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from eca.anthropic import AnthropicProvider, messages_payload
from eca.config import Settings
from eca.provider import Provider


def response_events(tool=False):
    block = {"type": "tool_use", "id": "t1", "name": "read", "input": {}} if tool else {"type": "text", "text": ""}
    delta = {"type": "input_json_delta", "partial_json": '{"path":'} if tool else {"type": "text_delta", "text": "Hello"}
    events = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 12, "output_tokens": 1}}},
        {"type": "ping"},
        {"type": "content_block_start", "index": 0, "content_block": block},
        {"type": "content_block_delta", "index": 0, "delta": delta},
    ]
    if tool:
        events.append({"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '"a.py"}'}})
    return events + [
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use" if tool else "end_turn"}, "usage": {"output_tokens": 7}},
        {"type": "message_stop"},
    ]


class AnthropicTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, events, status=200):
        requests, emitted = [], []
        async def handler(request):
            requests.append(request)
            # Includes SSE comments and multi-line JSON frames.
            stream = ": keepalive\n\n" + "".join(
                "event: " + e["type"] + "\n" + "\n".join("data: " + line for line in json.dumps(e, indent=2).splitlines()) + "\n\n"
                for e in events)
            return httpx.Response(status, text=stream, headers={"content-type": "text/event-stream"})
        settings = Settings(Path.cwd(), api_format="anthropic", model="fixture", api_key="test-key",
                            base_url="https://api.anthropic.com")
        provider = Provider(settings)
        native = provider.native = AnthropicProvider(settings)
        native.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await provider.complete([{"role": "user", "content": "Hello"}], [], lambda *e: emitted.append(e))
            return result, requests, emitted
        finally:
            await provider.close()
            self.assertTrue(native.client.is_closed)

    async def test_text_usage_headers_and_endpoint(self):
        (message, usage), requests, emitted = await self.invoke(response_events())
        self.assertEqual(message["content"], "Hello")
        self.assertEqual(usage["total_tokens"], 19)
        self.assertEqual(usage["output_tokens"], 7)  # Cumulative, not added to initial 1.
        self.assertEqual(str(requests[0].url), "https://api.anthropic.com/v1/messages")
        self.assertEqual(requests[0].headers["x-api-key"], "test-key")
        self.assertEqual(requests[0].headers["anthropic-version"], "2023-06-01")
        self.assertEqual([e for e in emitted if e[0]=='text'], [("text", "Hello")])
        self.assertEqual(emitted[-1][0], 'request_end')
        self.assertEqual(emitted[-1][1]['usage']['output_tokens'], 7)

    async def test_fragmented_tool_arguments(self):
        (message, _), _, emitted = await self.invoke(response_events(True))
        self.assertEqual(json.loads(message["tool_calls"][0]["function"]["arguments"]), {"path": "a.py"})
        self.assertIn('tool_arguments', [d['phase'] for e,d in emitted if e == 'model_activity'])
        self.assertEqual(emitted[-1][1]['tool_argument_chars'], len('{"path":"a.py"}'))
        self.assertEqual(emitted[-1][1]['output_tokens'], 7)
        self.assertNotIn('model_delta', [e for e,_ in emitted])

    async def test_truncated_stream_never_returns_tool(self):
        for length in range(len(response_events(True))):
            with self.subTest(length=length), self.assertRaises(RuntimeError):
                await self.invoke(response_events(True)[:length])

    async def test_rejects_output_limit_and_inconsistent_stop(self):
        for reason in ("max_tokens", "end_turn", "refusal", "pause_turn"):
            events = response_events(True)
            events[-2]["delta"]["stop_reason"] = reason
            with self.subTest(reason=reason), self.assertRaises(RuntimeError):
                await self.invoke(events)

    async def test_error_event_rejected(self):
        events = response_events(True)
        events.insert(-1, {"type": "error", "error": {"type": "overloaded_error", "message": "test-key"}})
        with self.assertRaisesRegex(RuntimeError, "stream reported an error") as cm:
            await self.invoke(events)
        self.assertNotIn("test-key", str(cm.exception))

    async def test_http_error_does_not_echo_body(self):
        with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
            await self.invoke(response_events(), 401)

    async def test_bad_json_and_non_object_arguments(self):
        for value in ('{"broken":', '[]'):
            events = response_events(True)
            events[3]["delta"]["partial_json"] = value
            events[4]["delta"]["partial_json"] = ""
            with self.subTest(value=value), self.assertRaises((ValueError, RuntimeError)):
                await self.invoke(events)

    async def test_unclosed_block_and_unsupported_thinking_rejected(self):
        events = [e for e in response_events(True) if e["type"] != "content_block_stop"]
        with self.assertRaises(RuntimeError):
            await self.invoke(events)
        events = response_events()
        events[2]["content_block"] = {"type": "thinking", "thinking": ""}
        with self.assertRaisesRegex(RuntimeError, "Unsupported"):
            await self.invoke(events)

    async def test_duplicate_tool_identity_rejected(self):
        events = response_events(True)
        duplicate = json.loads(json.dumps(events[2:6]))
        for event in duplicate:
            event["index"] = 1
        events[6:6] = duplicate
        with self.assertRaisesRegex(RuntimeError, "identity"):
            await self.invoke(events)

    async def test_cancellation_closes_stream(self):
        ready = asyncio.Event()
        class Stream(httpx.AsyncByteStream):
            closed = False
            async def __aiter__(self):
                yield b'data: {"type":"message_start","message":{}}\n\n'
                ready.set()
                await asyncio.Event().wait()
            async def aclose(self):
                self.closed = True
        stream = Stream()
        async def handler(request):
            return httpx.Response(200, stream=stream)
        provider = AnthropicProvider(Settings(Path.cwd(), api_key="test", base_url="https://fixture.invalid/v1"))
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            task = asyncio.create_task(provider.complete([], [], lambda *_: None))
            await asyncio.wait_for(ready.wait(), timeout=5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(stream.closed)
        finally:
            await provider.close()

    def test_tool_results_grouped_for_resume(self):
        call = lambda i: {"id": i, "function": {"name": "read", "arguments": '{"path":"a"}'}}
        messages = [{"role": "system", "content": "instructions"}, {"role": "user", "content": "read"},
                    {"role": "assistant", "content": None, "tool_calls": [call("a"), call("b")]},
                    {"role": "tool", "tool_call_id": "a", "content": "result a"},
                    {"role": "tool", "tool_call_id": "b", "content": "result b"}]
        schema = [{"function": {"name": "read", "parameters": {"type": "object"}}}]
        payload = messages_payload(messages, schema, Settings(Path.cwd(), max_output_tokens=4096))
        self.assertEqual(payload["system"], "instructions")
        self.assertEqual(len(payload["messages"]), 3)
        self.assertEqual([b["tool_use_id"] for b in payload["messages"][-1]["content"]], ["a", "b"])
        self.assertEqual(payload["tools"][0]["input_schema"], {"type": "object"})
        self.assertEqual(payload["max_tokens"], 4096)

    def test_config_protocol_isolates_credentials_and_requires_model(self):
        base = Path(os.environ.get("ECA_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp, patch.dict(os.environ, {
                "ANTHROPIC_API_KEY": "native-key", "OPENAI_API_KEY": "other-key", "OPENAI_BASE_URL": "https://other.invalid",
                "ECA_API_FORMAT": "anthropic"}, clear=True):
            with self.assertRaisesRegex(ValueError, "model"):
                Settings.load(Path(tmp))
            settings = Settings.load(Path(tmp), model="fixture")
            self.assertEqual(settings.api_key, "native-key")
            self.assertEqual(settings.base_url, "https://api.anthropic.com/v1")
            settings = Settings.load(Path(tmp), api_format="openai")
            self.assertEqual(settings.api_key, "other-key")
            self.assertEqual(settings.base_url, "https://other.invalid")
            with self.assertRaisesRegex(ValueError, "api_format"):
                Settings.load(Path(tmp), api_format="invalid")
            with self.assertRaisesRegex(ValueError, "max_output_tokens"):
                Settings.load(Path(tmp), model="fixture", max_output_tokens=0)
