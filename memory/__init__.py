import asyncio
from typing import Any, Dict, List, Optional

from agent_memory_core import CodingMemory, QualityGateResult
from core.stream import StreamHandler
from memory.short_term import MemoryOverflowError, ShortTermMemory
from utils.logger import logger


class MemoryManager:
    """
    Backward-compatible facade over agent_memory_core.CodingMemory.

    The old 3-tier memory API is preserved for core.engine, while the real
    memory system now stores evidence in SQLite + refs and builds a structured
    prompt with task state, task map, sourced memories, and retrieval results.
    """

    def __init__(self, stream_handler: StreamHandler):
        self.stream_handler = stream_handler
        self.short_term = ShortTermMemory()
        self.core = CodingMemory(project_root=".", workspace=".agent_memory")
        self._pending_tasks: set[asyncio.Task] = set()
        self._last_user_request: Optional[str] = None
        self._system_prompt = ""

    async def initialize(self) -> str:
        logger.info("Evidence-Gated Coding Memory initialized.")
        return ""

    def set_system_prompt(self, content: str):
        self._system_prompt = content or ""
        self.short_term.set_system_prompt(content or "")

    def get_system_prompt(self) -> str:
        return self._system_prompt

    def get_usage_percent(self) -> int:
        current, limit = self.short_term.get_usage()
        if limit <= 0:
            return 0
        return min(100, int((current / limit) * 100))

    def add(
        self,
        role: str,
        content: Any,
        tool_calls: List = None,
        tool_call_id: str = None,
        name: str = None,
        tool_args: Optional[Dict[str, Any]] = None,
    ):
        try:
            self.short_term.add(role, content, tool_calls, tool_call_id, name)
        except MemoryOverflowError:
            self.short_term.truncate_to_fit(target_ratio=0.55)

        if role == "user":
            self._last_user_request = str(content)
            self._schedule(self.core.record_user_message(str(content)))
        elif role == "assistant":
            self._schedule(self.core.record_assistant_message(str(content or ""), tool_calls=tool_calls))
        elif role == "tool":
            self._schedule(
                self.core.record_tool_result(
                    name=name or "tool",
                    args=tool_args or {},
                    result=content,
                    tool_call_id=tool_call_id,
                )
            )

    async def auto_save(self):
        await self._flush_pending()
        await self.core.save_session()

    async def get_context(self) -> List[Dict[str, Any]]:
        await self._flush_pending()
        evidence_context = await self.core.build_prompt_context(self._last_user_request)
        if evidence_context and evidence_context[0]["role"] == "system":
            if self._system_prompt:
                evidence_context[0]["content"] = f"{self._system_prompt}\n\n{evidence_context[0]['content']}"
        elif self._system_prompt:
            evidence_context.insert(0, {"role": "system", "content": self._system_prompt})
        return evidence_context

    async def check_quality_gate(self, proposal: Dict[str, Any]) -> QualityGateResult:
        await self._flush_pending()
        return await self.core.check_quality_gate(proposal)

    async def propose_state_transition(self, proposal: Dict[str, Any]) -> QualityGateResult:
        await self._flush_pending()
        return await self.core.propose_state_transition(proposal)

    async def validate_final_answer(self, content: str, task_profile: str = "coding_task") -> QualityGateResult:
        await self._flush_pending()
        return self.core.validate_final_answer(content, task_profile=task_profile)

    async def save_insight(self, content: str):
        await self._flush_pending()
        await self.core.add_memory(content=content, memory_type="Decision", source_refs=[])

    def _schedule(self, coro):
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(coro)
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)
        except RuntimeError:
            asyncio.run(coro)

    async def _flush_pending(self):
        if not self._pending_tasks:
            return
        pending = list(self._pending_tasks)
        self._pending_tasks.clear()
        results = await asyncio.gather(*pending, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Memory background task failed: {result}")
