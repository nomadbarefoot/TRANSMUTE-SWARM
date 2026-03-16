# Run analysis: test1 vs test2 (parallel Swarm Research)

**Runs:** test1 = [23124704722](https://github.com/nomadbarefoot/TRANSMUTE-SWARM/actions/runs/23124704722), test2 = [23124704785](https://github.com/nomadbarefoot/TRANSMUTE-SWARM/actions/runs/23124704785)  
**Config:** 3 iterations per branch, branch_ids = sort, search.

---

## Status

| Run   | prepare_matrix | setup_branches | branch_research (sort) | branch_research (search) |
|-------|----------------|----------------|------------------------|--------------------------|
| test1 | ✓ 2s           | ✓ 5s           | ✓ 3m10s                 | ✓ 53s                    |
| test2 | ✓ 3s           | ✓ 5s           | ✓ 3m10s                 | ✓ 44s                    |

Both runs completed successfully. Jobs ran in parallel across the two workflow runs.

---

## Results by branch

### Sort branch

| Run   | Experiments | Baseline (bubble) | Best | Best commit | Description        |
|-------|-------------|--------------------|------|-------------|--------------------|
| test1 | 2           | 45,948 ms          | **21.33 ms** | 48a10b4     | Use built-in sorted (Timsort) |
| test2 | 2           | 45,506 ms          | **21.33 ms** | 1df6cef     | Use built-in sorted (Timsort) |

- **Improvement:** ~2,150× (bubble → Timsort).
- **Conclusion:** Both runs found the same optimum; final code is `return sorted(arr)` (Timsort). Baseline variance (45.9k vs 45.5k ms) is runner/CPU noise.

### Search branch

| Run   | Experiments | Baseline (linear) | Best | Best commit |
|-------|-------------|-------------------|------|-------------|
| test1 | 1           | 4.54 ms           | 4.54 ms | 54fa90e   |
| test2 | 1           | 4.43 ms           | 4.43 ms | 54fa90e   |

- **Improvement:** None; both runs only recorded baseline (linear search).
- **Conclusion:** With 3 iterations and the tool-round limit, the search agent did not log a second experiment (e.g. binary search). Search baseline is already fast (~4.5 ms) so the agent may have hit the round limit before attempting a change.

---

## Summary

| Metric           | test1    | test2    | Note                          |
|------------------|----------|----------|-------------------------------|
| Sort best (ms)   | 21.33    | 21.33    | Same optimum                  |
| Sort speedup     | ~2,153×  | ~2,134×  | Bubble → Timsort              |
| Search best (ms) | 4.54     | 4.43     | Baseline only                 |
| Composite*       | ~12.9 ms | ~12.9 ms | 0.5×sort + 0.5×search (this run) |

\*For this 2-branch run, composite = 0.5×sort + 0.5×search. Current default is 3 branches with weights 1/3 each (sort, search, filter); see `evaluate_composite.py`.

---

## Observations

1. **Sort:** Both runs converged to the same strategy (Timsort) in 2 experiments. The problem is small (one dominant improvement), so results are stable across runs.
2. **Search:** No improvement logged in either run; more iterations or a higher tool-round limit would be needed to see binary search or other variants.
3. **Reproducibility:** Sort results are effectively identical across test1 and test2; runner variance appears only in the baseline (bubble) time.
4. **Artifact quirk:** Some TSV rows can contain a literal `-e` (from `echo -e`). Coordinator now strips that and extracts the 7-char hash. Programs instruct agents to use `printf` or Python when appending TSV rows to avoid this.
5. **Coordinator TSVs:** Results TSVs are not committed; the coordinator workflow downloads them from the swarm run's artifacts (provide swarm_run_id when triggering coordinator manually).
