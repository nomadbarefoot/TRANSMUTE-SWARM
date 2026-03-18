"""
Calcinator — Artifact lifecycle manager for TRANSMUTE-SWARM.

In alchemy, calcination burns away dross (impurities/waste), leaving only the
pure substance. The Calcinator does the same: it scans the repo for stale
branches, orphaned cog dirs, unused scaffolds, and completed run artifacts,
then archives, flags, or purges them.

Triggered automatically after `cog_manager create`, or run manually.

Commands:
  scan    [--run_tag <tag>]  Dry-run: show what would be touched (no changes)
  archive [--run_tag <tag>]  Move completed results/logs to results/archive/
  purge   [--run_tag <tag>]  Delete orphaned cog dirs, scaffolds, stale branches
  flag    [--run_tag <tag>]  Write calcinator_manifest.yaml without touching anything
  clean   [--run_tag <tag>]  Archive + purge (full cleanup)

Artifact categories:
  orphaned_cog_dir     cogs/<id>/ whose task_id is not in task_registry.yaml
  orphaned_solution    solutions/<file> not referenced by any registry entry
  scaffold_solution    solution file containing NotImplementedError (never used)
  archivable_results   results/results_<id>.tsv with no active cog branches
  archivable_log       results/logs/<id>.log with no active cog branches
  stale_discovery      discoveries/<id>.md for task not in registry
  stale_branch         cog branches for completed/cleaned runs (delegates to cog_manager)
"""
import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Registry + branch helpers
# ---------------------------------------------------------------------------

def _load_registry(root: Path) -> dict:
    path = root / "config" / "task_registry.yaml"
    if path.exists():
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return data.get("tasks", {})
        except Exception:
            pass
    return {}


def _registered_solution_files(registry: dict) -> set[str]:
    return {cfg["solution_file"] for cfg in registry.values() if "solution_file" in cfg}


def _list_active_cog_task_ids(root: Path) -> set[str]:
    """Return set of cog_ids that have at least one active local or remote branch."""
    import subprocess
    active = set()
    try:
        r = subprocess.run(
            ["git", "branch", "--format=%(refname:short)"],
            cwd=root, capture_output=True, text=True, check=False
        )
        for name in r.stdout.splitlines():
            parts = name.strip().split("/")
            if len(parts) == 3 and parts[0] == "cogs":
                active.add(parts[2])
        r = subprocess.run(
            ["git", "branch", "-r", "--format=%(refname:short)"],
            cwd=root, capture_output=True, text=True, check=False
        )
        for name in r.stdout.splitlines():
            name = name.strip().removeprefix("origin/")
            parts = name.split("/")
            if len(parts) == 3 and parts[0] == "cogs":
                active.add(parts[2])
    except Exception:
        pass
    return active


