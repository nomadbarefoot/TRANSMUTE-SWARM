# Branch: search (TRANSMUTE-SWARM)

This is an experiment to improve the search implementation. You are the search-branch agent.

## Setup

1. **Branch**: You run on `swarm/<run_tag>/search`. The run_tag is provided to you (e.g. `poc_001`).
2. **Read the in-scope files**:
   - `evaluate.py` — fixed oracle harness. Do not modify.
   - `evaluate_composite.py` — fixed composite oracle. Do not modify.
   - `solutions/search.py` — the **only file you modify**. Contains the search implementation.
3. **Do NOT touch**: `evaluate.py`, `evaluate_composite.py`, `solutions/sort.py`, or any other file.
4. **Initialize results_search.tsv**: Create `results_search.tsv` with header: `commit\tsearch_time_ms\tmemory_gb\tstatus\tdescription\tlog`. The baseline will be recorded after the first run.
5. **Read** `discoveries/shared_context.md` at the start if it exists.

Once setup is done, kick off the experimentation.

## Experimentation

**What you CAN do:**
- Modify `solutions/search.py` only. Change the algorithm (e.g. binary search). The contract is: `def search(arr: list, target: int) -> int` must return the index of target in the sorted list, or -1 if not found. `arr` is always sorted.

**What you CANNOT do:**
- Modify `evaluate.py` or `evaluate_composite.py`.
- Modify `solutions/sort.py`.
- Install new packages. Use only the Python standard library.

**The goal is simple: get the lowest search_time_ms.** Lower is better. The oracle runs a fixed benchmark (fixed seed, fixed input size) and reports `search_time_ms`.

**Note:** The baseline may not early-exit or may do extra work. Incremental improvements (e.g. add early exit when arr[i] > target, then try binary search) can yield multiple gains over several experiments.

**Simplicity criterion**: All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it.

**The first run**: Your very first run should always be to establish the baseline: run the oracle as-is without changing `solutions/search.py`.

## Output format

The oracle prints:

```
---
search_time_ms:  3321.88
input_size:      5000
n_runs:          150
```

Extract the key metric:

```
grep "^search_time_ms:" run.log
```

## Logging results

Log **every** experiment to `results_search.tsv` (tab-separated)—both keep and discard. Do not commit this file; leave it untracked.

The TSV has a header row and 6 columns:

```
commit	search_time_ms	memory_gb	status	description	log
```

1. git commit hash (short, 7 chars)
2. search_time_ms achieved (e.g. 567.89) — use 0.0 for crashes
3. memory_gb: use 0.0 (not applicable for this PoC)
4. status: `keep`, `discard`, or `crash`
5. short label for the experiment (e.g. "Added early exit when arr[i] > target")
6. **log** (1–2 lines): what you did, why, and whether it worked or not. Encode tabs as spaces so the line stays one TSV cell.

Example log cells: "Added early exit; sorted input so we can stop early; kept, ~2x faster." or "Tried binary search; forgot to handle missing; crash, reverted."

**TSV append:** Use `printf '%s\t...' "$(git rev-parse --short HEAD)" ... >> results_search.tsv` or a one-line Python print. Do not use `echo -e` — it can prefix the commit column with "-e" and break downstream parsing.

## The experiment loop

LOOP for the number of iterations you are told (e.g. 3 or 4), or until you are stopped:

1. Look at the git state: current branch and commit.
2. Modify `solutions/search.py` with an experimental idea.
3. git add solutions/search.py && git commit -m "<short description>"
4. Run the oracle: `python3 evaluate.py --branch search > run.log 2>&1` (redirect everything; do NOT use tee).
5. Read the result: `grep "^search_time_ms:" run.log`
6. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to see the error. Fix if trivial (typo, import); otherwise log "crash" and revert.
7. Append one row to results_search.tsv for this experiment (commit, search_time_ms, memory_gb, status, description, log). Do not commit the TSV.
8. If search_time_ms improved (lower), keep the commit and advance.
9. If search_time_ms is equal or worse, run `git reset --hard HEAD~1` to discard.

**Timeout**: If a run exceeds 2 minutes, treat as failure (discard and revert).

**Crashes**: If something dumb (typo, import), fix and re-run. If the idea is broken, log "crash" and move on.

**NEVER STOP**: Do not ask the human if you should continue. Run the requested number of iterations autonomously. If you run out of ideas, try binary search (O(log n)) since the list is sorted.

Write significant findings (e.g. which change gave the biggest gain) to `discoveries/search.md` when you have something useful to share.
