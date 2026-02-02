import json
import os
import glob
from typing import Dict, Any, List, Optional
from datetime import datetime
import aiofiles
from utils.logger import logger

class SessionStore:
    """
    Handles JSON serialization for Short-Term and Medium-Term memories.
    Path: memory/sessions/session_{timestamp}.json
    """
    def __init__(self, session_dir="memory/sessions"):
        self.session_dir = session_dir
        self.current_session_file = None
        self._ensure_dir()

    def _ensure_dir(self):
        if not os.path.exists(self.session_dir):
            os.makedirs(self.session_dir)

    def create_new_session(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_session_file = os.path.join(self.session_dir, f"session_{timestamp}.json")
        logger.info(f"New session created: {self.current_session_file}")

    def get_latest_session(self) -> Optional[str]:
        """Find the most recent session file."""
        files = glob.glob(os.path.join(self.session_dir, "session_*.json"))
        if not files:
            return None
        return max(files, key=os.path.getctime)

    async def save(self, messages: List[Dict], au2_summary: Optional[Dict] = None):
        """
        Auto-Save: Persist current state to JSON.
        Format:
        {
            "timestamp": "...",
            "au2_summary": {...},
            "messages": [...]
        }
        """
        if not self.current_session_file:
            self.create_new_session()

        data = {
            "timestamp": datetime.now().isoformat(),
            "au2_summary": au2_summary,
            "messages": messages
        }

        try:
            async with aiofiles.open(self.current_session_file, mode='w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            # logger.debug("Session auto-saved.") # Too verbose for regular log
        except Exception as e:
            logger.error(f"Failed to auto-save session: {e}")

    async def load(self, file_path: str) -> Dict[str, Any]:
        """Load session data from file."""
        try:
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error(f"Failed to load session {file_path}: {e}")
            return {}
