# Branch: search (TRANSMUTE-SWARM)

You are the search-branch agent.

## Scope
- **You own only** `solutions/search.py`.
- **Do not modify**: `oracles/evaluate.py`, `oracles/evaluate_composite.py`, or other solution files.
- Use only the Python standard library.

## Goal
Minimize `search_time_ms` (lower is better). `arr` is **sorted**. Contract:
`def search(arr: list, target: int) -> int` returns index or -1.

## Execution (single-call only)
- **Baseline first** (no edits):
  `bash run_experiment.sh --branch search --solution-path solutions/search.py --mode baseline --description "baseline" --log "baseline"`
- **Iterations**: make one edit and run **one** command that ends with `run_experiment.sh`.
  Use `--mode quick`; the script auto-runs full when quick improves.

Example single-call edit + run:
```bash
cat > solutions/search.py <<'PY'
# ...new implementation...
PY
bash run_experiment.sh --branch search --solution-path solutions/search.py --mode quick --description "Tried binary search" --log "Used binary search on sorted input."
```

## Ideas
- Binary search (O(log n)) is the obvious win.
- Handle not-found correctly.

## Rules
- Do **not** call `evaluate.py`, `git commit/reset/checkout`, or write TSVs directly.
- `run_experiment.sh` handles git + results.
- After iterations, reply `DONE` and summarize best metric + key change.
