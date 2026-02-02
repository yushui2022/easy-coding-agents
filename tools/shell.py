import asyncio
import subprocess
import platform
from tools.base import registry

@registry.register(
    name="bash",
    description="Execute a shell command (bash/cmd/powershell).",
    parameters={
        "properties": {
            "cmd": {"type": "string", "description": "Command to execute"}
        },
        "required": ["cmd"]
    }
)
async def run_shell(cmd: str) -> str:
    # Determine shell based on OS
    shell = True
    if platform.system() == "Windows":
        # On Windows, we might want to prefix with powershell or cmd if needed
        # But subprocess with shell=True defaults to cmd.exe usually.
        # Let's try to run as is.
        pass
    
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            return "Error: Command timed out after 30s."
            
        output = stdout.decode('utf-8', errors='replace')
        error = stderr.decode('utf-8', errors='replace')
        
        result = output
        if error:
            result += f"\nSTDERR:\n{error}"
            
        if not result.strip():
            return "(Command executed with no output)"
            
        return result.strip()
    except Exception as e:
        return f"Error executing command: {str(e)}"
