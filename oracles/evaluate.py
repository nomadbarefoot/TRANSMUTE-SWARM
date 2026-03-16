"""
Fixed oracle harness for TRANSMUTE-SWARM PoC. Do not modify.
Tests branch-owned solution modules and outputs a single scalar (time_ms) for the agent loop.
Usage: python evaluate.py --branch sort|search|filter [--mode quick|full]
Output: grep-parseable lines (<branch>_time_ms:, input_size:, n_runs:).
"""
import argparse
import os
import random
import sys
import timeit
from pathlib import Path

# Fixed constants for reproducible evaluation (tuned for ~5–15s per run)
INPUT_SIZE = 5_000
FULL_N_RUNS = 50
FULL_TIMER_REPEAT = 3
QUICK_N_RUNS = 10
QUICK_TIMER_REPEAT = 1
SEED = 42


def _get_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        val = int(raw)
        return val if val > 0 else default
    except ValueError:
        return default


def _get_solution_module(branch: str):
    """Import the solution module for the given branch."""
    # Solutions live at the TRANSMUTE-SWARM root under solutions/
    root = Path(__file__).resolve().parents[1]
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
    if branch == "filter":
        import importlib.util
        spec = importlib.util.spec_from_file_location("filter_solution", root / "solutions" / "filter.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    raise ValueError(f"Unknown branch: {branch}. Use 'sort', 'search', or 'filter'.")


def _benchmark_sort(n_runs: int, repeat: int):
    random.seed(SEED)
    mod = _get_solution_module("sort")
    arr = [random.randint(0, 10_000) for _ in range(INPUT_SIZE)]

    def run():
        mod.sort(arr.copy())

    times = timeit.repeat(run, number=n_runs, repeat=repeat)
    time_sec = min(times)  # best of repeats
    time_ms = time_sec * 1000
    return time_ms, INPUT_SIZE, n_runs * repeat


def _benchmark_search(n_runs: int, repeat: int):
    random.seed(SEED)
    mod = _get_solution_module("search")
    arr = sorted([random.randint(0, 10_000) for _ in range(INPUT_SIZE)])
    targets = [random.choice(arr) for _ in range(n_runs)]

    def run():
        for t in targets:
            mod.search(arr, t)

    times = timeit.repeat(run, number=1, repeat=repeat)
    time_sec = min(times)
    time_ms = time_sec * 1000
    return time_ms, INPUT_SIZE, n_runs * repeat


def _benchmark_filter(n_runs: int, repeat: int):
    random.seed(SEED)
    mod = _get_solution_module("filter")
    arr = sorted([random.randint(0, 10_000) for _ in range(INPUT_SIZE)])
    thresholds = [random.randint(0, 10_000) for _ in range(n_runs)]

    def run():
        for t in thresholds:
            mod.filter_le(arr, t)

    times = timeit.repeat(run, number=1, repeat=repeat)
    time_sec = min(times)
    time_ms = time_sec * 1000
    return time_ms, INPUT_SIZE, n_runs * repeat


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", required=True, choices=["sort", "search", "filter"])
    parser.add_argument("--mode", choices=["quick", "full"], default="full")
    args = parser.parse_args()
    branch = args.branch
    mode = args.mode

    if mode == "quick":
        n_runs = _get_int_env("ORACLE_QUICK_N_RUNS", QUICK_N_RUNS)
        repeat = _get_int_env("ORACLE_QUICK_REPEAT", QUICK_TIMER_REPEAT)
    else:
        n_runs = _get_int_env("ORACLE_FULL_N_RUNS", FULL_N_RUNS)
        repeat = _get_int_env("ORACLE_FULL_REPEAT", FULL_TIMER_REPEAT)

    try:
        if branch == "sort":
            time_ms, input_size, n_runs = _benchmark_sort(n_runs, repeat)
            metric_name = "sort_time_ms"
        elif branch == "search":
            time_ms, input_size, n_runs = _benchmark_search(n_runs, repeat)
            metric_name = "search_time_ms"
        else:
            time_ms, input_size, n_runs = _benchmark_filter(n_runs, repeat)
            metric_name = "filter_time_ms"
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)

    print("---")
    print(f"{metric_name}:  {time_ms:.2f}")
    print(f"input_size:    {input_size}")
    print(f"n_runs:        {n_runs}")


if __name__ == "__main__":
    main()
