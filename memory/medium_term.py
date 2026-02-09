import asyncio
import json
from typing import List, Dict, Any, Optional
from utils.logger import logger
from core.stream import StreamHandler

class MediumTermMemory:
    """
    第二层：中期记忆 (The Compressor - AU2)
    负责对话的“脱水快照”和 AU2 压缩。
    """
    def __init__(self, stream_handler: StreamHandler):
        self.stream_handler = stream_handler
        self.is_compressing = False

    async def compress(self, full_context: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Execute AU2 Compression Algorithm.
        Returns (New Context List, AU2 Structured Summary Dict)
        """
        # Feature Flag: If AU2 is disabled via config (implied), or we just want to skip it for stability
        # For now, we still allow it, but we add a guard.
        
        if self.is_compressing or len(full_context) < 10:
            return full_context, None

        self.is_compressing = True
        logger.info("Starting AU2 Context Compression...")
        
        au2_data = None

        try:
            # 1. Slice Strategy: Keep System + First 2 (Intro) + Last 4 (Recent)
            # Everything in between is "The Middle" to be compressed.
            system_msgs = [m for m in full_context if m['role'] == 'system']
            dialogue = [m for m in full_context if m['role'] != 'system']
            
            if len(dialogue) < 10:
                return full_context

            intro = dialogue[:2]
            recent = dialogue[-4:]
            middle = dialogue[2:-4]
            
            middle_text = json.dumps(middle, ensure_ascii=False, indent=1)

            # 2. AU2 Prompt Generation (Markdown Optimized)
            prompt = f"""
            You are a Memory Compressor (AU2 Algorithm).
            Compress the following conversation history into a concise Markdown summary.
            
            Input JSON:
            {middle_text}
            
            Output Format (Strict Markdown):
            ## Background
            (Context of the task)
            
            ## Key Decisions
            (Key technical decisions made)
            
            ## Progress
            (What has been achieved so far)
            
            ## Current State
            (Pending tasks and next steps)
            """
            
            # 3. Call LLM for compression
            compress_msgs = [{"role": "user", "content": prompt}]
            
            response_gen = self.stream_handler.chat(compress_msgs, tools=None)
            compressed_str, _ = await self.stream_handler.render_stream(response_gen)
            
            # 4. Use raw markdown directly
            au2_data = compressed_str # For session store
            summary_text = compressed_str

            # 5. Reflow
            # New Context = System + Intro + [Summary] + Recent
            # Note: We use "user" role for summary to avoid breaking message alternation rules.
            summary_message = {
                "role": "user",
                "content": f"System Notification: Previous conversation history has been compressed due to length limits.\n\n=== MEMORY SUMMARY ===\n{summary_text}\n======================\n\nPlease continue the task based on this summary and the recent messages below."
            }
            
            new_context = system_msgs + intro + [summary_message] + recent
            
            logger.info("AU2 Compression Completed.")
            return new_context, au2_data

        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return full_context, None
        finally:
            self.is_compressing = False
