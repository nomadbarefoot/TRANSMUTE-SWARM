# Swarm Research System — Full Design Document

> Built on top of [autoresearch](https://github.com/karpathy/autoresearch) by @karpathy.
> This document captures the full architecture of a multi-agent, self-improving research
> system that extends the autoresearch loop to handle complex, abstract problems.

---

## Table of Contents

1. [Foundation: What autoresearch Actually Does](#1-foundation-what-autoresearch-actually-does)
2. [The Core Insight](#2-the-core-insight)
3. [System Vision](#3-system-vision)
4. [Full Pipeline Overview](#4-full-pipeline-overview)
5. [Component: The Transmuter](#5-component-the-transmuter)
6. [Component: Branches](#6-component-branches)
7. [Component: The Coordinator](#7-component-the-coordinator)
8. [Component: Coordinator Dharma](#8-component-coordinator-dharma)
9. [Component: The Explanation Gate](#9-component-the-explanation-gate)
10. [Component: Shared Discovery Context](#10-component-shared-discovery-context)
11. [Component: Transmutation Keys](#11-component-transmutation-keys)
12. [Execution Infrastructure](#12-execution-infrastructure)
13. [Phase Progression: Human → Autonomous](#13-phase-progression-human--autonomous)
14. [File & Schema Specifications](#14-file--schema-specifications)
15. [Feasibility & Risk Analysis](#15-feasibility--risk-analysis)
16. [Proof of Concept: What to Build First](#16-proof-of-concept-what-to-build-first)
17. [Open Problems](#17-open-problems)

---

## 1. Foundation: What autoresearch Actually Does

Before extending it, understand what the base system actually is.

### The Core Loop

autoresearch is a single-agent greedy hill-climber for a well-defined ML optimization problem:

```
LOOP FOREVER:
  1. Modify train.py (architecture, hyperparams, optimizer — anything)
  2. git commit
  3. Run: uv run train.py  (exactly 5 minutes wall clock)
  4. Read val_bpb from output
  5. If improved (lower val_bpb): keep commit, advance branch
  6. If not improved: git reset, discard
  7. Log to results.tsv
```

### What Makes It Work

| Property | Why It Matters |
|---|---|
| Single scalar oracle (`val_bpb`) | Unambiguous, cheap to compute, directly reflects the goal |
| Fixed time budget (5 min) | All experiments are directly comparable regardless of changes |
| Greedy hill-climbing | No memory needed; state is fully captured in git |
| Bounded search space (one file) | Agent can't break the evaluation harness |
| Git = experiment ledger | Every meaningful state is a commit; bad states are reset |
| Tight feedback loop | ~100 experiments per human sleep cycle |

### What It Is NOT

autoresearch is not doing novel research or inventing new directions. It is doing
**architecture and hyperparameter search in a well-constrained space**. The LLM agent
is doing what a grad student does when told: "try variations on this transformer,
measure loss, iterate." Its power comes from the feedback loop being tight enough
and the oracle clean enough that an LLM can do this reliably, autonomously, overnight.

**The fundamental constraint:** it works because `val_bpb` is a perfect oracle.
No oracle, no loop.

---

## 2. The Core Insight

Most real-world problems are abstract and cannot be directly plugged into the autoresearch
loop. However, **most abstract problems can be chunked into smaller, independently
iterable sub-problems that do have computable scalar metrics.**

The question is not "how do we make autoresearch handle abstract problems?" — it's
"how do we decompose abstract problems into pieces that autoresearch CAN handle?"

That decomposition layer — and the coordination layer above it — is what this system adds.

---

## 3. System Vision

A **swarm-based autonomous research system** that:

- Takes any complex, abstract problem as input
- Decomposes it into atomic sub-problems, each with a computable scalar metric
- Spawns parallel autoresearch-style agents (branches) for each sub-problem
- Coordinates those agents: verifying local improvements actually improve the composite goal
- Learns from each decomposition session to get better at decomposing future problems
- Gradually reduces human involvement as it accumulates a reliable track record
- Preserves counterintuitive discoveries through a peer-review mechanism
- Governs itself through immutable core principles that only humans can change

The end state: a self-improving research org that can be pointed at problems and produce
solutions, with humans setting goals and holding veto power but not managing day-to-day.

---

## 4. Full Pipeline Overview

```
┌──────────────────────────────────────────────────────┐
│               ABSTRACT / COMPLEX PROBLEM             │
└──────────────────────────┬───────────────────────────┘
                           │
                 ┌─────────▼──────────┐
                 │     TRANSMUTER      │
                 │  (conversational)   │
                 │                     │
                 │  Proposes branches  │
                 │  Defines oracles    │
                 │  Clusters coupled   │
                 │  sub-problems       │
                 │  Asks clarifying    │
                 │  questions          │
                 └─────────┬──────────┘
                           │
                 ┌─────────▼──────────┐
                 │    HUMAN REVIEW     │  Phase 1: mandatory
                 │                     │  Phase 2: major decisions only
                 │  Validates metrics  │  Phase 3: veto only
                 │  Approves branches  │
                 │  Iterates plan      │
                 └─────────┬──────────┘
                           │ [approved decomposition.yaml]
             ┌─────────────┼─────────────┐
             │             │             │
   ┌──────────▼──┐ ┌────────▼──┐ ┌───────▼───┐
   │  BRANCH A   │ │ BRANCH B  │ │ BRANCH C  │
   │             │ │           │ │           │
   │ autoresearch│ │autoresearch│ │autoresearch│
   │ loop        │ │loop       │ │loop       │
   │ own metric  │ │own metric │ │own metric │
   │ owns files: │ │owns files:│ │owns files:│
   │  [A1, A2]   │ │  [B1, B2] │ │  [C1]    │
   └──────┬──────┘ └─────┬─────┘ └─────┬────┘
          │              │              │
          └──────────────┼──────────────┘
                         │  [after N rounds]
               ┌─────────▼──────────┐
               │    COORDINATOR      │
               │                     │
               │  Reads results.tsv  │
               │  Cherry-picks best  │
               │  Runs composite     │
               │  oracle             │
               │  Ablation tests     │
               │  Credit assignment  │
               │  Updates program.md │
               │  Checks dharma      │
               └─────────┬──────────┘
                         │
           ┌─────────────┼──────────────┐
           │             │              │
  ┌────────▼───┐  ┌──────▼────┐  ┌─────▼───────────┐
  │ Continue   │  │  Spawn    │  │ Archive branch   │
  │ with new   │  │  sub-     │  │ (unrecoverable   │
  │ context    │  │  branches │  │  after gate)     │
  └────────────┘  └───────────┘  └─────────────────┘
                         │
               [repeat until composite
                metric converges or
                budget exhausted]
```

---

## 5. Component: The Transmuter

### Role

The transmuter is an LLM agent driven by `transmuter.md`. It takes an abstract problem
and produces an approved decomposition plan. It operates as a **conversation** with the
human — no branches are spawned until the human approves the final plan.

### Why Conversational

Decomposition quality is the single most important factor in system performance. A bad
decomposition — poorly defined metrics, coupled problems in separate branches, wrong
file ownership — causes every downstream component to fail. Human conversation is the
quality gate before deployment.

### Conversation Structure

```
Human: "Problem: Improve cold start time of our web app to under 1.5s"

Transmuter: "Before proposing a decomposition, I need to clarify three things:

  1. 'Cold start time' — I need to pick a computable oracle. Is this:
     (a) time-to-first-byte (TTFB), measured via: curl -w "%{time_starttransfer}"
     (b) Largest Contentful Paint (LCP), measured via: lighthouse --output=json
     (c) custom E2E timer? If so, what command?

  2. I see frontend bundle size and rendering performance are tightly coupled
     (changes to one affect measurement of the other). I recommend grouping
     these into one 'bundle_render' branch with a composite metric:
       score = 0.5 * normalize(bundle_kb) + 0.5 * normalize(LCP_ms)
     Agree, or do you prefer to keep them separate?

  3. Your description mentions 'better UX'. I cannot define a computable oracle
     for this. Should I:
     (a) Convert to task_completion_rate (requires test harness)
     (b) Convert to js_error_rate (available from logs)
     (c) Exclude from this decomposition"
```

### Transmuter Hard Rules

These are enforced before any decomposition is deployed:

1. **Every branch must have a computable, scriptable oracle.** If the transmuter cannot
   write a shell command that produces a scalar number, that sub-problem is not ready
   to branch. Keep decomposing or exclude.

2. **Semantically coupled sub-problems must be grouped** into a single branch with a
   composite metric. Two sub-problems are coupled if changing one materially affects
   the measurement of the other.

3. **File ownership must be non-overlapping.** Every file in the codebase is assigned
   to at most one branch. Files not owned by any branch are read-only for all branches.

4. **Maximum K branches at initial spawn** (K=5 recommended). Start small. Sub-branches
   can be spawned later by the coordinator if complexity demands it.

5. **The transmuter proposes; the human disposes.** No branch is spawned without
   explicit human sign-off on the full `decomposition.yaml`.

### Transmuter's Own Program File

The transmuter runs on `transmuter.md`, which can be updated by the system over time
(with human approval in Phase 1, autonomously in Phase 3). It loads `transmutation_keys.md`
at the start of every session to apply past learnings.

---

## 6. Component: Branches

### What a Branch Is

A branch is a standard autoresearch agent running on a git branch
(`swarm/<run_tag>/<branch_id>`), driven by its own `program_<branch_id>.md`.
It runs the autoresearch loop autonomously, with the following differences from
the base autoresearch setup:

- Its metric is the sub-problem oracle (not necessarily `val_bpb`)
- It only modifies files listed in its `owns` field
- It writes findings to `discoveries/<branch_id>.md` after significant experiments
- It monitors for plateau conditions and writes `SPAWN_PROPOSAL.md` if stuck
- It is subject to the explanation gate if its local metric and composite metric diverge

### Branch program.md Template

Each branch receives a customized `program_<id>.md` containing:

```markdown
# Branch: <id>

## Problem scope
<description of this sub-problem>

## Your metric
Metric: <metric_name>  (lower/higher is better)
Oracle: `<shell command that produces a single scalar>`
Goal: <target value or direction>

## File ownership
You ONLY modify files in this list:
  - <file1>
  - <file2>

Read-only (do not modify):
  - <shared_interface_file>

## Shared context
Read discoveries/shared_context.md before each experiment cycle.
This contains findings from other branches that may affect your approach.

## Spawning condition
If you have no metric improvement for 10 consecutive experiments, write
SPAWN_PROPOSAL.md with:
  - Why you are stuck
  - Proposed split into 2 sub-branches with their own oracles
  - File ownership partition for each sub-branch
Then pause and wait for coordinator response.

## Explanation gate
If the coordinator sends you an EXPLANATION_REQUEST, respond using the
structured template in EXPLANATION_TEMPLATE.md within your next cycle.

## The loop
[standard autoresearch loop, but with your oracle replacing val_bpb]
```

### Branch Lifecycle States

```
proposed → active → plateaued → [spawning | completing | archived]
```

- **proposed**: in `decomposition.yaml`, awaiting human approval
- **active**: running the autoresearch loop
- **plateaued**: 10+ consecutive experiments with no local metric improvement
- **spawning**: writing `SPAWN_PROPOSAL.md`, waiting for coordinator response
- **completing**: local metric has converged, composite is stable
- **archived**: killed by coordinator after failed explanation gate or irrecoverable plateau

---

## 7. Component: The Coordinator

### Role

The coordinator is an LLM agent driven by `coordinator.md`. It runs on a slower
cadence than branches (e.g., every N branch experiment rounds, or on a time schedule).
Its job is integration, credit assignment, and cross-branch guidance.

**Critical design choice:** The coordinator is **algorithmic and evidence-based**, not
conversational. Its decisions are reproducible given the same inputs. It produces
human-readable reports but does not engage in dialogue to make decisions. This
prevents coordination-layer stochasticity from compounding branch-level stochasticity.

### Coordinator Loop

```
COORDINATOR CYCLE (runs every N rounds):

1. GATHER
   Read results.tsv from all active branches.
   Identify branches with new improvements since last cycle.

2. INTEGRATE
   For each improved branch:
     Cherry-pick best commit onto integration branch.
   Run composite oracle on integration branch.
   Record composite_metric_delta.

3. ABLATION (if composite regressed)
   For each branch contribution:
     Revert that branch's cherry-pick, re-run composite oracle.
     marginal_contribution[branch] = composite_with - composite_without
   Identify the culprit branch(es).

4. CREDIT ASSIGNMENT
   Based on ablation results:
     - Branches with positive marginal contribution: advance
     - Branches with neutral contribution: flag, continue
     - Branches with negative contribution: trigger EXPLANATION_REQUEST
       (see Explanation Gate)

5. REPORT
   Write coordinator_report_<cycle>.md:
     - Composite metric delta this cycle
     - Per-branch contribution scores
     - Branches flagged for explanation
     - Branches proposed for spawning (from SPAWN_PROPOSAL.md files)
     - Recommended program.md updates per branch
     - Any items requiring human review (per dharma)

6. UPDATE BRANCHES
   For each active branch: update their program_<id>.md with:
     - New shared context
     - Coordinator feedback (what to prioritize or avoid)
     - Whether to continue, spawn, or archive

7. DHARMA CHECK
   Before executing any action, verify it is consistent with
   coordinator_dharma.md. If any proposed action violates dharma,
   halt and flag for human review.

8. UPDATE TRANSMUTATION KEYS
   If a completed decomposition has enough outcome data, extract learnings
   and append to transmutation_keys.md with outcome_quality score.
```

### Coordinator's Own Program File

`coordinator.md` can be modified (by the system in Phase 3, with human approval in
Phases 1-2). The coordinator can propose changes to its own program file based on
observed inefficiencies, but the change requires human sign-off until Phase 3.

---

## 8. Component: Coordinator Dharma

### What It Is

`coordinator_dharma.md` is the **immutable constitution** of the system. It contains
core principles that no agent can modify — not branches, not the coordinator, not the
transmuter. Changes require explicit human approval with version-controlled sign-off.

Dharma is loaded at the start of every coordinator cycle and checked before every
action. It is the fixed point that prevents recursive self-improvement from destabilizing
the system.

### Example Dharma File

```markdown
# coordinator_dharma.md
# HUMAN-WRITABLE ONLY. Last updated: <date> by <human>.
# Version: 1.0

---

## PRINCIPLE 1: ORACLE PRIMACY
The composite oracle is ground truth. No branch improvement is accepted as
"real" unless it holds under composite evaluation. A branch that improves
its local metric but degrades the composite is not an improvement.
No exceptions without explicit human override.

## PRINCIPLE 2: EVIDENCE OVER RHETORIC
A branch's explanation can earn extended experimental runway.
It cannot override a negative composite result.
The coordinator tests predictions, not rhetoric.
An explanation without a falsifiable, automatically testable prediction
earns no extended runway.

## PRINCIPLE 3: SWARM BOUNDS
Maximum 5 active branches at any time during Phase 1 and Phase 2.
Spawning beyond this limit requires explicit human approval.
This limit exists to keep the system manageable and debuggable.

## PRINCIPLE 4: SELF-MODIFICATION GATE
Any proposed change to coordinator.md, transmuter.md, or this dharma file
requires human approval before being applied.
The system proposes; humans dispose.
This includes the coordinator proposing changes to itself.

## PRINCIPLE 5: TRANSMUTATION KEY INTEGRITY
Transmutation keys can be added automatically by the system.
Keys can only be deleted or quality-downgraded by humans.
Learning accumulates in one direction only.
Bad keys are flagged, not silently purged.

## PRINCIPLE 6: DISCOVERY PRESERVATION
Branch findings that fail the composite test but survive the explanation gate
are logged as discoveries, not silently discarded.
Counterintuitive results that can be explained are scientifically valuable
even when they don't immediately improve the composite metric.

## PRINCIPLE 7: HUMAN OVERRIDE
A human can always override any system decision at any phase.
The system documents the override in the coordinator report.
Overrides are not penalized but are tracked as signal for future learning.

## PRINCIPLE 8: METRIC DEFINITION IS SACRED
A branch's oracle may not be redefined after the branch is active without
human approval and a new baseline measurement.
Moving the goalposts invalidates all prior results on that branch.
```

---

## 9. Component: The Explanation Gate

### Purpose

LLM-driven branches are probabilistic. They will sometimes drift toward counterintuitive
solutions that don't immediately improve the composite metric. The explanation gate
exists to **distinguish productive drift (genuine discovery) from random noise**, before
the coordinator discards the branch's work.

This is the mechanism that allows unique ideas to survive. Without it, the system is
pure metric optimization and loses all benefit of LLM creativity.

### Trigger Conditions

The coordinator triggers `EXPLANATION_REQUEST` when:
- A branch's local metric improved BUT composite metric degraded
- A branch's changes are structurally unusual (large deviation from prior experiments)
- A branch has proposed a `SPAWN_PROPOSAL.md`

### Explanation Template

The branch must respond using a strict structured format:

```markdown
# EXPLANATION_RESPONSE: <branch_id>, cycle <N>

## CLAIM
[One sentence: what I believe is causing the composite regression/anomaly]

## EVIDENCE
[Specific experiment steps and results that support the claim.
Reference your results.tsv rows. Be concrete, not general.]

## PREDICTION
[A falsifiable, automatically testable prediction.
Format: "If [specific condition], then composite oracle will show [specific result].
Test command: [exact shell command the coordinator can run]"]

## ALTERNATIVE
[If prediction fails: fallback approach I will attempt next, with estimated
impact on local metric and expected composite effect]

## RISK ASSESSMENT
[Honestly: how confident am I? What's the worst case if I'm wrong?]
```

### Coordinator Response to Explanation

```
If prediction is testable:
  Run the test command.
  If prediction holds → extend branch runway by M more experiment cycles
                         with guidance from ALTERNATIVE section
  If prediction fails → graceful discard, log as discovery note,
                         update shared_context.md with the finding

If prediction is not testable (vague/untestable):
  No extended runway.
  Log the explanation as a low-confidence discovery note.
  Continue with next-best branch approach.
```

### Rate Limiting

Each branch gets at most **3 explanation chances per macro-round** to prevent a stuck
branch from permanently consuming coordinator cycles through perpetual justification.
After 3 failed gates, the branch is archived.

### Why This Matters: Drift as Feature

Standard optimization systems treat LLM stochasticity as noise to suppress. This system
treats it as **stochastic search in solution space**. Some of the most valuable
research findings come from:

- Misconfigurations that accidentally work better
- Agents trying "wrong" approaches that reveal deeper truths
- Unexpected interactions between independent improvements

The explanation gate is what separates signal from noise in that stochastic exploration.

---

## 10. Component: Shared Discovery Context

### Purpose

Branches run in parallel on isolated files, but they need to share learnings without
creating merge conflicts or blocking each other. The shared discovery context is an
**asynchronous, non-blocking knowledge channel**.

### Structure

Each branch maintains its own local discovery file:
```
discoveries/<branch_id>.md    (branch-local, untracked by branch's git)
```

After each coordinator cycle, the coordinator synthesizes all branch discoveries into:
```
discoveries/shared_context.md    (on integration branch, readable by all)
```

Each branch's `program.md` instructs it to pull and read `shared_context.md` at the
start of each new experiment cycle.

### Example shared_context.md

```markdown
# Shared Context — Coordinator Synthesis, Cycle 7
# Updated: <timestamp>

## Active Branches: bundle_render, network, auth

## Cross-branch findings

### From bundle_render → relevant to: all
Removing moment.js saves 140kb with no functional regression. If your branch
uses date formatting, it now uses Intl.DateTimeFormat (different API surface).

### From network → relevant to: bundle_render
TTFB improved 80ms via cache-control header changes. These headers affect
resource prefetching. If bundle_render is relying on browser-initiated prefetch
for lazy components, verify that caching headers haven't changed prefetch behavior.

### From coordinator
Current composite bottleneck is LCP (bundle_render branch), not TTFB (network branch).
Network branch should avoid changes that increase JS parse time even if TTFB improves.
The composite metric weights are: LCP 60%, TTFB 40% for this run.
```

### What Gets Written to Discoveries

Branches write to their local discovery file when:
- An experiment produces an unexpectedly large improvement
- An experiment crashes or fails in an informative way
- A branch notices something that seems relevant to other branches
- The explanation gate surfaces a counterintuitive finding

---

## 11. Component: Transmutation Keys

### What They Are

Transmutation keys are **distilled heuristics** that the transmuter accumulates over
multiple decomposition sessions. They encode the lessons learned from human corrections,
successful decompositions, and failed branch runs.

They are loaded by the transmuter at the start of every new decomposition session,
enabling it to make better first-pass proposals over time.

### Key Format

```markdown
# transmutation_keys.md

---

[key_001]
session_id: 2026-03-14-web-performance
problem_type: web app performance optimization
learning: >
  Frontend rendering and JS bundle size are almost always coupled.
  Changes to one affect measurement of the other.
  Default: group them into a single branch with composite metric.
  Exception: if the project uses SSR and client bundle separately, they
  may be safe to separate.
human_approved: true
outcome_quality: high        # set retroactively by coordinator after branches complete
composite_improvement: +18%  # set retroactively
added_by: transmuter
added_on: 2026-03-14

---

[key_002]
session_id: 2026-03-15-ml-training-cost
problem_type: ML training optimization
learning: >
  Data pipeline and model architecture have orthogonal failure modes and
  rarely share files. Safe to separate into independent branches.
  However: both branches must use the same evaluation harness or
  composite metric comparison becomes invalid.
human_approved: true
outcome_quality: high
composite_improvement: +22%
added_by: transmuter
added_on: 2026-03-15

---

[key_003]
session_id: 2026-03-16-api-latency
problem_type: API latency reduction
learning: >
  "Improve API latency" almost always contains a hidden coupling between
  database query optimization and caching strategy.
  Proposed separate branches but human merged them. Correct call —
  cache invalidation logic was in the same files as query optimization.
human_approved: true
outcome_quality: pending     # branches still running
composite_improvement: tbd
added_by: transmuter
added_on: 2026-03-16
human_correction: "merged db and cache branches — they share invalidation logic"
```

### Key Lifecycle

| Action | Who Can Do It |
|---|---|
| Add a key | Transmuter (automatically, after session) |
| Mark outcome_quality | Coordinator (retroactively, after branches complete) |
| Delete a key | Human only |
| Downgrade outcome_quality | Human only |
| Flag a key as unreliable | Coordinator (proposes), Human (approves) |

Keys with `outcome_quality: low` are loaded but marked with a warning in the
transmuter's context. They're not deleted because even failed decompositions
teach something.

---

## 12. Execution Infrastructure

### Git Branch Structure

```
main (or master)
├── integration/<run_tag>          ← coordinator's integration branch
├── swarm/<run_tag>/bundle_render  ← branch A
├── swarm/<run_tag>/network        ← branch B
├── swarm/<run_tag>/auth           ← branch C
└── swarm/<run_tag>/auth/query     ← sub-branch (spawned on complexity condition)
```

### GitHub Actions Workflow

Parallel branch execution via matrix jobs:

```yaml
# .github/workflows/swarm.yml

name: Swarm Research

on:
  workflow_dispatch:
    inputs:
      run_tag:
        description: 'Run tag (e.g. mar16)'
        required: true
      branches:
        description: 'Comma-separated branch IDs from decomposition.yaml'
        required: true

jobs:
  branch_research:
    name: Branch ${{ matrix.branch_id }}
    runs-on: [self-hosted, gpu]
    strategy:
      matrix:
        branch_id: ${{ fromJson(inputs.branches) }}
      fail-fast: false  # branches are independent; one failure doesn't kill others

    steps:
      - uses: actions/checkout@v4
        with:
          ref: swarm/${{ inputs.run_tag }}/${{ matrix.branch_id }}

      - name: Run autoresearch agent
        run: |
          # Agent reads program_${{ matrix.branch_id }}.md
          # Runs its autoresearch loop for N rounds
          # Writes results.tsv, discoveries/${{ matrix.branch_id }}.md
        env:
          BRANCH_ID: ${{ matrix.branch_id }}
          PROGRAM_FILE: program_${{ matrix.branch_id }}.md

  coordinator:
    name: Coordinator Cycle
    runs-on: [self-hosted, coordinator]
    needs: branch_research
    if: always()  # run even if some branches failed

    steps:
      - name: Run coordinator agent
        run: |
          # Reads all results.tsv files
          # Runs composite oracle
          # Runs ablation tests
          # Writes coordinator_report.md
          # Updates program_*.md files
          # Triggers next swarm run if not converged
```

### Coordinator Scheduling

The coordinator runs:
- After every N completed branch rounds (N configurable per decomposition)
- On a time schedule (e.g., every 2 hours regardless of branch state)
- On-demand when a branch writes `SPAWN_PROPOSAL.md`

### File Structure Per Run

```
/                                          (repo root)
├── decomposition.yaml                     (transmuter output, human-approved)
├── coordinator_dharma.md                  (human-writable only)
├── transmutation_keys.md                  (accumulates across runs)
├── transmuter.md                          (transmuter's program file)
├── coordinator.md                         (coordinator's program file)
│
├── program_<branch_id>.md                 (per branch, updated by coordinator)
├── SPAWN_PROPOSAL_<branch_id>.md          (written by branch when plateaued)
│
├── discoveries/
│   ├── shared_context.md                  (coordinator synthesis, readable by all)
│   ├── <branch_id>.md                     (branch-local findings)
│   └── archive/                           (findings from completed/archived branches)
│
├── results_<branch_id>.tsv                (per branch experiment log)
├── coordinator_report_<cycle>.md          (per coordinator cycle)
│
└── run.log                                (per branch, overwritten each experiment)
```

---

## 13. Phase Progression: Human → Autonomous

### Phase 1: Human as Oracle

Human is actively involved in every significant decision.

| Decision | Human Involvement |
|---|---|
| Decomposition approval | Required before any branch spawns |
| Metric validation | Required — human confirms oracle captures real goal |
| Branch spawn (new) | Required |
| Coordinator report review | Recommended after each cycle |
| Changes to coordinator.md / transmuter.md | Required |
| Transmutation key quality assessment | Required |

**What happens in Phase 1:**
The system is building its track record. Every human correction is logged. The transmuter
is learning what good decompositions look like. The coordinator is proving its credit
assignment is reliable. This phase may last 5-20 decomposition sessions.

**Graduation condition from Phase 1:**
- Transmuter's first-pass proposals require only minor human edits in >70% of sessions
- Coordinator's credit assignment matches human judgment in retrospective review
- At least 3 completed runs with measurable composite metric improvement

### Phase 2: Human as Board of Directors

Human only gates on structural decisions.

| Decision | Human Involvement |
|---|---|
| Decomposition approval | Human reviews but rarely needs to edit (transmuter has learned) |
| Branch spawn (initial) | Human reviews coordinator recommendation |
| Sub-branch spawn (complexity) | Coordinator decides autonomously |
| Coordinator cycle results | Human monitors dashboard, can intervene |
| Changes to coordinator.md | Required |
| Changes to transmuter.md | Required |
| Changes to dharma | Required |

**What happens in Phase 2:**
Day-to-day coordination is fully automated. The explanation gate runs without human
involvement. Sub-branch spawning happens automatically. Humans receive regular
reports and can veto or redirect at any time.

**Graduation condition from Phase 2:**
- Sub-branch spawning decisions are consistently good (human retrospective agreement >85%)
- Explanation gate correctly identifies real discoveries vs. noise (measurable via
  tracking which gated explanations led to eventual composite improvements)
- System has self-modified coordinator.md and transmuter.md with measurably positive effect

### Phase 3: System Self-Governs

Human sets top-level goals and budget. System executes end-to-end.

| Decision | Human Involvement |
|---|---|
| Decomposition | Human provides problem statement; system does rest |
| All branching decisions | Autonomous |
| Coordinator cycle | Autonomous |
| Changes to coordinator.md / transmuter.md | System proposes, human approves |
| Changes to dharma | Human only, always |
| Budget / goal override | Human can interrupt at any time |

---

## 14. File & Schema Specifications

### decomposition.yaml

```yaml
# decomposition.yaml
# Generated by transmuter, approved by human before deployment.

run_tag: mar16
problem: "Reduce web app cold start time to under 1.5 seconds on 4G"
human_approved_by: <name>
human_approved_on: 2026-03-16T14:30:00Z

composite_metric:
  name: cold_start_score
  oracle: "node bench/e2e_coldstart.js | jq .score"
  direction: higher_is_better
  integration_branch: integration/mar16

branches:
  - id: bundle_render
    description: "Optimize JS bundle size and rendering pipeline"
    owns:
      - webpack.config.js
      - src/components/**
      - src/hooks/**
    read_only:
      - src/api/client.ts     # interface shared with network branch
    metric:
      name: bundle_render_score
      oracle: "node bench/bundle_render.js | jq .score"
      direction: higher_is_better
    coupled_with: []
    max_experiments_before_spawn_check: 10
    initial_context: >
      Focus first on bundle size (quick wins). Then rendering pipeline.
      Avoid changes to src/api/client.ts — the network branch owns the
      interface, you are a consumer only.

  - id: network
    description: "Optimize TTFB, caching, and resource delivery"
    owns:
      - api/**
      - nginx.conf
      - src/api/client.ts
    read_only: []
    metric:
      name: TTFB_ms
      oracle: "node bench/ttfb.js | jq .p50_ms"
      direction: lower_is_better
    coupled_with: []
    max_experiments_before_spawn_check: 10
    initial_context: >
      Focus on cache-control headers first (highest leverage, lowest risk).
      Then API response compression. Avoid changes that increase
      client-side JS parse time — the composite metric weights LCP heavily.

coordinator_schedule:
  after_rounds: 5
  time_interval_hours: 2
  on_spawn_proposal: true

swarm_bounds:
  max_active_branches: 5
  phase: 1
```

### coordinator_report.md (per cycle)

```markdown
# Coordinator Report — Cycle 4, Run: mar16
# Generated: 2026-03-16T20:15:00Z

## Composite Metric
Previous: 0.71  |  This cycle: 0.79  |  Delta: +0.08  |  Direction: IMPROVING

## Branch Contributions (ablation results)
| Branch        | Local metric delta | Marginal composite contribution | Status   |
|---------------|-------------------|--------------------------------|----------|
| bundle_render | +12% score        | +0.06 composite                | KEEP     |
| network       | -8% TTFB          | +0.02 composite                | KEEP     |

## Explanation Gates This Cycle
None triggered.

## Spawn Proposals
None received.

## Recommended program.md Updates
- bundle_render: composite is now bottlenecked by render blocking scripts.
  Suggest prioritizing deferred script loading over further bundle splitting.
- network: positive contribution but diminishing returns on caching headers.
  Suggest exploring HTTP/2 push for critical resources.

## Items Requiring Human Review
None.

## Next Cycle
Scheduled after 5 more branch rounds or in 2 hours, whichever comes first.
```

---

## 15. Feasibility & Risk Analysis

### Component-Level Feasibility

| Component | Feasibility | Key Risk |
|---|---|---|
| Conversational transmuter | High | Metric definition quality — hardest judgment call |
| Parallel git branches | High | File ownership partitioning must be strict |
| Transmutation keys | High | Low-quality keys accumulating and degrading future sessions |
| Coordinator integration testing | Medium | Credit assignment breaks down with >3-4 coupled branches |
| Explanation gate | Medium | LLMs generating convincing but unfalsifiable explanations |
| Dharma enforcement | High | Simplest mechanism; highest safety value per complexity unit |
| Sub-branch spawning | Medium | Risk of premature splits; coordinator judgment needed |
| Full self-improvement loop | Low-Medium | Complexity compounds failure modes at each layer |

### The Metric Problem (Critical Risk)

This is the single largest risk. The entire system depends on every sub-problem having
a computable scalar oracle. In practice:

- For ML/systems problems: oracles are straightforward (benchmark scores, loss metrics)
- For software quality problems: oracles are reasonable (test coverage, error rates)
- For product/UX problems: oracles are proxy metrics that may drift from the real goal
- For creative/research problems: oracles may not exist

**Goodhart's Law applies:** once a metric is a target, it ceases to be a good measure.
Agents optimize the proxy, not the goal. Human review of oracle quality in Phase 1
is specifically designed to catch this before branches are deployed.

### The Coupling Problem

If sub-problems are not truly independent, local hill-climbing per branch does not
guarantee global improvement. Two branches each improving their local metric can
regress the composite.

**Mitigation strategy:** The transmuter's clustering step exists specifically to catch
this. Coupled problems stay on the same branch with a composite metric. The coordinator's
ablation testing catches coupling that slipped through decomposition. Rate-limited
explanation gates handle discovered coupling mid-run.

**The honest limit:** For highly interdependent systems (e.g., a monolith where
everything touches everything), this architecture provides less value. It works best
when the problem genuinely decomposes along ownership boundaries.

### LLM Reliability at Scale

autoresearch works with one agent doing one thing. This system has multiple LLM-driven
agents with interdependencies. Each additional LLM decision point introduces failure
modes: malformed outputs, hallucinated metrics, agents gaming local objectives.

**Mitigation:** Structured output formats for all inter-agent communication. Automatic
validation of oracle commands (they must be runnable shell commands). Dharma as
a hard-coded sanity check. Human oversight in Phase 1 to catch systematic failures
before they compound.

---

## 16. Proof of Concept: What to Build First

Do not build the full system. Build the minimum version that tests the hardest assumption:

> **Can you take one real, moderately complex problem, decompose it into 2-3 branches
> with clean scalar oracles, run them in parallel, and verify that a coordinator
> correctly identifies which branch's changes actually improve the composite metric?**

### Minimum PoC Scope

1. **One real problem** with a genuinely computable composite oracle
2. **2-3 branches** with non-overlapping file ownership and clean per-branch oracles
3. **Manual transmutation** — human writes `decomposition.yaml` directly (no transmuter agent yet)
4. **Parallel branch execution** — run autoresearch agents on each branch
5. **Simple coordinator script** — cherry-picks best commits, runs composite oracle,
   runs ablation (O(N)), writes a report. No LLM needed for the PoC coordinator.
6. **Verify** that the coordinator's credit assignment matches human intuition

### What PoC Validates

- File ownership partitioning is achievable in practice
- Branch metrics actually track sub-problem improvement
- Composite oracle correctly reflects overall goal
- Ablation-based credit assignment identifies real contributors
- Merge conflicts are manageable with strict ownership

### What PoC Does NOT Need

- Transmuter agent (manual YAML writing is fine for PoC)
- Explanation gate (implement after PoC proves basics)
- Transmutation keys (no history yet)
- GitHub Actions (manual triggers are fine for PoC)
- Self-modification of any program file

### Success Criteria for PoC

1. At least one branch finds a genuine improvement to composite metric via its local metric
2. Coordinator correctly identifies which branch contributed positively via ablation
3. Composite oracle produces consistent, meaningful results
4. No unresolvable merge conflicts during coordinator integration

If PoC fails on any of these: you've learned something important cheaply.
If PoC succeeds: the architecture is sound, and adding the remaining components
is engineering work, not research.

---

## 17. Open Problems

These are genuinely unsolved questions that the system will face in practice.

### 1. Proxy Metric Drift
How do you detect when a branch's oracle has drifted from the real goal? Especially
when the drift is gradual. Current mitigation: human review at transmutation time.
But over long runs, the problem may shift while the oracle stays fixed.

### 2. Coordinator Credit Assignment for Interacting Branches
Shapley values give theoretically correct attribution but require O(2^N) composite oracle
runs. Greedy ablation (O(N)) is an approximation. For highly interacting branches,
the approximation may be systematically wrong. No clean solution yet.

### 3. Transmutation Key Quality Decay
A key that was correct in 2026 may be wrong for a different problem domain in 2027.
Keys accumulate but don't decay. Over time, the key set may become large and
partially contradictory. Need a pruning strategy that doesn't require reviewing
every key manually.

### 4. Branch Spawning Criteria
When should a plateaued branch split vs. be archived? The current heuristic (10
experiments with no improvement → spawn proposal) is arbitrary. Better criteria
might involve the shape of the improvement curve, the nature of the plateau
(hard constraint vs. local optimum), or the remaining budget.

### 5. Self-Modification Stability
When the coordinator modifies its own program file (Phase 3), how do you prevent
gradual erosion of good behaviors through small individually-reasonable changes?
Dharma catches explicit violations, but doesn't catch implicit drift.

### 6. The Recursion Question
If the system can improve itself, can it apply this same architecture to the problem
of improving its own architecture? In principle yes — the meta-problem (improve
system performance) decomposes into sub-problems (improve transmuter quality, improve
coordinator credit assignment accuracy, etc.) with computable oracles (avg composite
improvement per run). This is the long-term research question this system opens up.

---

*Document version: 1.0*
*Status: Design — not yet implemented*
*PoC target: Start with Section 16 before building anything else*
