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

            # 2. AU2 Prompt Generation
            prompt = f"""
            You are a Memory Compressor (AU2 Algorithm).
            Compress the following conversation history into a structured 8-dimensional summary.
            
            Input JSON:
            {middle_text}
            
            Output Format (Strict JSON):
            {{
                "background": "Context of the task",
                "decisions": "Key technical decisions made",
                "tools": "Tools used and their outcomes",
                "intent": "User's core intent evolution",
                "results": "What has been achieved so far",
                "errors": "Errors encountered and fixes",
                "legacy_issues": "Unresolved problems",
                "next_steps": "Planned next actions"
            }}
            """
            
            # 3. Call LLM for compression (using a separate, non-streaming call if possible, 
            # but reusing stream_handler for simplicity)
            # We construct a temporary message list for the compressor
            compress_msgs = [{"role": "user", "content": prompt}]
            
            # We use a separate "inner" loop or just await the stream
            response_gen = self.stream_handler.chat(compress_msgs, tools=None) # No tools for compressor
            compressed_json_str, _ = await self.stream_handler.render_stream(response_gen) # Wait for full output
            
            # 4. Parse and Format
            # If JSON parsing fails, we fallback to raw text
            summary_text = ""
            try:
                # Clean up markdown code blocks if present
                clean_json = compressed_json_str.replace("```json", "").replace("```", "").strip()
                au2_data = json.loads(clean_json)
                
                summary_text = (
                    f"--- AU2 COMPRESSED MEMORY ---\n"
                    f"Background: {au2_data.get('background')}\n"
                    f"Decisions: {au2_data.get('decisions')}\n"
                    f"Intent: {au2_data.get('intent')}\n"
                    f"Results: {au2_data.get('results')}\n"
                    f"Legacy Issues: {au2_data.get('legacy_issues')}\n"
                    f"-----------------------------"
                )
            except json.JSONDecodeError:
                summary_text = f"--- COMPRESSED SUMMARY ---\n{compressed_json_str}"
                # Even if JSON fails, we might want to structure it loosely, 
                # but for session store we need a dict.
                au2_data = {"raw_summary": compressed_json_str}

            # 5. Reflow
            # New Context = System + Intro + [Summary] + Recent
            new_context = system_msgs + intro + [{"role": "system", "content": summary_text}] + recent
            
            logger.info("AU2 Compression Completed.")
            return new_context, au2_data

        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return full_context, None
        finally:
            self.is_compressing = False
