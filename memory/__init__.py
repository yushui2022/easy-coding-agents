from typing import List, Dict, Any, Optional
from utils.logger import logger, console
from core.stream import StreamHandler

# Sub-modules
from memory.short_term import ShortTermMemory, MemoryOverflowError
from memory.medium_term import MediumTermMemory
from memory.long_term import LongTermMemory
from memory.session_store import SessionStore

class MemoryManager:
    """
    Facade for the 3-Tier Memory Architecture.
    Coordinating Short, Medium, and Long term memories.
    """
    def __init__(self, stream_handler: StreamHandler):
        self.short_term = ShortTermMemory()
        self.medium_term = MediumTermMemory(stream_handler)
        self.long_term = LongTermMemory()
        self.session_store = SessionStore()
        self.current_au2_summary = None # Cache for auto-save

    async def initialize(self):
        """Lifecycle: Start -> Load Long Term Memory -> Check for Resume."""
        # 1. Load Long Term Memory (Experience)
        long_term_content = await self.long_term.load()
        
        # 2. Check for Session Resume
        latest_session = self.session_store.get_latest_session()
        if latest_session:
            # Simple interaction to ask user if they want to resume
            # Since this runs in async context before main loop, we can print.
            # Real interactive confirmation would require input() or similar, 
            # but here we'll just log availability or auto-load if very recent (todo).
            # For this implementation, we will auto-load for seamless experience if the file exists.
            logger.info(f"Found previous session: {latest_session}")
            # In a real CLI, we might prompt user here. For now, let's load it.
            data = await self.session_store.load(latest_session)
            if data:
                self.short_term.active_context = data.get("messages", [])
                self.current_au2_summary = data.get("au2_summary")
                logger.info("Session resumed successfully.")

        return long_term_content

    def set_system_prompt(self, content: str):
        self.short_term.set_system_prompt(content)

    def add(self, role: str, content: Any, tool_calls: List = None, tool_call_id: str = None, name: str = None):
        """
        Main Entry: Add to Short Term -> Check Overflow -> Trigger Compression.
        """
        try:
            self.short_term.add(role, content, tool_calls, tool_call_id, name)
        except MemoryOverflowError:
            # Trigger compression flow asynchronously
            pass

    async def auto_save(self):
        """Called by Engine at key checkpoints to persist session."""
        await self.session_store.save(self.short_term.active_context, self.current_au2_summary)

    async def get_context(self) -> List[Dict[str, Any]]:
        """
        Get context for LLM.
        Checks for overflow and runs compression if needed BEFORE returning context.
        """
        try:
            # Check overflow logic is usually triggered on write, 
            # but we can also double check here or use the flag from write.
            self.short_term._check_overflow() # Will raise if full
        except MemoryOverflowError:
            logger.warning("Memory overflow confirmed. Executing AU2 compression...")
            full_context = self.short_term.get_context()
            
            # Execute AU2
            new_context, au2_data = await self.medium_term.compress(full_context)
            
            # Update Short Term with Compressed version
            self.short_term.replace_context(new_context)
            
            # Update Medium Term Cache
            if au2_data:
                self.current_au2_summary = au2_data
                
            # Trigger Auto-Save immediately after compression
            await self.auto_save()
            
            # Value Extraction: Check for Long-Term Insights
            if au2_data:
                await self._extract_value_to_long_term(au2_data)
            
        return self.short_term.get_context()

    async def _extract_value_to_long_term(self, au2_data: Dict[str, Any]):
        """
        Heuristic check: If AU2 summary contains explicit decisions or preferences,
        we might want to save them to CLAUDE.md.
        Real implementation would use an LLM call to filter 'Global vs Local' info.
        For MVP, we just append 'Decisions' if they look significant.
        """
        decisions = au2_data.get("decisions")
        if decisions and len(str(decisions)) > 10:
             # We invoke the Archivist
             # In a real agent, we'd ask: "Is this decision project-specific or global?"
             # Here we just save it as a "Mid-Term Archive"
             await self.long_term.update(key_decisions=f"[From Session] {decisions}")

    async def save_insight(self, content: str):
        """Manual trigger to save something to long term memory."""
        await self.long_term.update(key_decisions=content)
