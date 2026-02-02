import glob as pyglob
import os
import re
from tools.base import registry

@registry.register(
    name="glob",
    description="Find files matching a glob pattern.",
    parameters={
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern (e.g., **/*.py)"},
            "path": {"type": "string", "description": "Base directory", "default": "."}
        },
        "required": ["pattern"]
    }
)
async def glob_search(pattern: str, path: str = ".") -> str:
    try:
        full_pattern = os.path.join(path, pattern)
        files = pyglob.glob(full_pattern, recursive=True)
        # Filter out git/venv directories usually
        files = [f for f in files if ".git" not in f and "venv" not in f and "__pycache__" not in f]
        
        if not files:
            return "No files found."
            
        # Sort by modification time (newest first)
        files.sort(key=lambda x: os.path.getmtime(x) if os.path.isfile(x) else 0, reverse=True)
        
        return "\n".join(files[:50]) # Limit to top 50
    except Exception as e:
        return f"Error executing glob: {str(e)}"

@registry.register(
    name="grep",
    description="Search for a regex pattern in files.",
    parameters={
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern"},
            "path": {"type": "string", "description": "Directory to search in", "default": "."},
            "include": {"type": "string", "description": "Glob pattern for files to include (e.g., *.py)", "default": "**/*"}
        },
        "required": ["pattern"]
    }
)
async def grep_search(pattern: str, path: str = ".", include: str = "**/*") -> str:
    try:
        regex = re.compile(pattern)
        hits = []
        
        search_files = pyglob.glob(os.path.join(path, include), recursive=True)
        
        for filepath in search_files:
            if not os.path.isfile(filepath):
                continue
            if any(ignore in filepath for ignore in [".git", "venv", "__pycache__", "node_modules"]):
                continue
                
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    for i, line in enumerate(f, 1):
                        if regex.search(line):
                            hits.append(f"{filepath}:{i}: {line.strip()}")
                            if len(hits) >= 100: # Limit results
                                break
            except Exception:
                pass
            if len(hits) >= 100:
                break
                
        if not hits:
            return "No matches found."
            
        return "\n".join(hits)
    except Exception as e:
        return f"Error executing grep: {str(e)}"
