#!/usr/bin/env python3
"""
Shell bridge for task_registry.yaml.

Usage (from run_experiment.sh):
    eval "$(python3 scripts/task_config.py "$branch")"

Outputs shell variable assignments:
    metric_name=sort_time_ms
    oracle_command="python3 oracles/evaluate.py --branch sort --mode {mode}"
    oracle_metric_pattern="^sort_time_ms:"
    tsv_header="commit\tsort_time_ms\tmemory_gb\tstatus\tdescription\tlog"
    solution_file=solutions/sort.py

Also used as a Python library:
    from scripts.task_config import load_task_registry, get_task
"""
import sys
from pathlib import Path

import yaml


def _find_registry() -> Path:
    """Locate task_registry.yaml relative to this script (scripts/) or repo root."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "config" / "task_registry.yaml",
        here / "task_registry.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError("task_registry.yaml not found in config/ or scripts/")


def load_task_registry(root: Path | None = None) -> dict:
    """Load and return the tasks dict from task_registry.yaml.

    Returns dict mapping task_id -> task config dict.
    """
    if root is not None:
        path = root / "config" / "task_registry.yaml"
    else:
        path = _find_registry()
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("tasks", {})


def get_task(task_id: str, root: Path | None = None) -> dict:
    """Get config for a single task. Raises KeyError if not found."""
    tasks = load_task_registry(root)
    if task_id not in tasks:
        raise KeyError(
            f"Unknown task '{task_id}'. Registered tasks: {list(tasks.keys())}"
        )
    return tasks[task_id]


def _shell_escape(s: str) -> str:
    """Minimal shell escaping — wrap in double quotes, escape inner quotes."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/task_config.py <task_id>", file=sys.stderr)
        sys.exit(1)

    task_id = sys.argv[1]
    try:
        cfg = get_task(task_id)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Output shell-friendly variable assignments
    print(f"metric_name={_shell_escape(cfg['metric_name'])}")
    print(f"oracle_command={_shell_escape(cfg['oracle_command'])}")
    print(f"oracle_metric_pattern={_shell_escape(cfg['oracle_metric_pattern'])}")
    print(f"tsv_header={_shell_escape(cfg['tsv_header'])}")
    print(f"solution_file={_shell_escape(cfg['solution_file'])}")


if __name__ == "__main__":
    main()
