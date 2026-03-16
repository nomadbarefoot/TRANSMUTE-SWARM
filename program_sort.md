# Branch: sort (TRANSMUTE-SWARM)

This is an experiment to improve the sorting implementation. You are the sort-branch agent.

## Setup

1. **Branch**: You run on `swarm/<run_tag>/sort`. The run_tag is provided to you (e.g. `poc_001`).
2. **Read the in-scope files**:
   - `evaluate.py` — fixed oracle harness. Do not modify.
   - `evaluate_composite.py` — fixed composite oracle. Do not modify.
   - `solutions/sort.py` — the **only file you modify**. Contains the sorting implementation.
3. **Do NOT touch**: `evaluate.py`, `evaluate_composite.py`, `solutions/search.py`, or any other file.
4. **Initialize results_sort.tsv**: Create `results_sort.tsv` with just the header row. The baseline will be recorded after the first run.
5. **Read** `discoveries/shared_context.md` at the start if it exists.

Once setup is done, kick off the experimentation.

## Experimentation

**What you CAN do:**
- Modify `solutions/sort.py` only. Change the algorithm (e.g. quicksort, mergesort, better bubble), data structures, or implementation details. The contract is: `def sort(arr: list) -> list` must sort the list and return it.

**What you CANNOT do:**
- Modify `evaluate.py` or `evaluate_composite.py`.
- Modify `solutions/search.py`.
- Install new packages. Use only the Python standard library.

**The goal is simple: get the lowest sort_time_ms.** Lower is better. The oracle runs a fixed benchmark (fixed seed, fixed input size) and reports `sort_time_ms`.

**Simplicity criterion**: All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it.

**The first run**: Your very first run should always be to establish the baseline: run the oracle as-is without changing `solutions/sort.py`.

## Output format

The oracle prints:

```
---
sort_time_ms:  4521.33
input_size:    5000
n_runs:        150
```

Extract the key metric:

```
grep "^sort_time_ms:" run.log
```

## Logging results

Log each experiment to `results_sort.tsv` (tab-separated). Do not commit this file; leave it untracked.

The TSV has a header row and 5 columns:

```
commit	sort_time_ms	memory_gb	status	description
```

1. git commit hash (short, 7 chars)
2. sort_time_ms achieved (e.g. 1234.56) — use 0.0 for crashes
3. memory_gb: use 0.0 (not applicable for this PoC)
4. status: `keep`, `discard`, or `crash`
5. short text description of what this experiment tried

## The experiment loop

LOOP for the number of iterations you are told (e.g. 20), or until you are stopped:

1. Look at the git state: current branch and commit.
2. Modify `solutions/sort.py` with an experimental idea.
3. git add solutions/sort.py && git commit -m "<short description>"
4. Run the oracle: `python3 evaluate.py --branch sort > run.log 2>&1` (redirect everything; do NOT use tee).
5. Read the result: `grep "^sort_time_ms:" run.log`
6. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to see the error. Fix if trivial (typo, import); otherwise log "crash" and revert.
7. Record the results in results_sort.tsv (do not commit results_sort.tsv).
8. If sort_time_ms improved (lower), keep the commit and advance.
9. If sort_time_ms is equal or worse, run `git reset --hard HEAD~1` to discard.

**Timeout**: If a run exceeds 2 minutes, treat as failure (discard and revert).

**Crashes**: If something dumb (typo, import), fix and re-run. If the idea is broken, log "crash" and move on.

**NEVER STOP**: Do not ask the human if you should continue. Run the requested number of iterations autonomously. If you run out of ideas, try different algorithms (quicksort, mergesort, heapsort, etc.) or optimizations.

Write significant findings (e.g. which change gave the biggest gain) to `discoveries/sort.md` when you have something useful to share.
