# Autoresearch vs TRANSMUTE-SWARM — Pipeline Comparison (2026-03-17)

## Overview
This document compares the original `autoresearch` pipeline (reference_repo) against the current TRANSMUTE-SWARM pipeline. It focuses on logical flow, control surfaces, and points where the pipelines diverge or can be improved.

## Reference Pipeline (autoresearch)
Source: `reference_repo/program.md`, `reference_repo/README.md`

**Core loop (single agent):**
1. Create a run branch `autoresearch/<tag>`
2. Read context: `README.md`, `prepare.py`, `train.py`
3. Ensure data prepared (`uv run prepare.py`)
4. Baseline run
5. Loop forever:
   - edit `train.py`
   - git commit
   - run `uv run train.py > run.log`
   - parse `val_bpb`
   - append `results.tsv`
   - keep if metric improves, else reset

**Key characteristics**
- Single agent, single file to modify (`train.py`).
- Fixed time budget (5 minutes) and single scalar metric (`val_bpb`).
- Minimal policy constraints, no coordinator/synthesizer.
- Results stored in a simple TSV; no integration or multi-branch composition.

## TRANSMUTE-SWARM Pipeline (current)
Source: `TRANSMUTE-SWARM/agents/agent.py`, `run_experiment.sh`, `prompts/programs`, `oracles/*`

**Core loop (branch agent):**
1. Program file specifies scope and loop (per-branch program).
2. Baseline via `run_experiment.sh --mode baseline`.
3. Loop for N iterations:
   - edit owned file
   - **single call** to `run_experiment.sh --mode quick` (auto-promotes to full on improvement)
   - script handles eval, compare, commit/revert, TSV append

**Key characteristics**
- Multi-branch capability (parallel agents), but can run single-agent.
- Tool-call strictness: only `run_experiment.sh` allowed for edits/eval.
- Deterministic composite layer and coordinator (phase-1 script).
- Results/logs standardized under `results/` and `results/logs/`.

## Logical Flow Comparison

**1) Scope control**
- Autoresearch: one mutable file (`train.py`), enforced by instruction only.
- TRANSMUTE-SWARM: per-branch ownership enforced by prompts + agent tool policy.

**2) Execution path**
- Autoresearch: many individual tool calls (git, run, grep, log) per iteration.
- TRANSMUTE-SWARM: single-call wrapper (`run_experiment.sh`) reduces tool calls to ~1 per iteration.

**3) Metric discipline**
- Autoresearch: one scalar metric, fixed time budget, always full evaluation.
- TRANSMUTE-SWARM: supports quick/full evaluation and explicit baseline modes; metrics are per-branch and optionally composited.

**4) Baseline handling**
- Autoresearch: baseline recorded by manual run + TSV entry (commit required).
- TRANSMUTE-SWARM: baseline written without commit (current HEAD hash), avoids empty commits.

**5) Logging & artifacts**
- Autoresearch: `run.log` and `results.tsv` in repo root.
- TRANSMUTE-SWARM: `results/results_<branch>.tsv` + `results/logs/<branch>.log`, consistent structure.

**6) Synthesis / integration**
- Autoresearch: no integration layer (single stream of improvements).
- TRANSMUTE-SWARM: coordinator script does multi-branch cherry-pick + composite + ablation.

## Inconsistencies / Gaps

1. **Agent instruction drift**
   - Autoresearch uses a single program (`program.md`).
   - TRANSMUTE-SWARM now stores programs under `prompts/programs/`, but older docs still reference `program_<id>.md` at repo root. Some design docs still describe the old location and manual loop.

2. **Baseline data vs. quick/full policy**
   - Autoresearch has no quick/full; always full.
   - TRANSMUTE-SWARM uses quick/full but does not yet normalize or track confidence, so quick variance can bias promotion decisions without additional safeguards.

3. **Result file divergence**
   - Some legacy runs still write TSVs at repo root while new flow writes to `results/`. Mixed locations can break coordinator runs unless carefully passed `--results_dir`.

4. **Oracle uniformity**
   - Autoresearch has one oracle embedded in `prepare.py` and enforced by structure.
   - TRANSMUTE-SWARM mixes oracles (`evaluate.py`, `evaluate_finance.py`), but there is no unified “oracle spec” for non-code tasks (e.g., window lengths, quick/full parameters).

5. **Tool-call safety**
   - Autoresearch depends on prompt compliance to avoid extraneous tool calls.
   - TRANSMUTE-SWARM enforces policy in `agent.py`, but a single failure mode (policy false positives) could block legitimate read commands that use pipes or multiple commands.

## Improvements / Enhancement Opportunities

**From Autoresearch to Swarm** (what we gained):
- Script-first iteration reduces tool chatter and token cost.
- Multi-branch scaffolding + composite scoring enables broader decomposition.
- Quick/full mode enables fast scouting with confirmation.

**From Swarm to Autoresearch** (what’s still strong in reference):
- Simplicity of a single objective and fixed time budget reduces variance.
- Single mutable file drastically reduces merge/conflict surface.

**Enhancement opportunities**
1. **Unify oracle interface**
   - Define a single `oracle_spec` format used by all branches (code and non-code), including quick/full parameters, metric name, and confidence handling.

2. **Create a “single agent mode” profile**
   - Provide a ready profile that mimics autoresearch simplicity when only one branch is active (e.g., `branch_count=1`, skip coordinator and composite by default).

3. **Add run provenance metadata**
   - Record `run_tag`, `base_sha`, data hash, oracle version, and quick/full params in each TSV row for auditability.

4. **Tighten quick/full promotion criteria**
   - Add simple variance checks or require two quick wins before a full promotion to reduce false positives from noisy quick runs.

5. **Program template modernization**
   - Deprecate legacy docs and keep prompts in a single canonical location; update design docs to reflect the script-first loop and `results/` structure.

6. **Branch independence enforcement**
   - Autoresearch avoids integration problems by design; to match that robustness, enforce a “frozen base SHA” rule in the coordinator for all multi-branch runs.

## Summary
Autoresearch is a minimal, single-agent loop optimized for simplicity and reliability. TRANSMUTE-SWARM extends that into a multi-branch system with better cost control (scripted iterations) and more ambitious synthesis. The current Swarm implementation is now structurally stronger, but still has documentation drift and a few missing standardizations (oracle specs, results location consistency, quick/full promotion safeguards). Addressing those will make the swarm pipeline as robust as the original while retaining its expanded capabilities.
