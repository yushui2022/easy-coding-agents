import platform
import random
import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text
from core.config import Config

# ASCII Art Logo for "ECA" (Easy Coding Agent)
LOGO = """
███████╗ ██████╗ ██████╗ 
██╔════╝██╔════╝██╔═══██╗
█████╗  ██║     ███████║ 
██╔══╝  ██║     ██╔═══██║
███████╗╚██████╗██║   ██║
╚══════╝ ╚═════╝╚═╝   ╚═╝
"""

def get_random_tip():
    tips = [
        "💡 Press [bold]Shift+Tab[/bold] to toggle modes (Plan/Code/Chat).",
        "💡 Use [bold]/exit[/bold] to quit the application.",
        "💡 Files created are stored in [bold]workspace/[/bold] by default.",
        "💡 I automatically manage memory to keep context relevant.",
        "💡 Use [bold]manage_core_memory[/bold] to save reusable rules.",
        "💡 In Plan Mode, I can help you architect before coding.",
    ]
    return random.choice(tips)

def render_splash_screen():
    """Renders the startup splash screen similar to Claude Code."""
    console = Console()
    console.clear()
    
    # Left Side: Info & Logo
    left_table = Table.grid(padding=0)
    left_table.add_column(justify="left")
    
    logo_text = Text(LOGO, style="bold green")
    left_table.add_row(logo_text)
    left_table.add_row(Text("Easy Coding Agents", style="bold white on green"))
    left_table.add_row("")
    
    # Environment Info
    info_table = Table.grid(padding=(0, 1))
    info_table.add_column(style="dim", justify="right")
    info_table.add_column(style="cyan")
    
    info_table.add_row("Model:", Config.MODEL_NAME.split("/")[-1]) # Shorten model name
    info_table.add_row("API:", Config.provider_label())
    info_table.add_row("OS:", f"{platform.system()} {platform.release()}")
    
    left_table.add_row(info_table)
    
    # Right Side: Tips
    right_table = Table.grid(padding=1)
    
    tips_panel = Panel(
        get_random_tip(),
        title="[bold]Tips for getting started[/bold]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
        width=50
    )
    right_table.add_row(tips_panel)
    
    # Recent Activity (Placeholder)
    # right_table.add_row(Text("\nRecent Activity:", style="dim"))
    # right_table.add_row(Text("No recent activity", style="dim italic"))
    
    # Main Layout Table
    main_grid = Table.grid(padding=(0, 4))
    main_grid.add_column()
    main_grid.add_column(justify="center") # Vertical center the right side? No, table row alignment.
    
    # Add content
    main_grid.add_row(left_table, right_table)
    
    # Outer Panel
    outer_panel = Panel(
        main_grid,
        title="[bold green]Welcome back![/bold green]",
        subtitle="[dim]Easy Coding Agents v2.0[/dim]",
        border_style="green",
        box=box.ROUNDED, # Claude uses rounded or heavy
        padding=(1, 2),
        expand=False
    )
    
    console.print(outer_panel, justify="center")
    console.print(f"[dim]Working Directory: {os.getcwd()}[/dim]", justify="center")
    console.print("")
