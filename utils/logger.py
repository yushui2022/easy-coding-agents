from rich.console import Console
from rich.logging import RichHandler
import logging

console = Console()

def setup_logger(debug=False):
    logging.basicConfig(
        level="INFO" if debug else "WARNING", # Global default to WARNING to keep it quiet
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, markup=True)]
    )
    
    # Suppress noisy libraries even if global level is INFO
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    # Set our own logger to INFO so we can see our own messages
    logger = logging.getLogger("easy_coding_agent")
    logger.setLevel(logging.INFO)
    
    return logger

logger = setup_logger()
