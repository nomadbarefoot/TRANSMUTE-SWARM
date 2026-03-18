# Branch: finance (TRANSMUTE-SWARM)

You are the finance-branch agent.

## Scope
- **You own only** `solutions/finance_ma.py`.
- **Do not modify** any oracle or data files.
- Use only the Python standard library.

## Goal
Minimize `finance_sharpe_neg` (lower is better). This is **negative Sharpe** of the MA strategy on NIFTY50 3-month daily data.
Contract: `def compute_signal(prices: list[float]) -> list[float]`

## Execution
- **Baseline first** — call `experiment` with mode='baseline' (no code change).
- **Iterate** — use `experiment` with mode='quick'; the system auto-promotes to full when quick improves.
- Use `read_file` and `explore` freely for reconnaissance.

## Ideas
- Tune short/long windows (short in [3..20], long in [20..120]).
- Adjust RSI period and ceiling/floor; consider removing RSI if it blocks entries.
- Avoid lookahead; signals must be causal.

## Rules
- Do **not** call oracle scripts, git commands, or write TSVs directly.
- Do **not** touch data under `data/`.
- `run_experiment.sh` handles git + results (called internally by the `experiment` tool).
- After iterations, reply `DONE` and summarize best metric + key change.
