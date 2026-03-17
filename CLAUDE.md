# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TRANSMUTE-SWARM is a tiered autonomous research system for decomposing optimization problems into parallel branches, running LLM-driven agents on each branch, and synthesizing results deterministically (no LLM in the synthesis layer).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r config/requirements.txt
echo 'OPENROUTER_API_KEY="your-key"' > keys.env
python scripts/probe_models.py  # run once; writes config/model_config.yaml
```

## Running Experiments

**Single branch agent (local):**
```bash
python agents/agent.py --branch_id sort --iterations 4 --run_tag poc_001
python agents/agent.py --branch_id finance --iterations 4 --run_tag poc_001
```

**Coordinator (after branches complete):**
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

**Experiment harness (used by agents):**
```bash
bash run_experiment.sh --branch sort --solution-path solutions/sort.py \
  --mode quick --description "Try timsort" --log "notes here"
```

## Architecture

### Three-Tier Design

```
Tier 1: Composite Oracle (deterministic ground truth, no LLM)
Tier 2: Branch Agents (cheap LLMs, parallel, scoped to one solution file)
Tier 3: Coordinator/Synthesizer (deterministic script or human, Phase 1)
```

### Key Invariants

- **Oracles are immutable** — agents may never modify `oracles/`. The oracle is the only arbiter.
- **Branch file ownership** — each agent owns exactly one file in `solutions/` and may not touch other branches.
- **`run_experiment.sh` is the only way agents interact with git and TSVs** — direct calls to `evaluate.py`, `append_tsv.py`, `git commit/reset`, or writing to `results/` are policy violations.
- **Composite score overrides all** — local branch improvements that don't move the composite are not wins.

### Data Flow

1. Agent calls `run_experiment.sh` (single tool call per iteration)
2. Script runs oracle → parses metric → commits if improved → appends TSV row
3. Coordinator reads TSVs → cherry-picks best commits → runs composite oracle → ablation

### Quick→Full Promotion

Agents use `--mode quick` (10 samples) for scouting; if better than baseline, the script auto-promotes to `--mode full` (50 samples) before committing. This cuts wall-clock time while keeping final metrics honest.

### Results Schema (`results/results_<branch>.tsv`)

Columns: `commit`, `<metric>`, `memory_gb`, `status`, `description`, `log`

- `status` values: `keep`, `discard`, `crash`
- Only `keep` rows are considered "best" by the coordinator

## GitHub Actions CI/CD

- **swarm.yml** — triggered via `workflow_dispatch` with `run_tag`, `branch_ids`, `iterations`; runs branch agents in parallel on separate git branches (`swarm/<run_tag>/<branch_id>`)
- **coordinator.yml** — triggered after swarm completes; downloads TSV artifacts, runs coordinator, uploads `coordinator_report_*.md`

## Model Configuration

`config/model_config.yaml` (written by `probe_models.py`):
```yaml
primary: stepfun/step-3.5-flash:free
fallback: openrouter/hunter-alpha
```

Agent reads this file; fallback activates automatically on primary failure.

## Current Phase

Phase 1: Human as synthesizer. The coordinator script is deterministic (no LLM). Branch agents are autonomous; synthesis/interpretation is manual.
