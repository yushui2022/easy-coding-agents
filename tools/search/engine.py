import shutil
import subprocess
import os
import glob as pyglob
import re
from utils.logger import logger

class RipgrepSearcher:
    """
    基于 ripgrep (rg) 的高性能代码搜索器。
    如果系统中未安装 rg，则降级为 Python 原生实现。
    """
    def __init__(self):
        # 检查系统路径中是否存在 rg 可执行文件
        self.rg_available = shutil.which("rg") is not None
        if not self.rg_available:
            logger.warning("未检测到 ripgrep (rg)，搜索功能将降级为 Python 原生实现 (速度较慢且不支持大文件)。")

    async def search(self, pattern: str, path: str = ".", include: str = None, context_lines: int = 0) -> str:
        """
        执行搜索的主入口。
        """
        if self.rg_available:
            return self._search_with_rg(pattern, path, include, context_lines)
        else:
            return self._search_fallback(pattern, path, include)

    def _search_with_rg(self, pattern: str, path: str, include: str, context_lines: int) -> str:
        """
        使用 subprocess 调用 rg 命令进行搜索。
        """
        # -n: 显示行号
        # --no-heading: 不按文件分组显示文件名 (每行都带文件名，方便解析)
        # --color=never: 禁止颜色输出
        cmd = ["rg", "-n", "--no-heading", "--color=never"]
        
        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])
            
        if include:
            # rg 使用 -g 参数处理 glob 模式
            cmd.extend(["-g", include])
            
        cmd.extend([pattern, path])
        
        try:
            # 执行 rg 命令
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                # 限制输出大小，防止上下文溢出
                lines = output.split('\n')
                if len(lines) > 200:
                    return "\n".join(lines[:200]) + f"\n... (已截断，剩余 {len(lines)-200} 个匹配项)"
                return output
            elif result.returncode == 1:
                return "未找到匹配项。"
            else:
                return f"rg 执行错误: {result.stderr}"
        except Exception as e:
            return f"运行 ripgrep 时发生异常: {str(e)}"

    def _search_fallback(self, pattern: str, path: str, include: str = "**/*") -> str:
        """
        Python 原生搜索实现 (Fallback)。
        增加了文件大小检查 (MAX 1MB) 以防止 OOM。
        """
        try:
            regex = re.compile(pattern)
            hits = []
            if not include: 
                include = "**/*"
            
            # 使用 glob 查找文件
            search_files = pyglob.glob(os.path.join(path, include), recursive=True)
            
            for filepath in search_files:
                if not os.path.isfile(filepath): continue
                
                # 过滤常见无关目录
                if any(ignore in filepath for ignore in [".git", "venv", "__pycache__", "node_modules", "dist", "build"]):
                    continue
                
                # 安全检查: 跳过大于 1MB 的文件
                try:
                    file_size = os.path.getsize(filepath)
                    if file_size > 1024 * 1024: # 1MB
                        continue
                except OSError:
                    continue

                # 尝试读取并匹配
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        # 检查是否为二进制文件 (简单的启发式: 检查前 1024 字节是否有 NULL)
                        # 这里我们用 errors='ignore' 实际上已经部分规避了，但为了性能最好还是略过
                        # 简单起见，我们按行读取，如果遇到解码错误会被 ignore
                        
                        for i, line in enumerate(f, 1):
                            if regex.search(line):
                                hits.append(f"{filepath}:{i}: {line.strip()}")
                                if len(hits) >= 100: break
                except Exception:
                    pass
                    
                if len(hits) >= 100: break
                    
            return "\n".join(hits) if hits else "未找到匹配项。"
        except Exception as e:
            return f"执行原生搜索时发生错误: {str(e)}"
