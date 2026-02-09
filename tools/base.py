from typing import Dict, Any, Callable, List
from dataclasses import dataclass
import inspect

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    func: Callable
    
class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}

    def register(self, name: str, description: str, parameters: Dict[str, Any]):
        def decorator(func):
            self.tools[name] = ToolDefinition(name, description, parameters, func)
            return func
        return decorator

    def get_schema(self) -> List[Dict[str, Any]]:
        """Generate OpenAI/ZhipuAI compatible tool schema."""
        schemas = []
        for tool in self.tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": tool.parameters.get("properties", {}),
                        "required": tool.parameters.get("required", [])
                    }
                }
            })
        return schemas

    async def execute(self, name: str, args: Dict[str, Any], context: Any = None) -> str:
        if name not in self.tools:
            return f"Error: Tool '{name}' not found."
        try:
            func = self.tools[name].func
            
            # Check if function accepts 'context' argument
            sig = inspect.signature(func)
            if "context" in sig.parameters:
                if context is None:
                     return f"Error: Tool '{name}' requires context but none was provided."
                # Inject context into args (don't modify original args dict)
                call_args = args.copy()
                call_args["context"] = context
            else:
                call_args = args

            if inspect.iscoroutinefunction(func):
                return await func(**call_args)
            return func(**call_args)
        except Exception as e:
            return f"Error executing {name}: {str(e)}"

# Global registry
registry = ToolRegistry()