def _is_scaffold(path: Path) -> bool:
    """Return True if the solution file is an unmodified scaffold (never used)."""
    try:
        return "NotImplementedError" in path.read_text()
    except Exception:
        return False


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def scan_artifacts(root: Path, run_tag: str | None = None) -> list[dict]:
    """
    Scan for stale/orphaned artifacts. Returns list of artifact dicts:
      { category, path, reason, action }
    """
    registry = _load_registry(root)
    registered_ids = set(registry.keys())
    registered_solutions = _registered_solution_files(registry)
    active_cog_ids = _list_active_cog_task_ids(root)

    artifacts = []

    # --- Orphaned cog dirs ---
    cogs_dir = root / "cogs"
    if cogs_dir.exists():
        for cog_dir in sorted(cogs_dir.iterdir()):
            if not cog_dir.is_dir():
                continue
            tid = cog_dir.name
            if run_tag and tid != run_tag:
                # Only flag if explicitly scoped (run_tag here means task_id scope)
                pass
            if tid not in registered_ids:
                artifacts.append({
                    "category": "orphaned_cog_dir",
                    "path": str(cog_dir.relative_to(root)),
                    "reason": f"task '{tid}' not in task_registry.yaml",
                    "action": "purge",
                })

    # --- Solution files ---
    solutions_dir = root / "solutions"
    if solutions_dir.exists():
        for sol in sorted(solutions_dir.iterdir()):
            if sol.suffix != ".py" or sol.name.startswith("__"):
                continue
            rel = str(sol.relative_to(root))
            if rel not in registered_solutions:
                artifacts.append({
                    "category": "orphaned_solution",
                    "path": rel,
                    "reason": f"not referenced by any task in task_registry.yaml",
                    "action": "purge",
                })
            elif _is_scaffold(sol):
                artifacts.append({
                    "category": "scaffold_solution",
                    "path": rel,
                    "reason": "contains NotImplementedError — scaffold never modified",
                    "action": "flag",
                })

    # --- Results TSVs ---
    results_dir = root / "results"
    if results_dir.exists():
        for tsv in sorted(results_dir.glob("results_*.tsv")):
            tid = tsv.stem.removeprefix("results_")
            if run_tag and tid != run_tag:
                continue
            if tid not in active_cog_ids and tid in registered_ids:
                artifacts.append({
                    "category": "archivable_results",
                    "path": str(tsv.relative_to(root)),
                    "reason": f"no active cog branches for task '{tid}'",
                    "action": "archive",
                })
            elif tid not in registered_ids:
                artifacts.append({
                    "category": "orphaned_results",
                    "path": str(tsv.relative_to(root)),
                    "reason": f"task '{tid}' not in task_registry.yaml",
                    "action": "purge",
                })

    # --- Log files ---
    logs_dir = results_dir / "logs" if results_dir.exists() else None
    if logs_dir and logs_dir.exists():
        for log in sorted(logs_dir.glob("*.log")):
            tid = log.stem
            if run_tag and tid != run_tag:
                continue
            if tid not in active_cog_ids and tid in registered_ids:
                artifacts.append({
                    "category": "archivable_log",
                    "path": str(log.relative_to(root)),
                    "reason": f"no active cog branches for task '{tid}'",
                    "action": "archive",
                })
            elif tid not in registered_ids:
                artifacts.append({
                    "category": "orphaned_log",
                    "path": str(log.relative_to(root)),
                    "reason": f"task '{tid}' not in task_registry.yaml",
                    "action": "purge",
                })

    # --- Stale discoveries ---
    discoveries_dir = root / "discoveries"
    if discoveries_dir.exists():
        skip = {"shared_context.md", "archive"}
        for disc in sorted(discoveries_dir.iterdir()):
            if disc.name in skip or not disc.suffix == ".md":
                continue
            tid = disc.stem
            if tid not in registered_ids:
                artifacts.append({
                    "category": "stale_discovery",
                    "path": str(disc.relative_to(root)),
                    "reason": f"task '{tid}' not in task_registry.yaml",
                    "action": "archive",
                })

    return artifacts


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _archive_file(path: Path, archive_dir: Path, ts: str) -> Path:
    """Move a file to archive_dir with timestamp suffix."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    suffix = path.suffix
    dest = archive_dir / f"{stem}_{ts}{suffix}"
    shutil.move(str(path), dest)
    return dest


def do_archive(root: Path, artifacts: list[dict], dry: bool = False) -> list[str]:
    """Archive archivable artifacts. Returns list of actions taken."""
    archive_results = root / "results" / "archive"
    archive_disc = root / "discoveries" / "archive"
    ts = _ts()
    done = []

    for a in artifacts:
        if a["action"] != "archive":
            continue
        path = root / a["path"]
        if not path.exists():
            continue
        if "result" in a["category"] or "log" in a["category"]:
            dest_dir = archive_results
        else:
            dest_dir = archive_disc
        tag = "[DRY] " if dry else ""
        done.append(f"  {tag}archive  {a['path']}  →  {dest_dir.relative_to(root)}/")
        if not dry:
            _archive_file(path, dest_dir, ts)

    return done


def do_purge(root: Path, artifacts: list[dict], dry: bool = False) -> list[str]:
    """Delete orphaned artifacts. Returns list of actions taken."""
    done = []
    for a in artifacts:
        if a["action"] != "purge":
            continue
        path = root / a["path"]
        tag = "[DRY] " if dry else ""
        if path.is_dir():
            done.append(f"  {tag}purge dir  {a['path']}  ({a['reason']})")
            if not dry:
                shutil.rmtree(path)
        elif path.is_file():
            done.append(f"  {tag}purge file {a['path']}  ({a['reason']})")
            if not dry:
                path.unlink()
    return done


def do_flag(root: Path, artifacts: list[dict]) -> Path:
    """Write calcinator_manifest.yaml with flagged artifacts."""
    manifest_path = root / "calcinator_manifest.yaml"
    manifest = {
        "generated_at": _ts(),
        "artifacts": artifacts,
    }
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)
    return manifest_path


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

CATEGORY_COLORS = {
    "orphaned_cog_dir":   "🗑 ",
    "orphaned_solution":  "🗑 ",
    "orphaned_results":   "🗑 ",
    "orphaned_log":       "🗑 ",
    "scaffold_solution":  "⚠  ",
    "archivable_results": "📦 ",
    "archivable_log":     "📦 ",
    "stale_discovery":    "📦 ",
}


def print_scan_report(artifacts: list[dict]) -> None:
    if not artifacts:
        print("  ✓ Nothing to clean.")
        return

    by_action: dict[str, list] = {}
    for a in artifacts:
        by_action.setdefault(a["action"], []).append(a)

    for action in ("purge", "archive", "flag"):
        items = by_action.get(action, [])
        if not items:
            continue
        label = {"purge": "PURGE (delete)", "archive": "ARCHIVE (move)", "flag": "FLAG (warn)"}[action]
        print(f"\n  {label} — {len(items)} item(s):")
        for a in items:
            icon = CATEGORY_COLORS.get(a["category"], "   ")
            print(f"    {icon}{a['path']}")
            print(f"        reason: {a['reason']}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_scan(root: Path, args: argparse.Namespace) -> None:
    run_tag = getattr(args, "run_tag", None)
    print(f"\n[calcinator] scan{' run_tag=' + run_tag if run_tag else ''}")
    artifacts = scan_artifacts(root, run_tag)
    print_scan_report(artifacts)
    print(f"\n  Total: {len(artifacts)} artifact(s) flagged.")
    print("  Run 'clean' to archive + purge, or 'flag' to write manifest only.")


def cmd_archive(root: Path, args: argparse.Namespace) -> None:
    run_tag = getattr(args, "run_tag", None)
    dry = getattr(args, "dry_run", False)
    artifacts = scan_artifacts(root, run_tag)
    print(f"\n[calcinator] archive{' (dry-run)' if dry else ''}")
    done = do_archive(root, artifacts, dry=dry)
    if done:
        for line in done:
            print(line)
    else:
        print("  Nothing to archive.")


def cmd_purge(root: Path, args: argparse.Namespace) -> None:
    run_tag = getattr(args, "run_tag", None)
    dry = getattr(args, "dry_run", False)
    artifacts = scan_artifacts(root, run_tag)
    print(f"\n[calcinator] purge{' (dry-run)' if dry else ''}")
    done = do_purge(root, artifacts, dry=dry)
    if done:
        for line in done:
            print(line)
    else:
        print("  Nothing to purge.")


def cmd_flag(root: Path, args: argparse.Namespace) -> None:
    run_tag = getattr(args, "run_tag", None)
    artifacts = scan_artifacts(root, run_tag)
    manifest_path = do_flag(root, artifacts)
    print(f"\n[calcinator] Manifest written: {manifest_path.relative_to(root)}")
    print(f"  {len(artifacts)} artifact(s) recorded.")


def cmd_clean(root: Path, args: argparse.Namespace) -> None:
    run_tag = getattr(args, "run_tag", None)
    dry = getattr(args, "dry_run", False)
    artifacts = scan_artifacts(root, run_tag)

    print(f"\n[calcinator] clean{' (dry-run)' if dry else ''}")
    if not artifacts:
        print("  ✓ Nothing to clean.")
        return

    print_scan_report(artifacts)
    print()

    archive_done = do_archive(root, artifacts, dry=dry)
    purge_done = do_purge(root, artifacts, dry=dry)

    total = len(archive_done) + len(purge_done)
    tag = "[DRY] " if dry else ""
    print(f"\n  {tag}Archived: {len(archive_done)}  Purged: {len(purge_done)}  Total: {total}")

    # Write manifest of what was flagged (scaffold_solution warnings)
    flagged = [a for a in artifacts if a["action"] == "flag"]
    if flagged and not dry:
        manifest_path = do_flag(root, flagged)
        print(f"  Warnings written to: {manifest_path.relative_to(root)}")


# ---------------------------------------------------------------------------
# Auto-scan hook (called by cog_manager after create)
# ---------------------------------------------------------------------------

def auto_scan(root: Path) -> None:
    """Quick scan called automatically after cog_manager create. Prints warnings only."""
    artifacts = scan_artifacts(root)
    if not artifacts:
        return

    purge_items = [a for a in artifacts if a["action"] == "purge"]
    flag_items = [a for a in artifacts if a["action"] == "flag"]

    if purge_items or flag_items:
        print(f"\n[calcinator] ⚠  {len(purge_items + flag_items)} artifact(s) need attention:")
        for a in purge_items:
            print(f"  🗑  {a['path']}  ({a['reason']})")
        for a in flag_items:
            print(f"  ⚠   {a['path']}  ({a['reason']})")
        print("  Run: python3 agents/calcinator.py scan  (for full report)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description="Calcinator — artifact lifecycle manager for TRANSMUTE-SWARM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  python3 agents/calcinator.py scan                      # show what needs cleaning
  python3 agents/calcinator.py clean --dry-run           # preview full cleanup
  python3 agents/calcinator.py clean                     # archive + purge
  python3 agents/calcinator.py archive --run_tag poc_001 # archive one run's results
  python3 agents/calcinator.py purge  --dry-run          # preview deletions
  python3 agents/calcinator.py flag                      # write manifest only
""",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_common(p):
        p.add_argument("--run_tag", default=None, help="Scope to a specific task/run_tag.")
        p.add_argument("--dry-run", action="store_true", help="Preview actions without making changes.")

    _add_common(sub.add_parser("scan",    help="Dry-run scan — show all stale artifacts."))
    _add_common(sub.add_parser("archive", help="Move completed results/logs to archive."))
    _add_common(sub.add_parser("purge",   help="Delete orphaned cog dirs and solution scaffolds."))
    _add_common(sub.add_parser("flag",    help="Write calcinator_manifest.yaml (no deletions)."))
    _add_common(sub.add_parser("clean",   help="Archive + purge (full cleanup)."))

    args = parser.parse_args()
    dispatch = {
        "scan":    cmd_scan,
        "archive": cmd_archive,
        "purge":   cmd_purge,
        "flag":    cmd_flag,
        "clean":   cmd_clean,
    }
    dispatch[args.command](root, args)


if __name__ == "__main__":
    main()
