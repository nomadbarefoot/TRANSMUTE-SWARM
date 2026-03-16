"""
Phase 1 deterministic coordinator for TRANSMUTE-SWARM.
Reads results TSVs per branch, finds best commit per branch, cherry-picks to integration branch,
runs composite oracle, runs ablation, writes coordinator_report_<cycle>.md.
No LLM. Human runs this after branches complete.
Expects results_<branch_id>.tsv under results/ (or --results_dir) with columns: commit, <metric>, memory_gb, status, description.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone


def run(cwd: Path, *cmd, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_tag", default="poc_001")
    parser.add_argument("--branch_ids", nargs="+", default=["sort", "search", "filter"])
    parser.add_argument("--results_dir", type=Path, default=None, help="Directory containing results_*.tsv (default: TRANSMUTE-SWARM results/)")
    parser.add_argument("--cycle", type=int, default=1)
    args = parser.parse_args()

    # Use TRANSMUTE-SWARM root (parent of agents/) as the working root
    root = Path(__file__).resolve().parents[1]
    results_dir = args.results_dir or (root / "results")
    run_tag = args.run_tag
    branch_ids = args.branch_ids
    cycle = args.cycle

    # 1. Read results TSVs and find best keep commit per branch
    metric_key = {"sort": "sort_time_ms", "search": "search_time_ms", "filter": "filter_time_ms"}
    best = {}  # branch_id -> (commit, metric_value)
    for bid in branch_ids:
        tsv = results_dir / f"results_{bid}.tsv"
        if not tsv.exists():
            print(f"WARNING: {tsv} not found; skipping branch {bid}", file=sys.stderr)
            continue
        lines = tsv.read_text().strip().splitlines()
        if not lines:
            continue
        header = lines[0].split("\t")
        try:
            metric_col = header.index(metric_key.get(bid, f"{bid}_time_ms"))
        except ValueError:
            metric_col = 1
        status_col = header.index("status") if "status" in header else 3
        commit_col = header.index("commit") if "commit" in header else 0
        best_metric = None
        best_commit = None
        lower_better = True
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) <= max(metric_col, status_col, commit_col):
                continue
            if parts[status_col].strip().lower() != "keep":
                continue
            try:
                val = float(parts[metric_col].strip())
            except ValueError:
                continue
            if best_metric is None or (val < best_metric if lower_better else val > best_metric):
                best_metric = val
                raw = parts[commit_col].strip()
                # Strip shell-artifact prefixes (e.g. echo -e producing "-e 2b1e346")
                if raw.startswith("-e "):
                    raw = raw[3:].strip()
                # Take first 7 chars (short hash) or extract first 7-char hex if embedded
                hex_match = re.search(r"[0-9a-fA-F]{7,}", raw)
                best_commit = (hex_match.group(0)[:7] if hex_match else raw[:7]).strip()
        if best_commit and best_metric is not None:
            best[bid] = (best_commit, best_metric)

    if not best:
        print("No best commits found in any results TSV. Exiting.", file=sys.stderr)
        sys.exit(1)

    # 2. Fetch swarm branches so we have the commits, then create integration branch
    run(root, "git", "fetch", "origin", check=False)
    for bid in branch_ids:
        run(root, "git", "fetch", "origin", f"swarm/{run_tag}/{bid}", check=False)
    run(root, "git", "checkout", "main", check=False)
    run(root, "git", "pull", "origin", "main", check=False)
    int_branch = f"integration/{run_tag}"
    run(root, "git", "branch", "-D", int_branch, check=False)
    run(root, "git", "checkout", "-b", int_branch)

    composite_before_abl = None
    try:
        for bid in branch_ids:
            if bid not in best:
                continue
            commit, _ = best[bid]
            r = run(root, "git", "cherry-pick", commit, check=False)
            if r.returncode != 0:
                run(root, "git", "cherry-pick", "--abort", check=False)
                print(f"WARNING: cherry-pick {commit} (branch {bid}) failed; skipping.", file=sys.stderr)
                continue

        # 3. Run composite oracle (now lives under oracles/)
        r = run(root, sys.executable, str(root / "oracles" / "evaluate_composite.py"), check=False)
        if r.returncode != 0:
            composite_before_abl = None
            print("WARNING: composite oracle failed.", file=sys.stderr)
        else:
            for line in r.stdout.splitlines():
                if line.startswith("composite_ms:"):
                    composite_before_abl = float(line.split(":", 1)[1].strip())
                    break
    except Exception as e:
        print(f"Integration step failed: {e}", file=sys.stderr)

    # 4. Ablation: for each branch, composite without that branch (main + other cherry-picks)
    marginal = {}
    for omit_bid in branch_ids:
        if omit_bid not in best:
            marginal[omit_bid] = None
            continue
        try:
            run(root, "git", "checkout", "main", check=False)
            run(root, "git", "branch", "-D", "_abl_temp", check=False)
            r = run(root, "git", "checkout", "-b", "_abl_temp", check=False)
            if r.returncode != 0:
                marginal[omit_bid] = None
                continue
            for bid in branch_ids:
                if bid == omit_bid or bid not in best:
                    continue
                commit, _ = best[bid]
                run(root, "git", "cherry-pick", commit, check=False)
            r = run(root, sys.executable, str(root / "oracles" / "evaluate_composite.py"), check=False)
            composite_without = None
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    if line.startswith("composite_ms:"):
                        composite_without = float(line.split(":", 1)[1].strip())
                        break
            if composite_before_abl is not None and composite_without is not None:
                # Lower is better: removing a helpful branch worsens composite (higher).
                # So composite_without > composite_before_abl when branch helped → marginal positive.
                marginal[omit_bid] = composite_without - composite_before_abl  # positive = branch helped
            else:
                marginal[omit_bid] = None
        except Exception:
            marginal[omit_bid] = None
        finally:
            run(root, "git", "checkout", int_branch, check=False)
            run(root, "git", "branch", "-D", "_abl_temp", check=False)

    # 5. Write report (into TRANSMUTE-SWARM root; later docs step will move/rename if desired)
    report_path = root / f"coordinator_report_{cycle}.md"
    lines = [
        f"# Coordinator Report — Cycle {cycle}, Run: {run_tag}",
        f"# Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "## Best commits per branch",
        "| Branch | Commit | Metric value |",
        "|--------|--------|--------------|",
    ]
    for bid in branch_ids:
        if bid in best:
            c, v = best[bid]
            lines.append(f"| {bid} | {c} | {v} |")
    lines.extend(["", "## Composite metric", ""])
    if composite_before_abl is not None:
        lines.append(f"Composite (all branches): {composite_before_abl:.2f} ms (lower is better)")
    else:
        lines.append("Composite: (run failed or not computed)")
    lines.extend(["", "## Marginal contribution (ablation)", ""])
    lines.append("| Branch | Marginal (ms) | Interpretation |")
    lines.append("|--------|----------------|----------------|")
    for bid in branch_ids:
        m = marginal.get(bid)
        if m is None:
            lines.append(f"| {bid} | - | not computed |")
        elif m > 0:
            lines.append(f"| {bid} | +{m:.2f} | positive (branch helps) |")
        else:
            lines.append(f"| {bid} | {m:.2f} | negative or neutral |")
    lines.extend(["", "## Items requiring human review", ""])
    lines.append("(None or add notes here.)")
    report_path.write_text("\n".join(lines))
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
