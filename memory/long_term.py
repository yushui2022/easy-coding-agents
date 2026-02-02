import os
import aiofiles
import asyncio
from utils.logger import logger

class LongTermMemory:
    """
    第三层：长期记忆 (The Archivist)
    管理跨越程序生命周期的“经验书” (CLAUDE.md)。
    """
    def __init__(self, file_path="CLAUDE.md"):
        self.file_path = file_path
        self._lock = asyncio.Lock() # Atomic write lock

    async def load(self) -> str:
        """Load long-term memory at startup."""
        if not os.path.exists(self.file_path):
            return ""
        
        try:
            async with aiofiles.open(self.file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
            logger.info(f"Loaded Long-Term Memory from {self.file_path}")
            return content
        except Exception as e:
            logger.error(f"Failed to load long-term memory: {e}")
            return ""

    async def update(self, key_decisions: str, preferences: str = None):
        """
        Append new insights to the memory file.
        Atomic operation to prevent corruption.
        """
        async with self._lock:
            try:
                # Read existing to check for duplicates or structure
                # For simplicity, we just append with a timestamp/header
                entry = f"\n\n## Update\n"
                if preferences:
                    entry += f"### User Preferences\n{preferences}\n"
                if key_decisions:
                    entry += f"### Key Decisions / Legacy Issues\n{key_decisions}\n"
                
                async with aiofiles.open(self.file_path, mode='a', encoding='utf-8') as f:
                    await f.write(entry)
                
                logger.info("Long-Term Memory updated.")
            except Exception as e:
                logger.error(f"Failed to write long-term memory: {e}")
