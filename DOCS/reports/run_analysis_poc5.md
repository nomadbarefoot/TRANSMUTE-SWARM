# poc5 — Swarm Loop & Coordinator Analysis

## 1. Run overview

- **Workflows**
  - `Swarm Research` (`.github/workflows/swarm.yml`)
    - Run ID: `23141992497`
    - Trigger: `workflow_dispatch`
    - Inputs: `run_tag=poc5`, `branch_ids=sort,search,filter`, `iterations=4`
    - Status: **success**, duration ≈ **13m56s** (11:44:35Z → 11:58:31Z)
  - `Coordinator` (`.github/workflows/coordinator.yml`)
    - Run ID: `23142502086`
    - Trigger: `workflow_run` (after `Swarm Research`)
    - Status: **success** (job completed, report uploaded), duration ≈ **10m18s** (11:58:34Z → 12:08:52Z)

- **Local token-logged test runs**
  - Agent runs under `.venv` with `run_tag=poc5_tokens`, `iterations=3`:
    - `branch_id=sort`
    - `branch_id=search`
    - `branch_id=filter`
  - Token usage logged to `token_usage.tsv` for each `chat.completions.create` call.

## 2. Branch metrics (poc5)

### 2.1 Sort

`results_sort.tsv` (subset):

```2:7:TRANSMUTE-SWARM/results_sort.tsv
commit     sort_time_ms  memory_gb  status   description
9720722    22524.27      0.0        keep     baseline bubble sort
bf2a09f    11.94         0.0        keep     Use built-in sorted (Timsort)
none       63613.85      0.0        discard  smoke: no-op    Smoke test of run_experiment.sh on sort
bf2a09f    11.48         0.0        keep     Baseline: built-in sorted()   Baseline run with built-in sorted() - 11.48ms
5a074af    10.65         0.0        keep     In-place list.sort()  In-place sort avoids creating new list; 10.65ms (improved from 11.48ms)
-e b323e84 10.79         0.0        keep     baseline: in-place list.sort()
```

- **Best kept metric**: ~**10.65 ms** (in-place `list.sort`), slightly better than the ~21.4 ms best in `poc4`.
- Branch loop clearly finds and keeps the right improvements from the deliberately bad bubble-sort baseline.

### 2.2 Search

`results_search.tsv` (subset):

```1:4:TRANSMUTE-SWARM/results_search.tsv
commit     search_time_ms  memory_gb  status  description
9720722    2.40            0.0        keep    baseline linear search
-e 5a074af 2.43            0.0        keep    baseline
-e b323e84 0.04            0.0        keep    binary search O(log n) implementation
```

- **Best kept metric**: ~**0.04 ms** (binary search).
- In `poc4` the agent reached ~0.02 ms via `bisect`; this run is the same order of magnitude and far better than the ~6.4 ms linear baseline.

### 2.3 Filter

- Filter branch produced `results_filter.tsv` in CI (confirmed by coordinator job logs), but the file is not currently present in the local workspace root.
- Coordinator log shows:

```132:138:.../actions/runs/23142502086 (via logs)
TSV files in workspace:
results_filter.tsv
results_search.tsv
results_sort.tsv
```

- Based on prior runs (poc4 and local tests), best filter_time_ms remains in the ~4 ms range (single-pass append-based implementation), starting from ~418 ms O(n²) baseline.

## 3. Token & tool usage (local poc5_tokens runs)

`token_usage.tsv` (subset):

```1:9:TRANSMUTE-SWARM/token_usage.tsv
timestamp_utc          branch_id  model                         prompt_tokens  completion_tokens  total_tokens  tool_rounds
2026-03-16T11:33:34Z   search     stepfun/step-3.5-flash:free   1522           263                1785          0
2026-03-16T11:33:36Z   sort       stepfun/step-3.5-flash:free   1529           266                1795          0
2026-03-16T11:33:38Z   search     stepfun/step-3.5-flash:free   1610           49                 1659          1
2026-03-16T11:33:41Z   search     stepfun/step-3.5-flash:free   1677           85                 1762          2
2026-03-16T11:33:42Z   sort       stepfun/step-3.5-flash:free   2718           236                2954          3
2026-03-16T11:33:45Z   search     stepfun/step-3.5-flash:free   1747           94                 1841          3
2026-03-16T11:33:48Z   search     stepfun/step-3.5-flash:free   1833           78                 1911          4
2026-03-16T11:33:48Z   sort       stepfun/step-3.5-flash:free   3710           78                 3788          6
```

