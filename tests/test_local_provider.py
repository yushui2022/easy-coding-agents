"""Local OpenAI-compatible servers (Ollama, vLLM, LM Studio) differ from OpenAI in
small, documented ways. These tests pin the differences the stream parser has to
absorb so a local model can drive tools inside ECA.
"""
import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from eca.config import Settings
from eca.provider import Provider


def chunk(delta, finish=None, usage=None, choices=True):
    return NS(usage=usage, choices=[NS(finish_reason=finish, delta=delta)] if choices else [])


def delta(content=None, reasoning=None, reasoning_content=None, tool_calls=None):
    return NS(content=content, reasoning=reasoning, reasoning_content=reasoning_content, tool_calls=tool_calls)


def call(name, arguments, ident=None, index=0):
    return NS(id=ident, index=index, function=NS(name=name, arguments=arguments))


def provider_with(chunks):
    class Stream:
        async def __aiter__(self):
            for item in chunks:
                yield item

        async def close(self):
            pass

    provider = Provider(Settings(Path.cwd(), api_key='fixture', network_retries=0, request_timeout=5))
    provider.client = NS(chat=NS(completions=NS(create=AsyncMock(return_value=Stream()))), close=AsyncMock())
    return provider


async def run(chunks):
    provider = provider_with(chunks)
    events = []
    try:
        message, usage = await provider.complete([], [], lambda *event: events.append(event))
    finally:
        await provider.close()
    return message, usage, events


class LocalProviderTests(unittest.TestCase):
    def test_ollama_style_reasoning_and_tool_call(self):
        usage = NS(model_dump=lambda: {'prompt_tokens': 12, 'completion_tokens': 7, 'total_tokens': 19})
        chunks = [
            chunk(delta(content='', reasoning='用户要求读取')),
            chunk(delta(content='', reasoning='文件')),
            chunk(delta(content='', tool_calls=[call('read', '{"path":"hello.txt"}', 'call_abc')]), ),
            chunk(delta(content=''), finish='tool_calls'),
            chunk(None, choices=False, usage=usage),
        ]
        message, got_usage, events = asyncio.run(run(chunks))
        self.assertEqual(got_usage['completion_tokens'], 7)
        self.assertEqual(len(message['tool_calls']), 1)
        self.assertEqual(message['tool_calls'][0]['id'], 'call_abc')
        self.assertEqual(json.loads(message['tool_calls'][0]['function']['arguments']), {'path': 'hello.txt'})
        # Ollama's `reasoning` deltas have to count as progress, or a long think
        # looks like a stalled stream and gets killed by the idle timeout.
        self.assertIn('用户要求读取', str(events))

    def test_vllm_style_object_arguments_without_id_or_index(self):
        chunks = [
            chunk(delta(content='', tool_calls=[call('read', {'path': 'a.py'}, None, None)])),
            chunk(delta(content='')),
        ]
        message, _, _ = asyncio.run(run(chunks))
        tool_call = message['tool_calls'][0]
        self.assertEqual(json.loads(tool_call['function']['arguments']), {'path': 'a.py'})
        self.assertTrue(tool_call['id'])
        self.assertEqual(tool_call['function']['name'], 'read')

    def test_tool_without_arguments_becomes_an_empty_object(self):
        chunks = [
            chunk(delta(content='', tool_calls=[call('list_files', '', 'call_empty')])),
            chunk(delta(content=''), finish='tool_calls'),
        ]
        message, _, _ = asyncio.run(run(chunks))
        self.assertEqual(message['tool_calls'][0]['function']['arguments'], '{}')

    def test_duplicate_call_ids_are_still_rejected(self):
        chunks = [
            chunk(delta(content='', tool_calls=[call('read', '{"path":"a"}', 'same', 0),
                                                call('read', '{"path":"b"}', 'same', 1)])),
            chunk(delta(content=''), finish='tool_calls'),
        ]
        with self.assertRaises(RuntimeError):
            asyncio.run(run(chunks))


if __name__ == '__main__':
    unittest.main()
