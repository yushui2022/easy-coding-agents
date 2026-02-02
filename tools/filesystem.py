import os
import aiofiles
from tools.base import registry

@registry.register(
    name="read",
    description="Read file content with line numbers. Use offset/limit for large files.",
    parameters={
        "properties": {
            "path": {"type": "string", "description": "Absolute path to file"},
            "offset": {"type": "integer", "description": "Start line number (0-indexed)"},
            "limit": {"type": "integer", "description": "Max lines to read"}
        },
        "required": ["path"]
    }
)
async def read_file(path: str, offset: int = 0, limit: int = 200) -> str:
    if not os.path.exists(path):
        return f"Error: File {path} not found."
    
    try:
        async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
            lines = await f.readlines()
            
        total_lines = len(lines)
        if offset >= total_lines:
            return f"Error: Offset {offset} is out of bounds (file has {total_lines} lines)."
            
        selected = lines[offset : offset + limit]
        content = "".join(f"{offset + i + 1:4}| {line}" for i, line in enumerate(selected))
        
        footer = ""
        if offset + limit < total_lines:
            footer = f"\n... ({total_lines - (offset + limit)} more lines) ..."
            
        return content + footer
    except Exception as e:
        return f"Error reading file: {str(e)}"

@registry.register(
    name="write",
    description="Write content to a file (overwrites existing).",
    parameters={
        "properties": {
            "path": {"type": "string", "description": "Absolute path to file"},
            "content": {"type": "string", "description": "Content to write"}
        },
        "required": ["path", "content"]
    }
)
async def write_file(path: str, content: str) -> str:
    try:
        async with aiofiles.open(path, mode='w', encoding='utf-8') as f:
            await f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

@registry.register(
    name="edit",
    description="Replace a unique string in a file with a new string.",
    parameters={
        "properties": {
            "path": {"type": "string", "description": "Absolute path to file"},
            "old_str": {"type": "string", "description": "Exact string to replace"},
            "new_str": {"type": "string", "description": "New string to insert"}
        },
        "required": ["path", "old_str", "new_str"]
    }
)
async def edit_file(path: str, old_str: str, new_str: str) -> str:
    if not os.path.exists(path):
        return f"Error: File {path} not found."
        
    try:
        async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
            content = await f.read()
            
        if old_str not in content:
            return "Error: old_str not found in file."
            
        count = content.count(old_str)
        if count > 1:
            return f"Error: old_str occurs {count} times. Please provide a more unique context."
            
        new_content = content.replace(old_str, new_str)
        
        async with aiofiles.open(path, mode='w', encoding='utf-8') as f:
            await f.write(new_content)
            
        return "Successfully edited file."
    except Exception as e:
        return f"Error editing file: {str(e)}"
