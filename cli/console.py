"""
Rich console singleton + theme helpers for the swarm CLI.
"""
from rich.console import Console
from rich.text import Text

console = Console()

# Color palette
ACCENT = "bold yellow"       # amber/alchemical gold — task IDs, best metrics, key names
SECONDARY = "cyan"           # stage labels, branch names, column headers
DIM = "dim"                  # timestamps, secondary info, paths
SUCCESS = "bold green"
ERROR = "bold red"
WARN = "yellow"


def header() -> None:
    """Print the swarm typographic header."""
    title = Text()
    title.append("  ⚗  ", style=ACCENT)
    title.append("transmute", style=DIM)
    title.append("·swarm", style="bold white")
    console.print(title)
    console.print("  " + "─" * 42, style=DIM)


def success(msg: str) -> None:
    console.print(f"  [bold green]✓[/] {msg}")


def error(msg: str) -> None:
    console.print(f"  [bold red]✗[/] {msg}")


def warn(msg: str) -> None:
    console.print(f"  [yellow]⚠[/]  {msg}")
