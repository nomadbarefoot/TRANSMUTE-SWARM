# Branch: sort (TRANSMUTE-SWARM)

You are the sort-branch agent.

## Scope
- **You own only** `solutions/sort.py`.
- **Do not modify**: `oracles/evaluate.py`, `oracles/evaluate_composite.py`, or other solution files.
- Use only the Python standard library.

## Goal
Minimize `sort_time_ms` (lower is better). Contract:
`def sort(arr: list) -> list` returns a sorted list.

## Execution (single-call only)
- **Baseline first** (no edits):
  `bash run_experiment.sh --branch sort --solution-path solutions/sort.py --mode baseline --description "baseline" --log "baseline"`
- **Iterations**: make one edit and run **one** command that ends with `run_experiment.sh`.
  Use `--mode quick`; the script auto-runs full when quick improves.

Example single-call edit + run:
```bash
cat > solutions/sort.py <<'PY'
# ...new implementation...
PY
bash run_experiment.sh --branch sort --solution-path solutions/sort.py --mode quick --description "Use list.sort" --log "Switched to in-place list.sort()."
```

## Ideas
- Prefer Python’s built-in `list.sort()` or `sorted()`.
- Avoid extra allocations if not needed.

## Rules
- Do **not** call `evaluate.py`, `git commit/reset/checkout`, or write TSVs directly.
- `run_experiment.sh` handles git + results.
- After iterations, reply `DONE` and summarize best metric + key change.
