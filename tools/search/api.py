import os
import glob as pyglob
from tools.base import registry
from utils.logger import logger
from tools.search.engine import RipgrepSearcher
from tools.search.templates import get_template
from tools.search.parser import SyntaxAwareParser

searcher = RipgrepSearcher()
parser = SyntaxAwareParser()

@registry.register(
    name="smart_search",
    description="Precise code search using Ripgrep + Syntax Templates + Tree-sitter.",
    parameters={
        "properties": {
            "query": {"type": "string", "description": "Search query or regex pattern"},
            "template": {"type": "string", "description": "Optional scenario template: 'def', 'class', 'assignment', 'call', 'import', etc."},
            "lang": {"type": "string", "description": "Language for template (e.g., 'python', 'javascript', 'go', 'java', 'rust')"},
            "path": {"type": "string", "description": "Root directory to search", "default": "."},
            "include": {"type": "string", "description": "Glob pattern to include (e.g., '*.py')", "default": None},
            "expand_scope": {"type": "boolean", "description": "If true, returns the full function/class body of the match.", "default": False}
        },
        "required": ["query"]
    }
)
async def smart_search(query: str, template: str = None, lang: str = "python", path: str = ".", include: str = None, expand_scope: bool = False) -> str:
    """
    执行智能代码搜索 (Smart Search)。
    
    Args:
        query: 搜索关键词或正则模式。
        template: 场景模板 (如 'def', 'class', 'call')，用于自动生成正则。
        lang: 编程语言，配合模板使用。
        path: 搜索根目录。
        include: 文件包含模式 (Glob)。
        expand_scope: 是否使用 Tree-sitter 扩展匹配范围 (返回完整的函数/类定义)。
    """
    final_pattern = query
    
    # 1. 应用场景模板
    if template:
        tpl = get_template(lang, template)
        if tpl:
            final_pattern = tpl.format(pattern=query)
            logger.info(f"应用搜索模板: {template} ({lang}) -> {final_pattern}")
        else:
            logger.warning(f"未找到语言 '{lang}' 的模板 '{template}'，将使用原始查询。")

    # 2. 执行搜索 (Ripgrep / Fallback)
    raw_results = await searcher.search(final_pattern, path=path, include=include)
    
    # 如果不需要扩展范围，或者搜索出错/无结果，直接返回
    if not expand_scope or "未找到匹配项" in raw_results or raw_results.startswith("Error") or raw_results.startswith("rg 执行错误"):
        return raw_results

    # 3. 范围扩展逻辑 (Tree-sitter Scope Expansion)
    # 这是一个实验性功能，旨在返回更完整的上下文。
    lines = raw_results.split('\n')
    expanded_results = []
    processed_files = set()

    for line in lines:
        # 预期格式: file_path:line_num: content
        parts = line.split(':', 2)
        if len(parts) < 3: continue
        
        file_path = parts[0]
        try:
            line_num = int(parts[1])
        except ValueError:
            continue
            
        # 避免重复处理同一文件的同一范围
        # 简化版: 仅检查是否处理过该文件+范围
        
        scope = parser.get_function_scope(file_path, line_num)
        if scope:
            start, end = scope
            key = f"{file_path}:{start}-{end}"
            if key in processed_files:
                continue
            processed_files.add(key)
            
            expanded_results.append(f"\n--- Scope: {file_path} ({start}-{end}) ---")
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    all_lines = f.readlines()
                    # Python 列表切片是 0-indexed，start/end 是 1-indexed
                    # 我们需要 start-1 到 end
                    snippet = "".join(all_lines[start-1:end])
                    expanded_results.append(snippet.strip())
            except Exception:
                expanded_results.append(f"(无法读取文件内容: {file_path})")
        else:
            # 如果无法获取范围 (如 Tree-sitter 未安装或解析失败)，保留原始行
            expanded_results.append(line)

    if not expanded_results:
        return raw_results
        
    return "\n".join(expanded_results)

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
    """
    按名称查找文件 (Glob)。
    """
    try:
        full_pattern = os.path.join(path, pattern)
        files = pyglob.glob(full_pattern, recursive=True)
        # 过滤掉常见的无关目录
        files = [f for f in files if ".git" not in f and "venv" not in f and "__pycache__" not in f]
        
        if not files:
            return "未找到文件。"
            
        # 按修改时间排序 (最新的在前)
        files.sort(key=lambda x: os.path.getmtime(x) if os.path.isfile(x) else 0, reverse=True)
        
        return "\n".join(files[:50]) # 限制返回前 50 个
    except Exception as e:
        return f"执行 glob 出错: {str(e)}"

@registry.register(
    name="grep",
    description="Search for a regex pattern in files (Legacy, use smart_search if possible).",
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
    """
    传统的 grep 搜索 (建议使用 smart_search)。
    """
    # 转发给 smart searcher 以获得更好的性能
    return await searcher.search(pattern, path, include)
