# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Agent Model Policy

**Use subagents aggressively for menial tasks.** Subagents must use `haiku` model exclusively. Reserve Sonnet/Opus for tasks requiring reasoning, judgment, or synthesis.

Delegate to subagents for:
- Codebase exploration (finding files, grepping patterns, summarizing structure)
- Reading and summarizing research papers or long documents
- Repetitive file reads across many files
- Any task that is mechanical, not requiring reasoning

Do NOT use subagents (use current model) for:
- Architecture decisions and implementation planning
- Writing or reviewing non-trivial code
- Debugging complex issues
- Tasks requiring cross-context reasoning

## Project Overview

TRANSMUTE-SWARM is a tiered autonomous research system. The **Transmuter** decomposes optimization problems into parallel tasks, **Cogs** (branch agents) run LLM-driven experiments on each task, and results are synthesized deterministically by the **Coordinator**.

## Terminology

- **Cog** — a single branch agent instance, scoped to one task and one solution file
- **Swarm** — a set of Cogs running in parallel under the same `run_tag`
- **Transmuter** — the orchestrator pipeline that decomposes problems, generates Cog programs, and dispatches runs
- **Coordinator** — the deterministic synthesizer that cherry-picks best commits and runs the composite oracle

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r config/requirements.txt
echo 'OPENROUTER_API_KEY="your-key"' > keys.env
python scripts/probe_models.py  # run once; writes config/model_config.yaml
```

## Running Experiments

**Transmuter (problem decomposition → artifact generation):**
```bash
# From natural language (LLM decomposes problem):
python agents/transmuter.py --problem "Optimize sorting for integer arrays" --run_tag tx_001

# From spec file (no LLM needed):
python agents/transmuter.py --spec config/decomposition.yaml --run_tag tx_001

# Auto mode (skip human checkpoint, for CI):
python agents/transmuter.py --problem "..." --run_tag tx_001 --auto
```

**Single Cog (local):**
```bash
python agents/agent.py --branch_id sort --iterations 4 --run_tag poc_001
python agents/agent.py --branch_id finance --iterations 4 --run_tag poc_001
```

**Cog branch management:**
```bash
python agents/cog_manager.py create  --run_tag poc_002 --cog_ids sort,search,filter --push
python agents/cog_manager.py list
python agents/cog_manager.py status  --run_tag poc_002
python agents/cog_manager.py cleanup --run_tag poc_001 --remote --dry-run
python agents/cog_manager.py purge   --older-than-days 7 --dry-run
```

**Coordinator (after Cogs complete):**
```bash
python agents/coordinator_script.py --run_tag poc_001 --branch_ids sort search filter
```

**Oracle evaluation (manual):**
```bash
python oracles/evaluate.py --branch sort --mode quick
python oracles/evaluate.py --branch sort --mode full
python oracles/evaluate_finance.py --mode full
python oracles/evaluate_composite.py
```

**Experiment harness (called internally by Cog agent):**
```bash
bash run_experiment.sh --branch sort --solution-path solutions/sort.py \
  --mode quick --description "Try timsort" --log "notes here"
```

## Directory Structure

```
TRANSMUTE-SWARM/
├── agents/
│   ├── agent.py              # Cog runner (structured tools: experiment/read_file/explore)
│   ├── cog_manager.py        # Cog branch lifecycle (create/list/status/cleanup/purge)
│   ├── coordinator_script.py # Deterministic synthesizer
│   └── transmuter.py         # Problem decomposition & task orchestration pipeline
│
├── cogs/                     # Cog task definitions (one dir per Cog type)
│   ├── sort/program.md       # Instructions for the sort Cog
│   ├── search/program.md
│   ├── filter/program.md
│   └── finance/program.md
│   # (Transmuter generates these dynamically from templates)
│
├── solutions/                # Cog-owned solution files (one file per Cog)
│   ├── sort.py, search.py, filter.py, finance_ma.py
│
├── oracles/                  # IMMUTABLE — deterministic ground truth
│   ├── evaluate.py, evaluate_composite.py, evaluate_finance.py
│   └── fixtures/
│
├── results/                  # All run outputs
│   ├── results_<cog_id>.tsv  # Live TSV per Cog
│   ├── token_usage.tsv       # Per-run token cost tracking
│   ├── logs/                 # Oracle run logs per Cog
│   └── archive/              # Timestamped snapshots of past runs
│
├── discoveries/              # Cog findings and shared context
│   ├── shared_context.md     # Cross-Cog discoveries injected into each Cog's context
│   └── archive/
│
├── config/
│   ├── model_config.yaml     # Primary + fallback + transmuter model config
│   ├── task_registry.yaml    # Central task registry (solution files, metrics, oracles)
│   ├── requirements.txt
│   ├── transmutation_keys.md
│   ├── decomposition.yaml    # Run decomposition spec (generated by transmuter or hand-written)
│   └── templates/            # Task templates (perf_benchmark, finance_strategy)
│       ├── perf_benchmark/   # program.md.tmpl + scaffold.py.tmpl
│       └── finance_strategy/ # program.md.tmpl + scaffold.py.tmpl
│
├── data/                     # External datasets
├── scripts/                  # Utility scripts (append_tsv, task_config, probe_models, fetch_nifty50)
└── DOCS/                     # Design docs, reports, analysis
    ├── dharma.md             # System invariants (human-writable only)
    └── reports/
