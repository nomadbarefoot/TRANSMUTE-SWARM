# Subagent Design Analysis & Improvements

## Decision: Option B — Structured Action Tool

The v2 agent replaces the freeform `bash` tool with three structured tools:

| Tool | Purpose | Counts against budget |
|------|---------|----------------------|
| `experiment` | Submit solution code + run oracle | Yes (hard limit) |
| `read_file` | Read any repo file | No (soft limit) |
| `explore` | Read-only shell (grep, ls, cat…) | No (soft limit) |

This eliminates the policy hole, heredoc fragility, and arbitrary execution surface in one move.

---

## Problems Addressed

### 1. Policy Hole (fixed)
The old `_policy_violation()` returned `None` (no violation) if `"run_experiment.sh"` appeared
*anywhere* in a command string, including:

```bash
rm -rf /important/stuff  # run_experiment.sh
```

With structured tools, agents submit JSON — there is no shell string to exploit. The `experiment`
handler writes only to the owned solution file (path validated from `BRANCH_SOLUTION_FILES`).
The `explore` handler validates against an allowed-prefix list and blocked-token list.

### 2. Exploration vs. Experiment Budget (fixed)
Old: `max_tool_rounds = iterations * 2 + 4` counted reads and experiments identically.

New: two separate counters.
- `experiment_count`: hard limit = `--iterations`. Incremented only by `experiment` tool calls.
- `read_count`: soft limit = `iterations * 4`. Incremented by `read_file` and `explore`.

### 3. Context Window Scaling (fixed)
Old: messages grew unboundedly.

New: sliding window (`SLIDING_WINDOW_PAIRS = 6`) keeps system + initial user + last 6 exchange
pairs. A fresh state block is injected before every API call:

```
## Agent State (experiment 7/15)
best_metric: 1200.5 (commit a1b2c3d, "Use numpy argsort")
recent_attempts (last 5): ...
dead_ends: ["radix sort (→ crash)", ...]

## Your Results So Far
| # | sort_time_ms | status | description |
...
```

### 4. Heredoc Fragility (eliminated)
Old: agents had to write valid shell heredocs — common failure mode for LLMs.

New: `solution_code` is passed as a JSON string. The agent never generates shell syntax for file
writes. The handler writes the file directly via `Path.write_text()`.

### 5. Dead-End Memory (fixed)
When `experiment` returns `status=discard` or `status=crash`, the description is appended to
`dead_ends`. This list is injected into every state block, surviving context pruning.

### 6. Reflection Checkpoint (fixed)
After `REFLECTION_INTERVAL` (default 3) consecutive non-improving experiments, the agent receives:

```
REFLECTION CHECKPOINT (experiment 6/15, 3 consecutive non-improvements, 9 remaining)
You've made several attempts without improvement. Before continuing:
1. What fundamentally different approach have you NOT tried?
2. Would a completely different algorithm or data structure beat incremental tuning?
```

This is a free injected user message — no extra API call.

### 7. Retry Before Fallback (fixed)
Old: any API exception immediately switched to fallback permanently.

New: exponential backoff (2^n seconds) for up to 3 retries on the current model before switching
to fallback. Handles transient 429 rate limits on free models.

### 8. Token Usage Tracking (fixed)
After each run, a row is appended to `results/token_usage.tsv`:

```
branch_id  run_tag  model_used  total_prompt_tokens  total_completion_tokens  iterations_completed  timestamp
```

### 9. Metric Trajectory Injection (fixed)
The full results TSV is rendered as a markdown table and injected before every API call.
The agent has perfect recall of its trajectory regardless of context pruning.

---

## What Was Not Implemented (Trade-offs)

**explore tool flexibility vs. baseline bash tool**

The `explore` tool covers grep/ls/cat/head/tail/find/wc/awk and read-only sed. This handles
~95% of legitimate exploration. Arbitrary bash (e.g., running Python scripts for analysis) is
no longer available. If agents need richer exploration, add specific tool types rather than
reopening freeform bash.

---

## Verification Checklist

```bash
# 1. Basic run
python3 agents/agent.py --branch_id sort --iterations 4 --run_tag fortify_test

# 2. Verify exploration reads don't count against experiment budget
# (check [agent] log line: experiments=4 reads=N)

# 3. Verify explore blocks writes
# (the handler should return BLOCK messages for any > token or sed -i)

# 4. Verify token_usage.tsv is written
cat results/token_usage.tsv

# 5. Verify 4 experiment iterations complete without infinite loop
```
