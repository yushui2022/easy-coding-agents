from typing import Optional, Tuple
from utils.logger import logger

class SyntaxAwareParser:
    """
    基于 Tree-sitter 的语法感知解析器。
    用于锁定代码块（函数、类）的有效范围，支持 Scope Expansion 功能。
    """
    def __init__(self):
        self.available = False
        try:
            from tree_sitter_languages import get_language, get_parser
            self.get_language = get_language
            self.get_parser = get_parser
            self.available = True
            logger.info("Tree-sitter initialized successfully via tree-sitter-languages.")
        except ImportError as e:
            logger.warning(f"Tree-sitter 初始化失败: {e} (Smart Search 的 Scope Expansion 功能将不可用)")
            pass
            
    def _get_node_scope(self, file_path: str, line_number: int, node_types: list) -> Optional[Tuple[int, int]]:
        """查找特定类型节点的范围的通用辅助方法。"""
        if not self.available:
            return None
            
        lang_id = self._infer_language(file_path)
        if not lang_id:
            return None
            
        try:
            language = self.get_language(lang_id)
            parser = self.get_parser(lang_id)
            
            with open(file_path, "rb") as f:
                source_code = f.read()
            
            tree = parser.parse(source_code)
            root_node = tree.root_node
            
            # Tree-sitter 使用 0-based 索引，用户输入为 1-based
            target_line = line_number - 1
            
            # 找到覆盖该行的最小节点
            # 启发式: 使用 point_range 查询
            # 注意: 这里假设 target_line 在文件范围内
            
            target_node = root_node.named_descendant_for_point_range((target_line, 0), (target_line, 0))
            
            # 向上遍历以找到符合 node_types 的最近闭包
            current = target_node
            while current:
                if current.type in node_types:
                    return (current.start_point.row + 1, current.end_point.row + 1)
                current = current.parent
                
            return None
            
        except Exception as e:
            logger.debug(f"Tree-sitter parse error for {file_path}: {e}")
            return None

    def _infer_language(self, file_path: str) -> Optional[str]:
        """根据文件扩展名推断 Tree-sitter 语言 ID。"""
        ext = file_path.split('.')[-1].lower()
        mapping = {
            'py': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'tsx': 'tsx',
            'go': 'go',
            'java': 'java',
            'cpp': 'cpp',
            'c': 'c',
            'rs': 'rust',
            'html': 'html',
            'css': 'css',
            'json': 'json'
        }
        return mapping.get(ext)

    def get_function_scope(self, file_path: str, line_number: int) -> Optional[Tuple[int, int]]:
        """
        返回包含指定行号的函数的 (start_line, end_line)。
        """
        # 常见语言的函数节点类型
        func_types = [
            'function_definition', # python, c
            'function_declaration', # js, ts, go, java
            'method_declaration', # java, go
            'arrow_function', # js, ts
            'method_definition', # python class methods
            'func_literal', # go
        ]
        return self._get_node_scope(file_path, line_number, func_types)

    def get_class_scope(self, file_path: str, line_number: int) -> Optional[Tuple[int, int]]:
        """
        返回包含指定行号的类的 (start_line, end_line)。
        """
        class_types = [
            'class_definition', # python
            'class_declaration', # js, ts, java, cpp
            'struct_specifier', # cpp
            'type_specifier', # go (struct)
        ]
        return self._get_node_scope(file_path, line_number, class_types)