```

## Architecture

### Three-Tier Design

```
Tier 0: Transmuter        (pipeline: parse → classify → decompose → generate → dispatch)
Tier 1: Composite Oracle  (deterministic ground truth — immutable)
Tier 2: Cogs              (cheap LLMs, parallel, each scoped to one solution file)
Tier 3: Coordinator       (deterministic synthesizer)
```

### Task Registry (`config/task_registry.yaml`)

Single source of truth for all task configurations. All scripts read this at runtime — no hardcoded branch mappings. To add a new task, append an entry; no code changes needed.

### Transmuter Pipeline

```
NL Problem / Spec YAML → Parse → Classify Template → Decompose (LLM) → Generate Artifacts → Human Checkpoint → Output
```

Only 2 of 6 stages use LLM (classify fallback + decompose). Spec mode bypasses LLM entirely.

### Key Invariants

- **Oracles are immutable** — Cogs may never modify `oracles/`. The oracle is the only arbiter.
- **Cog file ownership** — each Cog owns exactly one file in `solutions/`. No cross-Cog writes.
- **`run_experiment.sh` is the only path to git and TSVs** — Cog tools (experiment/read_file/explore) call it internally. Direct calls to `evaluate.py`, `append_tsv.py`, `git commit/reset`, or direct writes to `results/` are policy violations.
- **Composite score overrides all** — local Cog improvements that don't move the composite are not wins.

### Cog Agent Tools (v2 structured interface)

| Tool | Purpose | Counts against budget |
|------|---------|----------------------|
| `experiment` | Submit solution code + run oracle | Yes (hard limit = --iterations) |
| `read_file` | Read any repo file | No (soft limit) |
| `explore` | Read-only shell (grep/ls/cat/find…) | No (soft limit) |

### Cog Branch Naming

```
cogs/<run_tag>/<cog_id>
e.g. cogs/poc_001/sort, cogs/poc_002/finance
```

Managed via `agents/cog_manager.py`. Swarms share a `run_tag`; each Cog gets its own branch.

### Data Flow

1. Cog calls `experiment` tool → writes solution file → invokes `run_experiment.sh`
2. Script runs oracle → parses metric → commits if improved → appends TSV row
3. Coordinator reads TSVs → cherry-picks best commits → runs composite oracle → ablation

### Quick→Full Promotion

Cogs use `mode=quick` (10 samples) for scouting; if better than baseline the script auto-promotes to `mode=full` (50 samples) before committing.

### Results Schema (`results/results_<cog_id>.tsv`)

Columns: `commit`, `<metric>`, `memory_gb`, `status`, `description`, `log`

- `status` values: `keep`, `discard`, `crash`
- Only `keep` rows are considered best by the coordinator

## GitHub Actions CI/CD

- **swarm.yml** — triggered via `workflow_dispatch` with `run_tag`, `cog_ids`, `iterations`; creates `cogs/<run_tag>/<cog_id>` branches via `cog_manager.py`, runs Cogs in parallel
- **coordinator.yml** — triggered after swarm completes; downloads TSV artifacts, runs coordinator, uploads `coordinator_report_*.md`

## Model Configuration

`config/model_config.yaml` (written by `probe_models.py`):
```yaml
primary: stepfun/step-3.5-flash:free      # Cog primary
fallback: openrouter/hunter-alpha          # Cog fallback
transmuter: stepfun/step-3.5-flash:free    # Transmuter LLM (swap independently)
```

Agent reads this file; switches to fallback immediately on primary failure. Transmuter uses the `transmuter` key (falls back to `primary` if missing).

## Current Phase

Phase 2: Transmuter operational. The transmuter pipeline decomposes problems and generates Cog artifacts. Coordinator is deterministic (no LLM). Cogs are autonomous.