Observations:

- **Per-call token sizes**:
  - Prompt side is ~1.5–3.7k tokens; completion side is ~50–260 tokens.
  - This is dominated by:
    - Long system prompt (full `program_<branch>.md` + shared context).
    - Growing history of previous messages and tool outputs.
- **Tool rounds**:
  - `tool_rounds` is the cumulative count of bash tool invocations up to that completion.
  - Even with small `iterations=3`, we see several tool rounds per branch because the agent:
    - Still issues multiple bash calls per experiment (git, oracle, logging, etc.), following the fine-grained program instructions.

High-level takeaway:

- The new logging confirms that the **core cost per completion is on the order of a few thousand tokens**, and that **multiple completions + multiple tool calls occur per iteration**.
- To truly reduce token and tool overhead, we need to:
  - Make `run_experiment.sh` the *only* endorsed path for experiments.
  - Reduce `max_tool_rounds` and steer the agent away from granular git/oracle commands.

## 4. Coordinator behavior and integration fragility

Coordinator logs (for `poc5`):

```103:147:TRANSMUTE-SWARM/coordinator_script.py (logic)
run(root, "git", "checkout", "main", check=False)
run(root, "git", "pull", "origin", "main", check=False)
int_branch = f"integration/{run_tag}"
run(root, "git", "branch", "-D", int_branch, check=False)
run(root, "git", "checkout", "-b", int_branch)
...
run(root, "git", "cherry-pick", commit, check=False)
...
WARNING: cherry-pick fef208c (branch sort) failed; skipping.
WARNING: cherry-pick 045f829 (branch search) failed; skipping.
WARNING: cherry-pick 2ed7897 (branch filter) failed; skipping.
WARNING: composite oracle failed.
Wrote .../coordinator_report_1.md
```

Findings:

- **Best-commit discovery** still works:
  - Coordinator successfully reads `results_sort.tsv`, `results_search.tsv`, `results_filter.tsv`, identifies the best kept commit per branch, and writes them to `coordinator_report_1.md`.
- **Integration is fragile by design**:
  - Integration branch `integration/poc5` is always created from *current* `main`:
    - Not from the Swarm run’s base SHA (`headSha` when branches were spawned).
  - Swarm branches (`swarm/poc5/*`) were created off an earlier main (M₀).
  - When coordinator runs later, `main` may be at M₁ or M₂; cherry-picking best commits from M₀-based branches onto M₁/M₂ naturally causes conflicts.
  - Result: all cherry-picks are skipped, composite oracle fails (nothing to evaluate), but the report still emits best-commit tables and a “composite failed” note.

Key insight:

- For this PoC (and for future phases), the **integration branch should be based on the Swarm run’s base SHA**, not the moving HEAD of `main`. That base SHA is available from:
  - The Swarm run metadata (`headSha` for run `23141992497`), and/or
  - An explicit field in `decomposition.yaml` (e.g., `integration_base_sha`).

Conceptual fix:

- Replace:

```bash
git checkout main
git pull origin main
git checkout -b integration/poc5
```

- With something like:

```bash
git checkout -B integration/poc5 <integration_base_sha>
```

Where `<integration_base_sha>` is the SHA `swarm/poc5/*` were branched from (e.g., the Swarm run’s `headSha` at launch).

- This would:
  - Make composite + ablation **independent of subsequent changes to main**.
  - Leave the question of “how to land integration/poc5 onto latest main” as a **separate, human-reviewed merge step**.

## 5. Pipeline hardening insights from this run

### 5.1 Subagents need discipline, not intelligence

- These branch agents are not doing novel research; they are:
  - Editing a single file.
  - Calling a scripted oracle.
  - Keeping/discarding based on a scalar metric.
- What they need is **strong instruction-following on a very constrained action space**, not high reasoning ability.
- Current prompts still treat the agent like a generic shell user (“use bash for every action”), which:
  - Encourages many small, low-level tool calls.
  - Amplifies token and latency costs, especially with weaker models.

### 5.2 `run_experiment.sh` must be the primary interface

- You’ve implemented `run_experiment.sh` + `append_tsv.py`, which already:
  - Runs the oracle.
  - Parses metrics.
  - Decides keep/discard.
  - Performs git commit or revert.
  - Appends TSV rows with a consistent schema.
