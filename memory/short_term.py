from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from core.config import Config
from utils.logger import logger

@dataclass
class MemoryOverflowError(Exception):
    """Signal that short-term memory has exceeded capacity."""
    current_tokens: int
    limit: int

class ShortTermMemory:
    """
    第一层：短期记忆 (The Buffer)
    管理内存中的“活数据”，直接参与每一轮对话。
    """
    def __init__(self):
        self.active_context: List[Dict[str, Any]] = []
        self.system_prompt: Optional[Dict[str, Any]] = None
        # Simple heuristic estimation: 1 char ~= 0.3-0.5 tokens. 
        # Using a conservative 0.5 char/token ratio for estimation or just counting chars for now.
        # Ideally, we should use a tokenizer, but for a lightweight agent, len(str) / 3 is a common approximation.
        self.token_limit = Config.MAX_HISTORY_TOKENS
        
    def set_system_prompt(self, content: str):
        self.system_prompt = {"role": "system", "content": content}

    def add(self, role: str, content: Any, tool_calls: List = None, tool_call_id: str = None, name: str = None):
        msg = {"role": role, "content": content}
        if tool_calls: msg["tool_calls"] = tool_calls
        if tool_call_id: msg["tool_call_id"] = tool_call_id
        if name: msg["name"] = name
        
        self.active_context.append(msg)
        self._check_overflow()

    def get_context(self) -> List[Dict[str, Any]]:
        """Return System Prompt + Active Context."""
        context = []
        if self.system_prompt:
            context.append(self.system_prompt)
        context.extend(self.active_context)
        return context

    def _estimate_tokens(self) -> int:
        """Estimate current token usage."""
        text = "".join(str(m.get("content", "")) for m in self.active_context)
        # Adding system prompt length
        if self.system_prompt:
            text += str(self.system_prompt.get("content", ""))
        return int(len(text) / 3) # Rough approximation

    def _check_overflow(self):
        """Monitor token usage and raise signal if > 92%."""
        current = self._estimate_tokens()
        threshold = self.token_limit * 0.92
        
        if current > threshold:
            logger.warning(f"Memory Overflow Detected: {current}/{self.token_limit} tokens")
            raise MemoryOverflowError(current, self.token_limit)

    def replace_context(self, new_context: List[Dict[str, Any]]):
        """Used by Compressor to replace old context with compressed version."""
        self.active_context = new_context
