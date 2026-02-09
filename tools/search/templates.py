# --- Scenario-based Regex Template Library (场景化正则模板库) ---
# 该库为不同编程语言的常见代码搜索场景提供优化的正则表达式。
# 通过使用这些模板，用户只需提供关键词，无需编写复杂的正则。

REGEX_TEMPLATES = {
    "python": {
        "def": r"def\s+{pattern}",            # 函数定义
        "class": r"class\s+{pattern}",        # 类定义
        "assignment": r"{pattern}\s*=",       # 变量赋值
        "call": r"{pattern}\s*\(",            # 函数调用
        "import": r"(import\s+{pattern}|from\s+\S+\s+import\s+{pattern})", # 导入
        "decorator": r"@{pattern}",           # 装饰器
        "exception": r"except\s+{pattern}",   # 异常捕获
        "string": r"['\"]{pattern}['\"]",     # 字符串字面量
        "comment": r"#.*{pattern}",           # 注释
        "todo": r"#\s*TODO.*{pattern}"        # TODO 标记
    },
    "javascript": {
        "function": r"function\s+{pattern}",
        "arrow_function": r"(const|let|var)\s+{pattern}\s*=\s*\(", # 箭头函数
        "class": r"class\s+{pattern}",
        "method": r"{pattern}\s*\([^)]*\)\s*\{",
        "assignment": r"{pattern}\s*=",
        "const": r"const\s+{pattern}\s*=",
        "let": r"let\s+{pattern}\s*=",
        "var": r"var\s+{pattern}\s*=",
        "import": r"import.*{pattern}.*from",
        "export": r"export\s+.*{pattern}",
        "call": r"{pattern}\s*\(",
        "string": r"['\"`]{pattern}['\"`]",
        "comment": r"//.*{pattern}",
        "todo": r"//\s*TODO.*{pattern}"
    },
    "typescript": {
        "interface": r"interface\s+{pattern}",
        "type": r"type\s+{pattern}\s*=",
        "enum": r"enum\s+{pattern}",
        "function": r"function\s+{pattern}",
        "arrow_function": r"(const|let|var)\s+{pattern}\s*=\s*\(",
        "class": r"class\s+{pattern}",
        "method": r"(public|private|protected)?\s*{pattern}\s*\([^)]*\)\s*[:\{]",
        "assignment": r"{pattern}\s*=",
        "const": r"const\s+{pattern}\s*[:=]",
        "import": r"import.*{pattern}.*from",
        "export": r"export\s+.*{pattern}",
        "decorator": r"@{pattern}",
        "call": r"{pattern}\s*\(",
        "comment": r"//.*{pattern}",
        "todo": r"//\s*TODO.*{pattern}"
    },
    "go": {
        "func": r"func\s+{pattern}",
        "method": r"func\s*\([^)]+\)\s*{pattern}",
        "struct": r"type\s+{pattern}\s+struct",
        "interface": r"type\s+{pattern}\s+interface",
        "assignment": r"{pattern}\s*:=",
        "var": r"var\s+{pattern}",
        "call": r"{pattern}\s*\(",
        "import": r"import\s+\(\s*[^\)]*{pattern}", # approximate
        "comment": r"//.*{pattern}",
        "todo": r"//\s*TODO.*{pattern}"
    },
    "java": {
        "class": r"class\s+{pattern}",
        "interface": r"interface\s+{pattern}",
        "method": r"(public|private|protected)\s+\S+\s+{pattern}\s*\(",
        "assignment": r"{pattern}\s*=",
        "new": r"new\s+{pattern}\s*\(",
        "annotation": r"@{pattern}",
        "import": r"import\s+.*{pattern}",
        "comment": r"//.*{pattern}",
        "todo": r"//\s*TODO.*{pattern}"
    },
    "cpp": {
        "class": r"class\s+{pattern}",
        "struct": r"struct\s+{pattern}",
        "function": r"\S+\s+{pattern}\s*\(", # simple function
        "assignment": r"{pattern}\s*=",
        "include": r"#include\s+[<\"]{pattern}[>\"]",
        "namespace": r"namespace\s+{pattern}",
        "comment": r"//.*{pattern}",
        "todo": r"//\s*TODO.*{pattern}"
    },
    "rust": {
        "fn": r"fn\s+{pattern}",
        "struct": r"struct\s+{pattern}",
        "enum": r"enum\s+{pattern}",
        "impl": r"impl\s+{pattern}",
        "trait": r"trait\s+{pattern}",
        "let": r"let\s+(mut\s+)?{pattern}",
        "const": r"const\s+{pattern}",
        "macro": r"{pattern}!",
        "mod": r"mod\s+{pattern}",
        "use": r"use\s+.*{pattern}",
        "comment": r"//.*{pattern}",
        "todo": r"//\s*TODO.*{pattern}"
    },
}

def get_template(lang: str, template_name: str) -> str:
    """
    根据语言和场景获取正则表达式模板。
    
    Args:
        lang (str): 编程语言 (e.g., 'python', 'javascript')
        template_name (str): 场景名称 (e.g., 'def', 'class')
        
    Returns:
        str: 格式化前的正则模板字符串，如果未找到则返回 None
    """
    if lang in REGEX_TEMPLATES and template_name in REGEX_TEMPLATES[lang]:
        return REGEX_TEMPLATES[lang][template_name]
    return None
