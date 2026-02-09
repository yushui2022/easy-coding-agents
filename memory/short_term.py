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
        self.token_limit = Config.MAX_HISTORY_TOKENS
        
        # Initialize Tokenizer
        try:
            import tiktoken
            # Use cl100k_base which is used by GPT-4 and recent models like Qwen often align with it
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
            self.use_tiktoken = True
            logger.info("Token Management: tiktoken initialized (cl100k_base).")
        except ImportError:
            self.use_tiktoken = False
            logger.warning("Token Management: tiktoken not found. Falling back to char-length estimation.")

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
        """Estimate current token usage using tiktoken or fallback."""
        text_content = ""
        
        # Collect all text content
        if self.system_prompt:
             text_content += str(self.system_prompt.get("content", ""))
             
        for msg in self.active_context:
            text_content += str(msg.get("content", ""))
            if msg.get("tool_calls"):
                text_content += str(msg["tool_calls"])
            if msg.get("name"):
                text_content += str(msg["name"])

        if self.use_tiktoken:
            try:
                # Need to handle potential encoding errors with replacement
                return len(self.tokenizer.encode(text_content, disallowed_special=()))
            except Exception as e:
                logger.warning(f"tiktoken encoding failed: {e}. Fallback to char estimation.")
                return int(len(text_content) / 3)
        else:
            return int(len(text_content) / 3)

    def get_usage(self) -> tuple[int, int]:
        current = self._estimate_tokens()
        return current, self.token_limit

    def _check_overflow(self):
        """Monitor token usage and raise signal if > 92%."""
        current = self._estimate_tokens()
        threshold = self.token_limit * 0.92
        
        if current > threshold:
            logger.warning(f"Memory Overflow Detected: {current}/{self.token_limit} tokens")
            raise MemoryOverflowError(current, self.token_limit)

    def truncate_fifo(self, count: int = 2) -> List[Dict[str, Any]]:
        """
        Simple Sliding Window: Remove the oldest 'count' messages from active_context.
        """
        if len(self.active_context) > count:
            removed = self.active_context[:count]
            self.active_context = self.active_context[count:]
            return removed
        return []

    def truncate_to_fit(self, target_ratio: float = 0.8) -> List[Dict[str, Any]]:
        """
        Aggressive Truncation: Keep removing oldest messages until usage is below target_ratio * limit.
        Returns the list of removed messages.
        """
        removed_total = []
        target_tokens = int(self.token_limit * target_ratio)
        
        # Safety break to avoid infinite loop
        max_loops = 50 
        loops = 0
        
        while self._estimate_tokens() > target_tokens and self.active_context and loops < max_loops:
            # Remove 2 messages (User + Assistant pair usually)
            removed = self.truncate_fifo(count=2)
            if not removed:
                # Try removing 1 if 2 failed (odd number of messages?)
                removed = self.truncate_fifo(count=1)
                
            if removed:
                removed_total.extend(removed)
            else:
                break # Cannot truncate further
            loops += 1
            
        logger.info(f"Aggressive Truncation: Removed {len(removed_total)} messages to fit token limit.")
        return removed_total

    def replace_context(self, new_context: List[Dict[str, Any]]):
        """Used by Compressor to replace old context with compressed version."""
        # Note: new_context usually includes System Prompt, so we need to separate it
        # because active_context shouldn't contain system prompt (it's stored separately)
        
        self.active_context = [m for m in new_context if m.get("role") != "system"]
        
        # If new_context has a system prompt that is different, update it?
        # Usually AU2 doesn't change system prompt, but if it does, we can handle it.
        # For now, we assume System Prompt is invariant.
