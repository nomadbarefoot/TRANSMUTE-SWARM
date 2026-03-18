"""
swarm cogs — Cog branch lifecycle subcommands (list / cleanup / purge).
"""
from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from cli.console import ACCENT, DIM, SECONDARY, console, error, success, warn

app = typer.Typer(help="Manage Cog branches (list / cleanup / purge).")

_ROOT = Path(__file__).resolve().parents[2]


def _import_cog_manager():
    sys.path.insert(0, str(_ROOT))
    try:
        import agents.cog_manager as cm
        return cm
    except ImportError as e:
        error(f"Cannot import cog_manager: {e}")
        raise typer.Exit(1)


@app.command("list")
def list_cogs(
    run_tag: str = typer.Option(None, "--run_tag", help="Filter by run_tag"),
) -> None:
    """List Cog branches (local and remote)."""
    cm = _import_cog_manager()
    branches = cm.list_cog_branches(_ROOT, run_tag)

    if not branches:
        label = f" for run_tag=[bold]{run_tag}[/]" if run_tag else ""
        warn(f"No Cog branches found{label}.")
        raise typer.Exit(0)

    # Group by run_tag
    by_run: dict[str, list] = {}
    for b in branches:
        by_run.setdefault(b["run_tag"], []).append(b)

    for rt in sorted(by_run):
        table = Table(border_style=DIM, show_header=True, header_style=SECONDARY, expand=False)
        table.add_column("Cog ID", style=ACCENT)
        table.add_column("Branch", style=DIM)
        table.add_column("Location")
        table.add_column("Age", justify="right", style=DIM)

        for b in sorted(by_run[rt], key=lambda x: x["cog_id"]):
            age = cm.branch_age_days(_ROOT, b["name"], b["remote"])
            age_str = f"{age:.1f}d" if age is not None else "?"
            loc = "[dim]remote[/]" if b["remote"] else "[cyan]local[/]"
            table.add_row(b["cog_id"], b["name"], loc, age_str)

        console.print(
            Panel(table, title=f"[{SECONDARY}]Cogs — {rt}[/]", border_style=DIM)
        )


@app.command("cleanup")
def cleanup(
    run_tag: str = typer.Option(..., "--run_tag", help="Run tag to clean up"),
    remote: bool = typer.Option(False, "--remote", help="Also delete remote branches"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without deleting"),
) -> None:
    """Delete Cog branches for a completed run."""
    cm = _import_cog_manager()
    branches = cm.list_cog_branches(_ROOT, run_tag)

    if not branches:
        warn(f"No Cog branches found for run_tag=[bold]{run_tag}[/]")
        raise typer.Exit(0)

    tag = "[DRY RUN] " if dry_run else ""
    console.print(f"\n  [{SECONDARY}]{tag}cleanup — run_tag: {run_tag}[/]")

    if not dry_run:
        proceed = typer.confirm(f"  Delete {len(branches)} branch(es)?", default=False)
        if not proceed:
            warn("Aborted.")
            raise typer.Exit(0)

    deleted_local = deleted_remote = 0
    for b in branches:
        branch = b["name"]
        if not b["remote"]:
            console.print(f"  [dim]delete local   {branch}[/]")
            if not dry_run:
                cm.run(_ROOT, "git", "branch", "-D", branch, check=False)
            deleted_local += 1
        elif remote:
            console.print(f"  [dim]delete remote  {branch}[/]")
            if not dry_run:
                cm.run(_ROOT, "git", "push", "origin", "--delete", branch, check=False)
            deleted_remote += 1

    summary = f"{tag}local={deleted_local}  remote={deleted_remote}"
    if not remote:
        summary += "  [dim](pass --remote to also delete remote branches)[/]"
    success(summary)


@app.command("purge")
def purge(
    older_than_days: float = typer.Option(..., "--older-than-days", help="Delete branches older than N days"),
    remote: bool = typer.Option(False, "--remote", help="Also delete remote branches"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without deleting"),
) -> None:
    """Delete all Cog branches older than N days."""
    cm = _import_cog_manager()
    branches = cm.list_cog_branches(_ROOT)

    tag = "[DRY RUN] " if dry_run else ""
    stale = []
    for b in branches:
        age = cm.branch_age_days(_ROOT, b["name"], b["remote"])
        if age is not None and age >= older_than_days:
            stale.append((b, age))

    if not stale:
        success(f"No Cog branches older than {older_than_days:.0f} days.")
        raise typer.Exit(0)

    console.print(f"\n  [{SECONDARY}]{tag}purge — {len(stale)} branch(es) ≥ {older_than_days:.0f}d old[/]")

    if not dry_run:
        proceed = typer.confirm(f"  Purge {len(stale)} branch(es)?", default=False)
        if not proceed:
            warn("Aborted.")
            raise typer.Exit(0)

    count = 0
    for b, age in stale:
        action = "remote" if b["remote"] else "local "
        console.print(f"  [dim]{tag}delete {action}  {b['name']}  ({age:.1f}d old)[/]")
        if not dry_run:
            if b["remote"] and remote:
                cm.run(_ROOT, "git", "push", "origin", "--delete", b["name"], check=False)
            elif not b["remote"]:
                cm.run(_ROOT, "git", "branch", "-D", b["name"], check=False)
        count += 1

    summary = f"{tag}Processed {count} branch(es) older than {older_than_days:.0f} days."
    if not remote:
        summary += "  [dim](remote branches skipped — pass --remote to include)[/]"
    success(summary)
