"""
Fixed composite oracle for TRANSMUTE-SWARM PoC. Do not modify.
Runs all branch oracles and outputs weighted composite time (lower is better).
Usage: python evaluate_composite.py
Output: grep-parseable lines (composite_ms, sort_time_ms, search_time_ms, filter_time_ms, weights).
"""
import subprocess
import sys
from pathlib import Path

# Weights from decomposition.yaml (must match)
SORT_WEIGHT = 1.0 / 3
SEARCH_WEIGHT = 1.0 / 3
FILTER_WEIGHT = 1.0 / 3


def run_oracle(branch: str) -> float:
    """Run evaluate.py for one branch and return time_ms."""
    # Oracles live under TRANSMUTE-SWARM/oracles/, solutions under TRANSMUTE-SWARM/solutions/
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "oracles" / "evaluate.py"), "--branch", branch],
        capture_output=True,
        text=True,
        cwd=root,
        timeout=300,
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
    filter_ms = run_oracle("filter")
    composite_ms = SORT_WEIGHT * sort_ms + SEARCH_WEIGHT * search_ms + FILTER_WEIGHT * filter_ms

    print("---")
    print(f"composite_ms:     {composite_ms:.2f}")
    print(f"sort_time_ms:     {sort_ms:.2f}")
    print(f"search_time_ms:   {search_ms:.2f}")
    print(f"filter_time_ms:   {filter_ms:.2f}")
    print(f"sort_weight:      {SORT_WEIGHT}")
    print(f"search_weight:    {SEARCH_WEIGHT}")
    print(f"filter_weight:    {FILTER_WEIGHT}")


if __name__ == "__main__":
    main()