- However, `program_*.md` still describe the original, fine-grained loop (git, evaluate, grep, printf, reset).
- As a result:
  - Agents *can* still call raw git/`evaluate.py`/grep, and often do.
  - Token usage and tool-round counts remain higher than necessary.

Insight:

- To harden the loop, `run_experiment.sh` should be the **only endorsed way** to run experiments. Program and system instructions should explicitly:
  - **Allow**: `bash run_experiment.sh ...`.
  - **Forbid**: direct `git add/commit/reset`, `python3 evaluate.py`, `grep` on `run.log`, and manual TSV writes.

### 5.3 Token and tool-call budgets should be explicit and tight

- `max_tool_rounds` is currently `iterations * 5` in `agent.py`. Even with small `iterations`, agents frequently hit “Max tool rounds reached; stopping.” because:
  - Each experiment is decomposed into multiple tiny bash calls.
  - Some calls are redundant (re-checking files, re-running commands).
- Combined with ~1.5–3.5k prompt tokens per completion, this is where most token waste lives.

Insight:

- Once program.md files are updated to enforce `run_experiment.sh`, it will be safe and beneficial to:
  - Reduce `max_tool_rounds` (e.g., `iterations * 3` or similar).
  - Treat hitting the tool-round limit as a signal to revise instructions or review the model, not as a “normal completion”.

### 5.4 Quick-mode oracle is ready but not yet systematically exploited

- `evaluate.py` now supports `--quick` (10 inner runs, 1 repeat) vs full (50 runs, 3 repeats):
  - Quick mode gives up to **15× fewer function calls** per eval.
  - It’s ideal for scouting experiments on very slow baselines.
- The branch programs, however, don’t yet instruct the agent to:
  - Use `--quick` for intermediate experiments.
  - Reserve full evaluations for final, `status=keep` candidate commits.

Insight:

- To gain consistent runtime improvements, program.md files should:
  - Codify a two-stage evaluation: quick scouting → full confirm on promising variants.
  - Make sure `results_*.tsv` metrics for `keep` rows come from full runs.

## 6. Overall conclusion

- **Core loop health**:
  - The improved loop (helpers, token logging, quick-mode-ready oracle, CI pip cache) works end-to-end for `poc5`.
  - Branch agents still find strong improvements on sort/search/filter from deliberately bad baselines.
- **Coordinator**:
  - Successfully reads artifacts and identifies best commits.
  - Integration via cherry-pick onto evolving `main` is fragile; composite/oracle failures are expected under this strategy.
- **Hardening priorities surfaced by this run**:
  1. Make `run_experiment.sh` the *only* legal path for experiments in program/system prompts.
  2. Base `integration/<run_tag>` on the Swarm run’s base SHA, not the moving `main`.
  3. Tighten `max_tool_rounds` once (1) is in place.
  4. Update `program_*.md` to describe a quick-vs-full evaluation strategy and to emphasize instruction-following over creativity.

These changes would preserve the successful behavior of `poc4/poc5` while making the pipeline more robust, cheaper, and less sensitive to model quality and `main` branch drift.

## 7. Clarifying the desired main / integration model

From this run and discussion, the intended mental model is:

- **Freeze `main` for the duration of a run.**
  - For a given `run_tag` (e.g. `poc5`), there is a base commit `M0` on `main`.
  - `swarm/<run_tag>/<branch_id>` branches are created from `M0`.
  - While branches iterate and the coordinator runs, `main` should conceptually remain at `M0` — no unrelated deltas.

- **Branch agents operate only on swarm branches.**
  - All experimental commits live on `swarm/<run_tag>/<branch_id>`.
  - `main` is never touched directly by branch agents.

- **Coordinator integrates against the same base `M0`.**
  - Instead of using current `main`, `coordinator_script.py` should:
    - Base `integration/<run_tag>` on `M0` (or an explicit `integration_base_sha` recorded at swarm start).
    - Cherry-pick the best commits from each `swarm/<run_tag>/<branch_id>` onto `integration/<run_tag>`.
    - Run composite + ablation on that frozen base + best-branch deltas.

- **Only after coordination does `main` move.**
  - Human (or future LLM coordinator) reviews `integration/<run_tag>`.
  - If approved, `main` is updated (fast-forward or merge) to that integration state.
  - If not approved, `main` stays at `M0`; the run is effectively “archived” without touching `main`.

This keeps `main` stable during a run, matches the “complex expression = combination of sub-results” mental model, and avoids the current situation where the CI coordinator’s use of a drifting `main` undermines composite evaluation.


