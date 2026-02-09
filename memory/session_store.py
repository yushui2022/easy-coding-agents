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
        self.current_session_file = os.path.join(self.session_dir, f"session_{timestamp}.md")
        logger.info(f"New session created: {self.current_session_file}")

    def get_latest_session(self) -> Optional[str]:
        """Find the most recent session file."""
        files = glob.glob(os.path.join(self.session_dir, "session_*.md"))
        if not files:
            return None
        return max(files, key=os.path.getctime)

    async def save(self, messages: List[Dict], au2_summary: Optional[Dict] = None):
        """
        Auto-Save: Persist current state to Markdown.
        Format:
        ---
        timestamp: "..."
        au2_summary: "..." (Markdown string)
        ---
        
        ## User
        Content...
        
        ## Assistant
        Content...
        """
        if not self.current_session_file:
            self.create_new_session()

        timestamp = datetime.now().isoformat()
        
        # Prepare content
        md_lines = ["---", f"timestamp: {timestamp}"]
        
        if au2_summary:
            # We assume au2_summary is now a Markdown string or dict we convert
            if isinstance(au2_summary, str):
                summary_str = au2_summary.replace("\n", "\\n") # Simple escape for YAML header
                md_lines.append(f"au2_summary: {summary_str}")
            else:
                md_lines.append(f"au2_summary: {json.dumps(au2_summary)}")
        
        md_lines.append("---\n")
        
        # Optimization: Only save the last N messages in detail if the session is huge
        # This prevents the markdown file from growing indefinitely.
        # However, for resuming, we might want the full history?
        # The user specifically asked "do we need to record ALL dialogues?".
        # Let's archive older messages into a summary block or just truncate them in the file.
        # Since we have AU2 summary, we can rely on that for "past" and only save "recent".
        
        # Strategy: Keep only the last 20 messages (approx 10 turns).
        # AU2 Summary handles the long-term context.
        # This ensures the .md file remains a lightweight "Working Memory Snapshot"
        # rather than a massive execution log.
        
        msgs_to_save = messages
        if len(messages) > 20:
             # Keep System Prompt (usually index 0) + Last 20
             # Note: messages list usually starts with user/assistant exchanges.
             # System prompt is handled separately in ShortTermMemory but passed here?
             # Let's just safely slice the last 20.
             
             msgs_to_save = messages[-20:]
             md_lines.append(f"<!-- Archived {len(messages)-20} older messages. See AU2 Summary for context. -->\n")

        for msg in msgs_to_save:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
            
            # --- Smart Filtering (User Request) ---
            # 只同步主要信息：User 的话，Assistant 的话。
            # 过滤掉 Tool 的执行结果和 Tool Calls 的详细 JSON。
            
            # 1. 忽略 Tool 的执行结果
            if role.lower() == "tool":
                continue
                
            # 2. 对于 Assistant 消息，只保留 content
            # 如果 content 为空且只有 tool_calls，则跳过该消息（因为它没有实质性对话内容）
            if role.lower() == "assistant":
                if not content and "tool_calls" in msg:
                    continue
            
            md_lines.append(f"## {role}")
            
            if content:
                md_lines.append(str(content))
            
            # 3. 不再保存 Tool Calls 详情
            # if "tool_calls" in msg and msg["tool_calls"]:
            #     md_lines.append("\n```json:tool_calls")
            #     md_lines.append(json.dumps(msg["tool_calls"], indent=2, ensure_ascii=False))
            #     md_lines.append("```")
                
            # Serialize tool results (已在上面被过滤，这里注释掉以防万一)
            # if role == "Tool":
            #    if "name" in msg:
            #        md_lines.append(f"\n**Tool Name**: {msg['name']}")
                
            md_lines.append("\n")

        try:
            async with aiofiles.open(self.current_session_file, mode='w', encoding='utf-8') as f:
                await f.write("\n".join(md_lines))
        except Exception as e:
            logger.error(f"Failed to auto-save session: {e}")

    async def load(self, file_path: str) -> Dict[str, Any]:
        """Load session data from Markdown file."""
        try:
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
            
            # Simple parser for the specific MD format we write
            messages = []
            current_msg = None
            au2_summary = None
            
            # Split header
            parts = content.split("---", 2)
            if len(parts) >= 3:
                header = parts[1]
                body = parts[2]
                
                # Parse header
                for line in header.splitlines():
                    if line.startswith("au2_summary:"):
                        val = line.split(":", 1)[1].strip()
                        try:
                            au2_summary = json.loads(val)
                        except:
                            au2_summary = val.replace("\\n", "\n")
            else:
                body = content

            # Parse body
            lines = body.splitlines()
            buffer = []
            role = None
            tool_calls = None
            
            # Very basic state machine parser
            i = 0
            while i < len(lines):
                line = lines[i]
                if line.startswith("## "):
                    # New message start, save previous
                    if role:
                        msg = {"role": role.lower(), "content": "\n".join(buffer).strip()}
                        if tool_calls:
                            msg["tool_calls"] = tool_calls
                        messages.append(msg)
                    
                    # Start new
                    role = line[3:].strip()
                    buffer = []
                    tool_calls = None
                    i += 1
                    continue
                
                if line.strip().startswith("```json:tool_calls"):
                    # Parse tool calls block
                    json_lines = []
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith("```"):
                        json_lines.append(lines[i])
                        i += 1
                    try:
                        tool_calls = json.loads("\n".join(json_lines))
                    except:
                        pass
                    i += 1
                    continue
                    
                buffer.append(line)
                i += 1
            
            # Save last
            if role:
                msg = {"role": role.lower(), "content": "\n".join(buffer).strip()}
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                messages.append(msg)
                
            # Optimization: When loading for resume, do NOT load the entire history if it's huge.
            # We only need the recent context + AU2 summary.
            # If we load too much, we risk confusing the LLM or hitting token limits immediately.
            if len(messages) > 50:
                logger.info(f"Session Load: Truncating {len(messages)} messages to last 50 for stability.")
                messages = messages[-50:]
                
            return {
                "messages": messages,
                "au2_summary": au2_summary
            }
            
        except Exception as e:
            logger.error(f"Failed to load session {file_path}: {e}")
            return {}
