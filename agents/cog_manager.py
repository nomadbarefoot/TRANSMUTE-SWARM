"""
Cog branch lifecycle manager for TRANSMUTE-SWARM.

A "Cog" is a branch agent instance — one Cog per task per run.

Branch naming convention:
  cogs/<run_tag>/<cog_id>
  e.g. cogs/poc_001/sort, cogs/poc_002/finance

Commands:
  create  --run_tag <tag> --cog_ids <id,id,...>   Create Cog branches from main
  list    [--run_tag <tag>]                        List Cog branches (local + remote)
  status  --run_tag <tag>                          Show per-Cog result summary
  cleanup --run_tag <tag> [--remote] [--dry-run]  Delete Cog branches for a completed run
  purge   --older-than-days <n> [--remote] [--dry-run]  Delete Cog branches older than N days
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


COG_PREFIX = "cogs"


def run(cwd: Path, *cmd, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True, check=check)


def cog_branch(run_tag: str, cog_id: str) -> str:
    return f"{COG_PREFIX}/{run_tag}/{cog_id}"


def list_cog_branches(root: Path, run_tag: str | None = None, include_remote: bool = True) -> list[dict]:
    """Return list of dicts with keys: name, remote, run_tag, cog_id."""
    run(root, "git", "fetch", "--prune", "origin", check=False)

    branches = []
    pattern = f"{COG_PREFIX}/{run_tag}/" if run_tag else f"{COG_PREFIX}/"

    # Local branches
    r = run(root, "git", "branch", "--format=%(refname:short)")
    for name in r.stdout.splitlines():
        name = name.strip()
        if name.startswith(pattern):
            parts = name.split("/")
            if len(parts) == 3:
                branches.append({"name": name, "remote": False, "run_tag": parts[1], "cog_id": parts[2]})

    # Remote branches
    if include_remote:
        r = run(root, "git", "branch", "-r", "--format=%(refname:short)")
        for name in r.stdout.splitlines():
            name = name.strip().removeprefix("origin/")
            if name.startswith(pattern):
                parts = name.split("/")
                if len(parts) == 3:
                    # Skip if already in local list
                    if not any(b["name"] == name for b in branches):
                        branches.append({"name": name, "remote": True, "run_tag": parts[1], "cog_id": parts[2]})

    return branches


def branch_age_days(root: Path, branch_name: str, remote: bool = False) -> float | None:
    """Return age of branch tip in days, or None if unavailable."""
    ref = f"origin/{branch_name}" if remote else branch_name
    r = run(root, "git", "log", "-1", "--format=%ct", ref, check=False)
    ts = r.stdout.strip()
    if not ts:
        return None
    try:
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(int(ts), tz=timezone.utc)
        return age.total_seconds() / 86400
    except ValueError:
        return None


def _load_metric_cols(root: Path) -> dict:
    """Load metric column names from task registry, fallback to hardcoded."""
    _fallback = {"sort": "sort_time_ms", "search": "search_time_ms", "filter": "filter_time_ms", "finance": "finance_sharpe_neg"}
    registry_path = root / "config" / "task_registry.yaml"
    if registry_path.exists():
        try:
            import yaml
            with open(registry_path) as f:
                data = yaml.safe_load(f) or {}
            result = dict(_fallback)
            for tid, tcfg in data.get("tasks", {}).items():
                result[tid] = tcfg.get("metric_name", f"{tid}_metric")
            return result
        except Exception:
            pass
    return _fallback


def load_cog_status(root: Path, run_tag: str, cog_ids: list[str]) -> list[dict]:
    """Load best keep result per Cog from results TSVs."""
    metric_cols = _load_metric_cols(root)
    rows = []
    for cog_id in cog_ids:
        metric_col = metric_cols.get(cog_id, f"{cog_id}_metric")
        tsv = root / "results" / f"results_{cog_id}.tsv"
        best_metric = None
        best_desc = "-"
        n_keep = 0
        n_total = 0
        if tsv.exists():
            import csv
            try:
                with open(tsv) as f:
                    reader = csv.DictReader(f, delimiter="\t")
                    for row in reader:
                        n_total += 1
                        if row.get("status", "").lower() == "keep":
                            n_keep += 1
                            try:
                                val = float(row.get(metric_col, "inf"))
                                if best_metric is None or val < best_metric:
                                    best_metric = val
                                    best_desc = row.get("description", "-")[:40]
                            except (ValueError, TypeError):
                                pass
            except Exception:
                pass
        rows.append({
            "cog_id": cog_id,
            "metric_col": metric_col,
            "best": best_metric,
            "best_desc": best_desc,
            "n_keep": n_keep,
            "n_total": n_total,
        })
    return rows


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_create(root: Path, args: argparse.Namespace) -> None:
    cog_ids = [c.strip() for c in args.cog_ids.split(",") if c.strip()]
    if not cog_ids:
        print("ERROR: --cog_ids must list at least one cog id.", file=sys.stderr)
        sys.exit(1)

    run(root, "git", "fetch", "origin", "main", check=False)
    created = []
    skipped = []
    for cog_id in cog_ids:
        branch = cog_branch(args.run_tag, cog_id)
        # Check if already exists locally or remotely
        r_local = run(root, "git", "rev-parse", "--verify", branch, check=False)
        r_remote = run(root, "git", "rev-parse", "--verify", f"origin/{branch}", check=False)
        if r_local.returncode == 0 or r_remote.returncode == 0:
            print(f"  skip  {branch}  (already exists)")
            skipped.append(branch)
            continue

        r = run(root, "git", "checkout", "-b", branch, "main", check=False)
        if r.returncode != 0:
            # Try origin/main
            r = run(root, "git", "checkout", "-b", branch, "origin/main", check=False)
        if r.returncode != 0:
            print(f"  ERROR creating {branch}: {r.stderr.strip()}", file=sys.stderr)
            continue

        if args.push:
            rp = run(root, "git", "push", "-u", "origin", branch, check=False)
            status = "created+pushed" if rp.returncode == 0 else "created (push failed)"
        else:
            status = "created (local)"

        # Return to main
        run(root, "git", "checkout", "main", check=False)
        print(f"  {status}  {branch}")
        created.append(branch)

    print(f"\nCogs created: {len(created)}  skipped: {len(skipped)}")

    # Auto-scan for stale artifacts after branch creation
    if created:
        try:
            from agents.calcinator import auto_scan
            auto_scan(root)
        except Exception:
            pass


def cmd_list(root: Path, args: argparse.Namespace) -> None:
    run_tag = getattr(args, "run_tag", None)
    branches = list_cog_branches(root, run_tag)
    if not branches:
        print(f"No Cog branches found{' for run_tag=' + run_tag if run_tag else ''}.")
        return

    # Group by run_tag
    by_run: dict[str, list] = {}
    for b in branches:
        by_run.setdefault(b["run_tag"], []).append(b)

    for rt, blist in sorted(by_run.items()):
        print(f"\nrun_tag: {rt}")
        for b in sorted(blist, key=lambda x: x["cog_id"]):
            loc = "remote" if b["remote"] else "local "
            age = branch_age_days(root, b["name"], b["remote"])
            age_str = f"{age:.1f}d ago" if age is not None else "unknown age"
            print(f"  [{loc}]  {b['name']}  ({age_str})")


def cmd_status(root: Path, args: argparse.Namespace) -> None:
    branches = list_cog_branches(root, args.run_tag)
    cog_ids = sorted({b["cog_id"] for b in branches})
    if not cog_ids:
        print(f"No Cog branches found for run_tag={args.run_tag}.")
        return

    rows = load_cog_status(root, args.run_tag, cog_ids)
    print(f"\nCog status — run_tag: {args.run_tag}")
    print(f"{'cog_id':<12} {'metric':<22} {'best':>10}  {'keep/total':>10}  description")
    print("-" * 80)
    for row in rows:
        best = f"{row['best']:.4f}" if row["best"] is not None else "no data"
        print(f"  {row['cog_id']:<10} {row['metric_col']:<22} {best:>10}  "
              f"{row['n_keep']:>4}/{row['n_total']:<4}  {row['best_desc']}")


def cmd_cleanup(root: Path, args: argparse.Namespace) -> None:
    branches = list_cog_branches(root, args.run_tag)
    if not branches:
        print(f"No Cog branches found for run_tag={args.run_tag}.")
        return

    dry = args.dry_run
    tag = "[DRY RUN] " if dry else ""
    deleted_local = 0
    deleted_remote = 0

    for b in branches:
        branch = b["name"]
        if not b["remote"]:
            print(f"  {tag}delete local  {branch}")
            if not dry:
                run(root, "git", "branch", "-D", branch, check=False)
            deleted_local += 1
        elif args.remote:
            print(f"  {tag}delete remote {branch}")
            if not dry:
                run(root, "git", "push", "origin", "--delete", branch, check=False)
            deleted_remote += 1

    print(f"\n{tag}local={deleted_local} remote={deleted_remote} (pass --remote to also delete remote branches)")


def cmd_purge(root: Path, args: argparse.Namespace) -> None:
    branches = list_cog_branches(root)
    cutoff_days = args.older_than_days
    dry = args.dry_run
    tag = "[DRY RUN] " if dry else ""
    count = 0

    for b in branches:
        age = branch_age_days(root, b["name"], b["remote"])
        if age is None or age < cutoff_days:
            continue
        action = "remote" if b["remote"] else "local "
        print(f"  {tag}delete {action}  {b['name']}  ({age:.1f}d old)")
        if not dry:
            if b["remote"]:
                if args.remote:
                    run(root, "git", "push", "origin", "--delete", b["name"], check=False)
            else:
                run(root, "git", "branch", "-D", b["name"], check=False)
        count += 1

    if count == 0:
        print(f"No Cog branches older than {cutoff_days} days.")
    else:
        print(f"\n{tag}Processed {count} branches older than {cutoff_days} days.")
        if not args.remote:
            print("  (remote branches skipped — pass --remote to include them)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description="Cog branch lifecycle manager for TRANSMUTE-SWARM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python3 agents/cog_manager.py create  --run_tag poc_002 --cog_ids sort,search,filter
  python3 agents/cog_manager.py create  --run_tag poc_002 --cog_ids finance --push
  python3 agents/cog_manager.py list
  python3 agents/cog_manager.py list    --run_tag poc_002
  python3 agents/cog_manager.py status  --run_tag poc_002
  python3 agents/cog_manager.py cleanup --run_tag poc_001 --dry-run
  python3 agents/cog_manager.py cleanup --run_tag poc_001 --remote
  python3 agents/cog_manager.py purge   --older-than-days 7 --dry-run
""",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="Create Cog branches from main.")
    p_create.add_argument("--run_tag", required=True)
    p_create.add_argument("--cog_ids", required=True, help="Comma-separated Cog IDs, e.g. sort,search")
    p_create.add_argument("--push", action="store_true", help="Push branches to origin after creating.")

    # list
    p_list = sub.add_parser("list", help="List Cog branches.")
    p_list.add_argument("--run_tag", default=None, help="Filter by run_tag.")

    # status
    p_status = sub.add_parser("status", help="Show per-Cog result summary for a run.")
    p_status.add_argument("--run_tag", required=True)

    # cleanup
    p_cleanup = sub.add_parser("cleanup", help="Delete Cog branches for a completed run.")
    p_cleanup.add_argument("--run_tag", required=True)
    p_cleanup.add_argument("--remote", action="store_true", help="Also delete remote branches.")
    p_cleanup.add_argument("--dry-run", action="store_true", help="Print what would be deleted without deleting.")

    # purge
    p_purge = sub.add_parser("purge", help="Delete all Cog branches older than N days.")
    p_purge.add_argument("--older-than-days", type=float, required=True, dest="older_than_days")
    p_purge.add_argument("--remote", action="store_true", help="Also delete remote branches.")
    p_purge.add_argument("--dry-run", action="store_true", help="Print what would be deleted without deleting.")

    args = parser.parse_args()
    dispatch = {
        "create": cmd_create,
        "list": cmd_list,
        "status": cmd_status,
        "cleanup": cmd_cleanup,
        "purge": cmd_purge,
    }
    dispatch[args.command](root, args)


if __name__ == "__main__":
    main()
