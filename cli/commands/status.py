"""
swarm status — per-Cog results table.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from cli.console import ACCENT, DIM, SECONDARY, console, warn

_ROOT = Path(__file__).resolve().parents[2]


def status(
    run_tag: str = typer.Option(..., "--run_tag", help="Run tag to inspect"),
) -> None:
    """Show per-Cog result summary for a completed or in-progress run."""
    sys.path.insert(0, str(_ROOT))
    try:
        from agents.cog_manager import list_cog_branches, load_cog_status
    except ImportError as e:
        from cli.console import error
        error(f"Cannot import cog_manager: {e}")
        raise typer.Exit(1)

    branches = list_cog_branches(_ROOT, run_tag)
    cog_ids = sorted({b["cog_id"] for b in branches})

    if not cog_ids:
        warn(f"No Cog branches found for run_tag=[bold]{run_tag}[/]")
        raise typer.Exit(0)

    rows = load_cog_status(_ROOT, run_tag, cog_ids)

    table = Table(border_style=DIM, show_header=True, header_style=SECONDARY, expand=False)
    table.add_column("Cog", style=ACCENT)
    table.add_column("Metric", style=SECONDARY)
    table.add_column("Best", justify="right")
    table.add_column("Keep/Total", justify="right", style=DIM)
    table.add_column("Top Description", style=DIM)

    for row in rows:
        best_str = f"[bold yellow]{row['best']:.4f}[/]" if row["best"] is not None else "[dim]no data[/]"
        keep_str = f"{row['n_keep']}/{row['n_total']}"
        table.add_row(
            row["cog_id"],
            row["metric_col"],
            best_str,
            keep_str,
            row["best_desc"],
        )

    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    footer = f"[dim]{now} UTC[/]"
    console.print(
        Panel(
            table,
            title=f"[{SECONDARY}]Cog Status — {run_tag}[/]",
            subtitle=footer,
            border_style=DIM,
        )
    )

    if all(r["n_total"] == 0 for r in rows):
        console.print(f"  [dim]No results yet — Cog experiments still running.[/]")
