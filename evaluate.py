"""
Fixed oracle harness for TRANSMUTE-SWARM PoC. Do not modify.
Tests branch-owned solution modules and outputs a single scalar (time_ms) for the agent loop.
Usage: python evaluate.py --branch sort|search
Output: grep-parseable lines (sort_time_ms: or search_time_ms:, input_size:, n_runs:).
"""
import argparse
import random
import sys
import timeit
from pathlib import Path

# Fixed constants for reproducible evaluation (tuned for ~5–15s per run)
INPUT_SIZE = 5_000
N_RUNS = 50
TIMER_REPEAT = 3
SEED = 42


def _get_solution_module(branch: str):
    """Import the solution module for the given branch."""
    root = Path(__file__).resolve().parent
    if branch == "sort":
        import importlib.util
        spec = importlib.util.spec_from_file_location("sort_solution", root / "solutions" / "sort.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    if branch == "search":
        import importlib.util
        spec = importlib.util.spec_from_file_location("search_solution", root / "solutions" / "search.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    raise ValueError(f"Unknown branch: {branch}. Use 'sort' or 'search'.")


def _benchmark_sort():
    random.seed(SEED)
    mod = _get_solution_module("sort")
    arr = [random.randint(0, 10_000) for _ in range(INPUT_SIZE)]
    def run():
        mod.sort(arr.copy())
    times = timeit.repeat(run, number=N_RUNS, repeat=TIMER_REPEAT)
    time_sec = min(times)  # best of repeats
    time_ms = time_sec * 1000
    return time_ms, INPUT_SIZE, N_RUNS * TIMER_REPEAT


def _benchmark_search():
    random.seed(SEED)
    mod = _get_solution_module("search")
    arr = sorted([random.randint(0, 10_000) for _ in range(INPUT_SIZE)])
    targets = [random.choice(arr) for _ in range(N_RUNS)]
    def run():
        for t in targets:
            mod.search(arr, t)
    times = timeit.repeat(run, number=1, repeat=TIMER_REPEAT)
    time_sec = min(times)
    time_ms = time_sec * 1000
    return time_ms, INPUT_SIZE, N_RUNS * TIMER_REPEAT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", required=True, choices=["sort", "search"])
    args = parser.parse_args()
    branch = args.branch

    try:
        if branch == "sort":
            time_ms, input_size, n_runs = _benchmark_sort()
            metric_name = "sort_time_ms"
        else:
            time_ms, input_size, n_runs = _benchmark_search()
            metric_name = "search_time_ms"
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)

    print("---")
    print(f"{metric_name}:  {time_ms:.2f}")
    print(f"input_size:    {input_size}")
    print(f"n_runs:        {n_runs}")


if __name__ == "__main__":
    main()
