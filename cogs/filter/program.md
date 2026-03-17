# Branch: filter (TRANSMUTE-SWARM)

You are the filter-branch agent.

## Scope
- **You own only** `solutions/filter.py`.
- **Do not modify**: `oracles/evaluate.py`, `oracles/evaluate_composite.py`, or other solution files.
- Use only the Python standard library.

## Goal
Minimize `filter_time_ms` (lower is better). Contract:
`def filter_le(arr: list, threshold: int) -> list` returns all values <= threshold.

## Execution (single-call only)
- **Baseline first** (no edits):
  `bash run_experiment.sh --branch filter --solution-path solutions/filter.py --mode baseline --description "baseline" --log "baseline"`
- **Iterations**: make one edit and run **one** command that ends with `run_experiment.sh`.
  Use `--mode quick`; the script auto-runs full when quick improves.

Example single-call edit + run:
```bash
cat > solutions/filter.py <<'PY'
# ...new implementation...
PY
bash run_experiment.sh --branch filter --solution-path solutions/filter.py --mode quick --description "Single-pass append" --log "Single-pass loop appending matches."
```

## Ideas
- Single-pass loop with append is usually fastest.
- Avoid repeated scans or quadratic behavior.

## Rules
- Do **not** call `evaluate.py`, `git commit/reset/checkout`, or write TSVs directly.
- `run_experiment.sh` handles git + results.
- After iterations, reply `DONE` and summarize best metric + key change.
