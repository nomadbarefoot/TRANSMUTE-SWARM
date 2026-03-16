"""
Fixed composite oracle for TRANSMUTE-SWARM PoC. Do not modify.
Runs both branch oracles and outputs weighted composite time (lower is better).
Usage: python evaluate_composite.py
Output: grep-parseable lines (composite_ms, sort_time_ms, search_time_ms, weights).
"""
import subprocess
import sys
from pathlib import Path

# Weights from decomposition.yaml (must match)
SORT_WEIGHT = 0.5
SEARCH_WEIGHT = 0.5


def run_oracle(branch: str) -> float:
    """Run evaluate.py for one branch and return time_ms."""
    root = Path(__file__).resolve().parent
    result = subprocess.run(
        [sys.executable, str(root / "evaluate.py"), "--branch", branch],
        capture_output=True,
        text=True,
        cwd=root,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"evaluate.py --branch {branch} failed: {result.stderr}")
    time_ms = None
    for line in result.stdout.splitlines():
        if line.startswith(f"{branch}_time_ms:"):
            time_ms = float(line.split(":", 1)[1].strip())
            break
    if time_ms is None:
        raise RuntimeError(f"Could not parse {branch}_time_ms from output")
    return time_ms


def main():
    sort_ms = run_oracle("sort")
    search_ms = run_oracle("search")
    composite_ms = SORT_WEIGHT * sort_ms + SEARCH_WEIGHT * search_ms

    print("---")
    print(f"composite_ms:     {composite_ms:.2f}")
    print(f"sort_time_ms:     {sort_ms:.2f}")
    print(f"search_time_ms:   {search_ms:.2f}")
    print(f"sort_weight:      {SORT_WEIGHT}")
    print(f"search_weight:    {SEARCH_WEIGHT}")


if __name__ == "__main__":
    main()
