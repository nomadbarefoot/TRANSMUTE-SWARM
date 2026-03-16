"""
Helper to append a single TSV row to a branch results file.

Usage:
    python append_tsv.py <branch_id> <commit> <metric_value> <memory_gb> <status> <description> <log>

This script:
- Ensures the correct header exists for the given branch.
- Appends one tab-separated row.
"""
import sys
from pathlib import Path


HEADERS = {
    "sort": "commit\tsort_time_ms\tmemory_gb\tstatus\tdescription\tlog\n",
    "search": "commit\tsearch_time_ms\tmemory_gb\tstatus\tdescription\tlog\n",
    "filter": "commit\tfilter_time_ms\tmemory_gb\tstatus\tdescription\tlog\n",
}


def main() -> None:
    if len(sys.argv) != 8:
        raise SystemExit(
            "Usage: python append_tsv.py <branch_id> <commit> <metric_value> "
            "<memory_gb> <status> <description> <log>"
        )

    branch_id, commit, metric_value, memory_gb, status, description, log = sys.argv[1:]
    header = HEADERS.get(branch_id)
    if header is None:
        raise SystemExit(f"Unknown branch_id '{branch_id}'. Expected one of: sort, search, filter.")

    # Use TRANSMUTE-SWARM root (parent of scripts/) for results paths.
    root = Path(__file__).resolve().parents[1]
    results_dir = root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"results_{branch_id}.tsv"

    # Create file with header if missing or empty.
    if not path.exists() or path.stat().st_size == 0:
        path.write_text(header)

    # Tabs are schema delimiters; replace any in description/log with spaces.
    description = description.replace("\t", " ")
    log = log.replace("\t", " ")

    with path.open("a") as f:
        f.write(
            f"{commit}\t{metric_value}\t{memory_gb}\t{status}\t{description}\t{log}\n"
        )


if __name__ == "__main__":
    main()
