import os
import difflib
import aiofiles
from tools.base import registry
from tools.interaction import ask_selection
from utils.logger import console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

def _render_diff(path: str, old_content: str, new_content: str):
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    table = Table(title=f"Diff Preview: {path}", box=box.SIMPLE, show_lines=False)
    table.add_column("原始代码", overflow="fold")
    table.add_column("修改后代码", overflow="fold")
    old_no = 1
    new_no = 1
    changed_blocks = 0
    added = 0
    removed = 0
    rows = 0
    max_rows = 200
    context = 2

    def add_row(left_text: Text, right_text: Text):
        nonlocal rows
        if rows >= max_rows:
            return False
        table.add_row(left_text, right_text)
        rows += 1
        return True

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            segment_len = i2 - i1
            if segment_len > context * 2 + 1:
                for idx in range(i1, i1 + context):
                    left = Text(f"{old_no:4}| {old_lines[idx]}")
                    right = Text(f"{new_no:4}| {new_lines[j1 + (idx - i1)]}")
                    if not add_row(left, right):
                        break
                    old_no += 1
                    new_no += 1
                if rows < max_rows:
                    add_row(Text("   | ..."), Text("   | ..."))
                old_no += segment_len - context * 2
                new_no += segment_len - context * 2
                for idx in range(i2 - context, i2):
                    if rows >= max_rows:
                        break
                    left = Text(f"{old_no:4}| {old_lines[idx]}")
                    right = Text(f"{new_no:4}| {new_lines[j2 - context + (idx - (i2 - context))]}")
                    add_row(left, right)
                    old_no += 1
                    new_no += 1
            else:
                for idx in range(i1, i2):
                    left = Text(f"{old_no:4}| {old_lines[idx]}")
                    right = Text(f"{new_no:4}| {new_lines[j1 + (idx - i1)]}")
                    if not add_row(left, right):
                        break
                    old_no += 1
                    new_no += 1
        else:
            changed_blocks += 1
            old_seg = old_lines[i1:i2]
            new_seg = new_lines[j1:j2]
            if tag in ["replace", "delete"]:
                removed += len(old_seg)
            if tag in ["replace", "insert"]:
                added += len(new_seg)
            max_len = max(len(old_seg), len(new_seg))
            for k in range(max_len):
                left_line = old_seg[k] if k < len(old_seg) else ""
                right_line = new_seg[k] if k < len(new_seg) else ""
                left_no = f"{old_no:4}" if k < len(old_seg) else "    "
                right_no = f"{new_no:4}" if k < len(new_seg) else "    "
                left = Text(f"{left_no}| {left_line}", style="red" if k < len(old_seg) else "")
                right = Text(f"{right_no}| {right_line}", style="green" if k < len(new_seg) else "")
                if not add_row(left, right):
                    break
                if k < len(old_seg):
                    old_no += 1
                if k < len(new_seg):
                    new_no += 1

    console.print(Panel(table, title="代码变更预览", border_style="cyan"))
    console.print(f"变更块: {changed_blocks} | 新增行: {added} | 删除行: {removed}")

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
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
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
async def write_file(path: str, content: str, context=None) -> str:
    try:
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        old_content = ""
        if os.path.exists(path):
            async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
                old_content = await f.read()
        _render_diff(path, old_content, content)
        decision = await ask_selection("是否保留这些修改？", ["保留修改", "放弃修改"], context)
        if "放弃" in decision:
            return "已放弃修改。"
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
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
async def edit_file(path: str, old_str: str, new_str: str, context=None) -> str:
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    if not os.path.exists(path):
        return f"Error: File {path} not found."
        
    try:
        async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
            content = await f.read()
            
        if old_str not in content:
            return "Error: old_str not found in file."
            
        if content.count(old_str) > 1:
            idx = content.find(old_str)
            new_content = content[:idx] + new_str + content[idx+len(old_str):]
        else:
            new_content = content.replace(old_str, new_str)
        
        _render_diff(path, content, new_content)
        decision = await ask_selection("是否保留这些修改？", ["保留修改", "放弃修改"], context)
        if "放弃" in decision:
            return "已放弃修改。"
        async with aiofiles.open(path, mode='w', encoding='utf-8') as f:
            await f.write(new_content)
            
        return "Successfully edited file."
    except Exception as e:
        return f"Error editing file: {str(e)}"
