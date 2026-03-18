"""
swarm scan / swarm clean — artifact lifecycle via Calcinator.
"""
from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cli.console import ACCENT, DIM, SECONDARY, console, error, success, warn

_ROOT = Path(__file__).resolve().parents[2]


def _import_calcinator():
    sys.path.insert(0, str(_ROOT))
    try:
        import agents.calcinator as calc
        return calc
    except ImportError as e:
        error(f"Cannot import calcinator: {e}")
        raise typer.Exit(1)


ACTION_STYLE = {
    "purge":   "bold red",
    "archive": "yellow",
    "flag":    "cyan",
}

ACTION_ICON = {
    "purge":   "✗",
    "archive": "📦",
    "flag":    "⚠",
}


def _render_scan_table(artifacts: list[dict]) -> None:
    if not artifacts:
        success("Nothing to clean — workspace is tidy.")
        return

    by_action: dict[str, list] = {}
    for a in artifacts:
        by_action.setdefault(a["action"], []).append(a)

    for action in ("purge", "archive", "flag"):
        items = by_action.get(action, [])
        if not items:
            continue

        style = ACTION_STYLE[action]
        icon = ACTION_ICON[action]
        label = {"purge": "PURGE (delete)", "archive": "ARCHIVE (move)", "flag": "FLAG (warn)"}[action]

        table = Table(border_style=DIM, show_header=True, header_style=SECONDARY, expand=False)
        table.add_column("Category", style=DIM)
        table.add_column("Path")
        table.add_column("Reason", style=DIM)

        for a in items:
            table.add_row(a["category"], a["path"], a["reason"])

        title_text = Text()
        title_text.append(f"{icon} {label} — {len(items)} item(s)", style=style)
        console.print(Panel(table, title=title_text, border_style=DIM))


def scan(
    run_tag: str = typer.Option(None, "--run_tag", help="Scope to a specific run_tag"),
) -> None:
    """Dry-run artifact scan — show what would be touched (no changes made)."""
    calc = _import_calcinator()
    with console.status(f"[{DIM}]scanning artifacts...[/]"):
        artifacts = calc.scan_artifacts(_ROOT, run_tag)
    _render_scan_table(artifacts)
    console.print(f"  [dim]Total: {len(artifacts)} artifact(s) flagged.[/]")
    if artifacts:
        console.print(f"  [dim]Run [bold]swarm clean[/] to archive + purge.[/]")


def clean(
    run_tag: str = typer.Option(None, "--run_tag", help="Scope to a specific run_tag"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview actions without making changes"),
) -> None:
    """Archive completed results and purge orphaned artifacts."""
    calc = _import_calcinator()
    tag = "[DRY RUN] " if dry_run else ""

    with console.status(f"[{DIM}]scanning artifacts...[/]"):
        artifacts = calc.scan_artifacts(_ROOT, run_tag)

    if not artifacts:
        success("Nothing to clean — workspace is tidy.")
        raise typer.Exit(0)

    _render_scan_table(artifacts)

    if not dry_run:
        proceed = typer.confirm(f"\n  {tag}Proceed with archive + purge?", default=False)
        if not proceed:
            warn("Aborted.")
            raise typer.Exit(0)

    with console.status(f"[{DIM}]{tag}archiving...[/]"):
        archive_done = calc.do_archive(_ROOT, artifacts, dry=dry_run)
    with console.status(f"[{DIM}]{tag}purging...[/]"):
        purge_done = calc.do_purge(_ROOT, artifacts, dry=dry_run)

    for line in archive_done + purge_done:
        console.print(f"  [dim]{line.strip()}[/]")

    total = len(archive_done) + len(purge_done)
    success(f"{tag}Archived: {len(archive_done)}  Purged: {len(purge_done)}  Total: {total}")

    # Write manifest for flagged items
    flagged = [a for a in artifacts if a["action"] == "flag"]
    if flagged and not dry_run:
        manifest_path = calc.do_flag(_ROOT, flagged)
        console.print(f"  [dim]Warnings written to: {manifest_path.relative_to(_ROOT)}[/]")
