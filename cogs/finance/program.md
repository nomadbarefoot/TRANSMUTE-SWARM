# Branch: finance (TRANSMUTE-SWARM)

You are the finance-branch agent.

## Scope
- **You own only** `solutions/finance_ma.py`.
- **Do not modify** any oracle or data files.
- Use only the Python standard library.

## Goal
Minimize `finance_sharpe_neg` (lower is better). This is **negative Sharpe** of the MA strategy on NIFTY50 3‑month daily data.

## Execution (single-call only)
- **Baseline first** (no edits):
  `bash run_experiment.sh --branch finance --solution-path solutions/finance_ma.py --mode baseline --description "baseline" --log "baseline"`
- **Iterations**: make one edit and run **one** command that ends with `run_experiment.sh`.
  Use `--mode quick`; the script auto-runs full when quick improves.

Example single-call edit + run:
```bash
cat > solutions/finance_ma.py <<'PY'
# ...new implementation...
PY
bash run_experiment.sh --branch finance --solution-path solutions/finance_ma.py --mode quick --description "Tune MA windows" --log "Adjusted short/long windows."
```

## Ideas
- Tune short/long windows (short in [3..20], long in [20..120]).
- Adjust RSI period and ceiling/floor; consider removing RSI if it blocks entries.
- Avoid lookahead; signals must be causal.

## Rules
- Do **not** call `evaluate_finance.py` directly.
- Do **not** touch data under `data/`.
- `run_experiment.sh` handles git + results.
- After iterations, reply `DONE` and summarize best metric + key change.
