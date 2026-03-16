# Swarm Research System — Design Document v3

> Extended from [autoresearch](https://github.com/karpathy/autoresearch) by @karpathy.
> This version reflects the architectural clarity reached after initial implementation
> and testing. The core shift: explicit compute tiering, a cleaner separation between
> exploration and synthesis, and a deterministic composite score as the system's
> ground truth layer.

---

## Table of Contents

1. [What This System Actually Is](#1-what-this-system-actually-is)
2. [The Core Reframe](#2-the-core-reframe)
3. [Three-Tier Architecture](#3-three-tier-architecture)
4. [Tier One: The Deterministic Layer](#4-tier-one-the-deterministic-layer)
5. [Tier Two: Branch Agents](#5-tier-two-branch-agents)
6. [Tier Three: The Synthesis Layer](#6-tier-three-the-synthesis-layer)
7. [Component: The Transmuter](#7-component-the-transmuter)
8. [Component: The Test Agent](#8-component-the-test-agent)
9. [Component: The Research Agent (Optional)](#9-component-the-research-agent-optional)
10. [The Decision Document](#10-the-decision-document)
11. [The Explanation Gate](#11-the-explanation-gate)
12. [Transmutation Keys](#12-transmutation-keys)
13. [Coordinator Dharma](#13-coordinator-dharma)
14. [Shared Discovery Context](#14-shared-discovery-context)
15. [Phase Progression](#15-phase-progression)
16. [Domain Generality](#16-domain-generality)
17. [PoC: Where to Start](#17-poc-where-to-start)
18. [Honest Limitations](#18-honest-limitations)
19. [Open Problems](#19-open-problems)
20. [Deferred Ideas — Documented for Later](#20-deferred-ideas--documented-for-later)
21. [What Changed from V2](#21-what-changed-from-v2)

---

## 1. What This System Actually Is

A tiered autonomous research system that takes an abstract problem, decomposes it
into independently iterable sub-problems, runs parallel agents on each sub-problem,
and synthesizes results into directed improvements — all governed by a deterministic
composite score that serves as objective ground truth throughout.

The system is not trying to eliminate human judgment. It is trying to replace the
menial, repetitive parts of research — running variations, measuring outcomes,
logging results — with cheap autonomous iteration, while preserving and amplifying
the high-value parts: decomposition, synthesis, and strategic direction.

The end state is a research organization where humans set goals, define success,
and hold veto power — but do not manage day-to-day experimentation.

---

## 2. The Core Reframe

Previous versions of this design treated the coordinator as a component that needed
to be kept cheap and simple. This was wrong. The coordinator — now called the
synthesizer — is the most valuable and cognitively demanding part of the system.
It should be the most powerful component, not the cheapest.

The reframe: **iterations are menial work. Synthesis is the real work.**

This changes the compute allocation fundamentally. Branch agents are running
repetitive, focused experiments. They do not need to understand the whole problem.
They need to understand their sub-problem, generate intelligent variations, measure
outcomes, and report findings clearly. A capable but cheap model is appropriate here.

The synthesizer is reading noisy data across multiple parallel experiments,
identifying what is actually signal versus noise, understanding how branch findings
interact, and generating the next high-level hypothesis. This requires genuine
reasoning ability. A powerful model is appropriate here.

The deterministic composite score sits above both. It requires no model at all —
it is just math. And it is the most important component in the system, because it
is the only one that cannot be fooled, hallucinated, or argued with.

---

## 3. Three-Tier Architecture

```
┌─────────────────────────────────────────────────────────┐
│           DETERMINISTIC COMPOSITE SCORE                  │
│   Ground truth. Always running. Requires no model.       │
│   If this number isn't moving, something is wrong.       │
└───────────────────────────┬─────────────────────────────┘
                            │ governs everything below
┌───────────────────────────▼─────────────────────────────┐
│                  SYNTHESIS LAYER                          │
│   Powerful model. Interprets. Directs. Synthesizes.      │
│   Reads decision doc + branch results + discovery logs.  │
│   Updates guidance per branch. Flags deviations.         │
│   Runs at low cadence. High compute, high value.         │
└──────┬────────────────────┬────────────────────┬────────┘
       │                    │                    │
┌──────▼──────┐    ┌────────▼──────┐    ┌────────▼──────┐
│  BRANCH A   │    │   BRANCH B    │    │   BRANCH C    │
│             │    │               │    │               │
│ Capable but │    │ Capable but   │    │ Capable but   │
│ cheap model │    │ cheap model   │    │ cheap model   │
│             │    │               │    │               │
│ Ingest ctx  │    │ Ingest ctx    │    │ Ingest ctx    │
│ Generate    │    │ Generate      │    │ Generate      │
│ variation   │    │ variation     │    │ variation     │
│ Measure     │    │ Measure       │    │ Measure       │
│ Log results │    │ Log results   │    │ Log results   │
│ + findings  │    │ + findings    │    │ + findings    │
└─────────────┘    └───────────────┘    └───────────────┘
```

Each tier has exactly one job. Each tier uses appropriate compute for that job.
The deterministic layer sits above the intelligent layers as an objective check
on both. This is not a coincidence — the composite score being ungameable and
model-free is the entire point.

---

## 4. Tier One: The Deterministic Layer

### What It Is

A composite scalar score computed from the outputs of all active branches,
combined according to weights set at decomposition time. It runs automatically
after every synthesis cycle. No model is involved in its computation.

### Why It Matters

Every intelligent component in this system — branches, synthesizer, transmuter —
is probabilistic. LLMs can hallucinate, drift, optimize proxies, and generate
convincing but wrong reasoning. The deterministic composite score does none of
these things. It measures what actually happened, expressed as a number.

If a branch claims it improved things but the composite score disagrees, the
composite score is right. If the synthesizer directs branches toward an approach
and the composite score doesn't improve, the direction was wrong. If the system
is working, the composite score moves. If it isn't, it doesn't. No argument,
no explanation, no exception.

### Design Requirements

The composite oracle must be a scriptable command that produces a single scalar.
It must run in a fixed time budget so all cycles are comparable. It must be
defined before any branch is spawned and cannot be redefined mid-run without
human approval and a new baseline measurement. Moving the goalposts invalidates
all prior results.

### Deviation as Warning Signal

Any significant deviation between a branch's local metric improvement and the
composite score movement is an automatic warning signal. This catches two failure
modes: local optimization that hurts the composite (a branch winning the wrong
game), and composite regression from a branch that looked fine locally (hidden
coupling). The deviation signal is what triggers the explanation gate and
informs the synthesizer's credit assignment.

### Metric Normalization

Branches use different oracle types — milliseconds, ratios, counts, index scores.
To make them comparable at the composite level, all branch contributions are
expressed as percentage improvement from a fixed baseline established at
decomposition time. This makes the composite weights (e.g. 60% LCP, 40% TTFB)
meaningful and directly comparable regardless of underlying unit.

Near-zero baseline edge cases are handled with a domain-defined floor — a minimum
meaningful value set at decomposition time — to prevent percentage arithmetic
from becoming unstable or gameable.

---

## 5. Tier Two: Branch Agents

### What They Are

Capable but cost-efficient agents, each scoped to a specific sub-problem defined
by the transmuter. Each branch owns a non-overlapping set of files, optimizes a
single scalar oracle, and operates autonomously within that scope for N iterations
before reporting to the synthesis layer.

### What They Actually Do

The branches are not dumb measurement instruments. They reason about their
sub-problem, form hypotheses, implement changes, evaluate results, and surface
observations. What they do not do is reason about the whole system, make
cross-branch decisions, or redefine their own success criteria. Their autonomy
is real but scoped.

Each iteration a branch agent ingests its current context — its program file,
the shared discovery context, and the synthesizer's latest guidance — then
decides what to try. It implements the change, runs its oracle, and logs the
result along with any observations worth sharing. The loop is tight, cheap,
and repeatable.

### The Form-Filling Optimization

A key implementation insight from early testing: branch agents were making too
many individual tool calls, which is expensive and slow. The solution is to
collapse the mechanical actions (file changes, git operations, oracle execution)
into a single shell command that the agent fills in like a form. The agent's
job is to decide *what* to change — not to manage *how* the change gets applied.
This keeps the expensive part (reasoning) separate from the cheap part (execution)
and dramatically reduces per-iteration cost.

### Iteration Cadence

Branches run 15-20 iterations before the synthesis layer reviews results.
This cadence is not arbitrary — it gives each branch enough runway to find
real signal before triggering a synthesis cycle, without letting branches drift
too far in a bad direction before correction. The cadence is configurable per
decomposition based on how fast the oracle runs and how expensive each iteration is.

### Branch Lifecycle

A branch starts active and runs its loop. If it goes N consecutive iterations
with no local metric improvement, it enters a plateaued state and submits a
spawn proposal to the synthesizer, suggesting either a sub-branch split or an
approach change. The synthesizer decides whether to split, redirect, or archive.

---

## 6. Tier Three: The Synthesis Layer

### What It Is

The upgraded coordinator. A powerful model assigned the job of interpreting
multi-branch results, assigning credit, identifying what is actually signal,
and generating high-level direction for the next round. It runs at low cadence —
once per branch iteration batch — and is the most compute-intensive component
in the system by design.

### Why It Needs to Be Powerful

The synthesizer is doing the cognitively hardest work: reading noisy scalar data
across multiple parallel experiments, understanding how branch findings interact,
spotting hidden coupling, identifying which improvements compose and which
conflict, and generating the next hypothesis. This is not summarization.
It is interpretation and strategic direction. Assigning a weak model to this
layer means the whole system thinks at that level.

### What the Synthesizer Reads

At the start of each synthesis cycle, the synthesizer has access to:
- The decision document (transmuter's decomposition rationale — immutable)
- Per-branch results logs and scalar trajectories
- Per-branch discovery notes (qualitative observations from branches)
- The test agent's scoring report (winner pool and combo scores)
- The composite score delta from this cycle
- Its own previous synthesis reports (continuity)

With this full context, the synthesizer can reason about the system as a whole,
not just individual branch performance.

### What the Synthesizer Produces

After each cycle the synthesizer produces:
- Updated guidance per branch for the next iteration round (specific and actionable)
- Credit assignment (which branches contributed positively to composite)
- Deviation flags (branches with local improvement but composite regression)
- Spawn recommendations (branches to split, redirect, or archive)
- A synthesis report summarizing what actually happened this cycle
- Proposed additions to the transmutation keys based on this run's learnings

### Relationship to Deterministic Layer

The synthesizer interprets. The composite score judges. If the synthesizer's
direction leads to composite improvement, the direction was right. If it doesn't,
the direction was wrong — regardless of how reasonable the synthesizer's reasoning
sounded. The deterministic layer is the final arbiter. The synthesizer serves it,
not the other way around.

---

## 7. Component: The Transmuter

### Role

A conversational LLM agent that takes an abstract problem and produces an approved
decomposition plan before any branches are spawned. It operates as a dialogue with
the human, asking clarifying questions until it can define clean oracles and
non-overlapping ownership for each branch. No branch runs without human sign-off
on the full decomposition.

### Why Conversational

Decomposition quality is the highest-leverage input to the entire system. A bad
oracle poisons every downstream component. A poorly partitioned ownership boundary
causes merge conflicts and hidden coupling that the synthesizer then has to untangle
for the rest of the run. Human conversation is the quality gate before any compute
is spent. The transmuter proposes; the human disposes.

### Hard Rules

Every branch must have a scriptable oracle. If a shell command cannot be written
that produces a single scalar, the sub-problem is not ready to branch. It must be
decomposed further or excluded from this run.

Semantically coupled sub-problems must be grouped into a single branch with a
composite local metric. Two sub-problems are coupled if changing one materially
affects measurement of the other. The transmuter is responsible for catching this
at decomposition time. The synthesizer catches what slips through.

File ownership must be non-overlapping. Every file in scope belongs to at most one
branch. Files in no branch's ownership are read-only for all branches.

The system starts with a maximum of five branches. Sub-branches can be spawned
later by the synthesizer if complexity demands. Starting small keeps the system
manageable and debuggable while the first few runs build confidence.

### Transmutation Keys

At the start of every decomposition session, the transmuter loads the current
working-memory tier of transmutation keys — a distilled set of heuristics from
past runs. These inform the transmuter's first-pass proposals and help it catch
known coupling patterns, bad oracle choices, and ownership partition mistakes
that have been observed in previous sessions.

---

## 8. Component: The Test Agent

### Role

A dedicated evaluation layer that sits between the branches and the synthesizer.
Its job is to pre-filter the candidate space so the synthesizer only evaluates
a small, high-quality winner pool rather than the raw output of every branch iteration.

### Critical Design Rule

The test agent writes and owns all test scripts. Branches do not write their own
tests. An agent that writes its own evaluation will, not necessarily maliciously
but probabilistically, write one that favors its own output. The test agent
authors the evaluation independently, based on the branch's stated prediction
but not controlled by the branch.

### What It Does

After each branch iteration batch, the test agent collects all variants from all
branches, runs them against its test suite, and scores each one. It then identifies
the top performers per branch and generates cross-branch combinations — testing
whether improvements from different branches compose at the composite level.
This combo testing is a form of genetic recombination: checking not just which
branch won but whether the winners can be combined into something better than any
individual branch found alone.

The test agent produces a scoring report that the synthesizer reads as its primary
input. This report includes per-variant scores, the winner pool, the best performing
cross-branch combinations, failed variants with failure reasons, and any anomalies
where local improvement diverged significantly from composite score movement.

### Test Suite Maintenance

Test scripts are updated between rounds, never mid-round. Updates are proposed
by the test agent when a major architectural change invalidates existing tests,
and reviewed by the synthesizer before taking effect. The test suite is a shared
asset that no individual branch can influence unilaterally.

---

## 9. Component: The Research Agent (Optional)

### Role

A web-search-backed LLM agent that provides grounded external context before and
during a run. It is explicitly optional — problems with well-defined solution spaces
may not need it. It runs at low frequency and never inline with branch iterations.

### What It Adds

For problems where relevant prior work exists, the research agent provides a
literature-backed starting point so branches begin from a reasonable floor rather
than hallucinated baselines. It can validate whether a branch's approach is
already known and documented, surface known failure modes of existing approaches,
and suggest baseline values for oracle targets drawn from published benchmarks.

### How It Is Framed

The research agent informs, it does not anchor. Its output is framed as relevant
approaches and their documented limitations, along with gaps in the literature —
what has not been tried. Branches should explore beyond published solutions.
Research output is a floor and a sanity check, not a target. If the research agent
leads branches to simply re-implement known solutions, it has failed its purpose.

### Failure Mode Caveat

The research agent creates an external dependency. It runs only at decomposition
time and at synthesis cycles — never inline with branch iterations. Failure of
the research agent must not block branch execution. It is advisory, not structural.

---

## 10. The Decision Document

### What It Is

A structured document produced by the transmuter at decomposition time and shared
with the synthesizer throughout the run. It captures the reasoning behind the
decomposition — not just what was decided but why.

### Why It Exists

The synthesizer currently receives scalars and findings but not the original
intent. This is like handing someone a spreadsheet of experimental results without
the experimental design. The synthesizer can identify which branch improved but
cannot reason about whether that improvement actually matters to the original
problem without understanding why the problem was split this way in the first place.

### Structure

The decision document has two sections with different mutability:

The immutable section is written once by the transmuter and never changed. It
contains the problem statement and the reasoning behind how it was decomposed,
what each branch is actually optimizing for and why, known coupling risks the
transmuter identified during decomposition, and what composite success looks like
in concrete terms. This section gives the synthesizer the original intent throughout
the run regardless of how many cycles have passed.

The mutable section is maintained by the synthesizer and updated after each cycle.
It contains what approaches have been tried and failed across branches, cross-branch
findings worth knowing, the current bottleneck in the composite metric, and specific
guidance per branch for the next round. Branches read this section only —
they get the synthesizer's latest direction without needing to parse the full history.

This division means the synthesizer always has full context of original intent,
branches always have the latest actionable guidance, and neither is polluted by
what belongs to the other.

---

## 11. The Explanation Gate

### Purpose

The mechanism that distinguishes genuine discovery from noise when a branch's
local metric improvement diverges from composite score movement. Without it,
the system is pure metric optimization with no benefit from the creative and
exploratory capacity of LLM agents. With it, counterintuitive findings that can
be explained and tested are preserved rather than discarded.

### v3: Binary, Single Chance

The gate is strict. One prediction, one test, one result.

When the synthesizer flags a branch for explanation, the branch states a single
falsifiable claim: what it believes is happening and what specific measurable
outcome would confirm it. The test agent then writes and runs a test script based
on that claim. The branch cannot influence the test methodology. The result is
binary — the prediction holds or it does not.

If the prediction holds, the branch earns extended runway with the synthesizer's
guidance. If the prediction fails, the branch is gracefully archived and its
findings are logged as a low-confidence discovery note. One chance, clean outcome,
no perpetual justification loops.

### Why Strict

A softer gate with multiple chances creates an incentive for branches to generate
convincing but unfalsifiable explanations to buy time. LLMs are good at this.
The binary gate eliminates the incentive entirely — either the prediction survives
a test or it doesn't, and no amount of rhetorical quality changes that.

---

## 12. Transmutation Keys

### What They Are

Distilled heuristics that accumulate across decomposition sessions, encoding lessons
learned from human corrections, successful runs, and failed experiments. Loaded by
the transmuter at the start of every new session, they allow the system to make
better first-pass decomposition proposals over time.

### Consolidation

After every N sessions, a consolidation pass runs on the key set. Semantically
similar keys are clustered. High-confidence keys that agree are merged.
Contradictions are flagged for human review. A staleness signal is applied —
keys not confirmed in recent sessions have their last-confirmed date updated only
when the key's advice proves out in a subsequent run.

The result is two tiers: a working memory of high-confidence recently-confirmed
keys that are injected into the transmuter's prompt, and a long-term archive of
lower-confidence or older keys that are searched only when the working memory does
not cover the current problem type. This prevents unbounded prompt growth while
preserving the accumulated learning.

### Governance

Keys can be added automatically by the transmuter after a session. Keys can only
be deleted or quality-downgraded by humans. The synthesizer can update outcome
quality scores retroactively and flag keys as potentially unreliable, but human
approval is required before a flag becomes a downgrade. Learning accumulates in
one direction only — bad keys are flagged and archived, not silently purged.

---

## 13. Coordinator Dharma

The immutable constitution of the system. No agent can modify it. Changes require
explicit human approval with version-controlled sign-off. It is loaded at the start
of every synthesis cycle and checked before every action. It is the fixed point
that prevents recursive self-improvement from destabilizing the system.

### Core Principles

**Oracle Primacy.** The composite score is ground truth. A local win that regresses
the composite is not a win. No exceptions without explicit human override.

**Evidence Over Rhetoric.** An explanation earns extended runway only if it produces
a falsifiable, automatically testable prediction. A prediction without a test command
earns nothing.

**Swarm Bounds.** Maximum five active branches during Phase 1 and Phase 2.
Exceeding this limit requires explicit human approval.

**Self-Modification Gate.** Any proposed change to the synthesizer's program file,
the transmuter's program file, or this dharma document requires human approval
before being applied. The system proposes; humans dispose.

**Transmutation Key Integrity.** Keys accumulate automatically. Deletion and
quality downgrade are human-only actions. Learning moves in one direction only.

**Discovery Preservation.** Findings that fail the composite test but survive the
explanation gate are logged as discoveries, not discarded. Counterintuitive results
with valid explanations are scientifically valuable even when they don't immediately
improve the composite.

**Human Override.** A human can always override any system decision at any phase.
Overrides are documented and tracked as signal for future learning. They are not
penalized.

**Metric Definition Is Sacred.** A branch's oracle cannot be redefined after the
branch is active without human approval and a new baseline measurement.

---

## 14. Shared Discovery Context

Branches run in parallel on isolated files but share learnings asynchronously.
No blocking, no merge conflicts.

Each branch maintains its own local discovery file where it logs unexpected
findings, informative failures, and observations relevant to other branches.
After each synthesis cycle, the synthesizer reads all branch discovery files
and synthesizes them into a shared context document that all branches read at
the start of their next iteration round.

This is not just a summary. The synthesizer actively interprets cross-branch
findings — noting when a discovery from one branch affects the valid approach
space for another, flagging when two branches are inadvertently working against
each other, and highlighting which findings upgrade or downgrade confidence in
existing assumptions.

---

## 15. Phase Progression

### Phase 1: Human as Synthesizer

The human does manually what the synthesis layer will eventually do automatically.
No LLM coordinator yet. This is not a simplified prototype of the system —
it is the correct first phase. You learn what to automate by doing it.

The branches run autonomously. The human reads results, picks winners, runs the
composite oracle manually, identifies which branch contributed what, and writes
updated guidance for the next round. The transmuter helps with decomposition.
The test agent may or may not exist yet — the human can fill that role too.

This phase lasts until manual synthesis becomes the bottleneck and you understand
it well enough to automate it. Target: at least three completed runs where the
human's manual credit assignment matches what an ablation script would have
produced. That's when you know the pattern is reliable enough to hand off.

### Phase 2: Deterministic Coordinator Script

Replace human synthesis with a deterministic script. No LLM yet — just
cherry-pick plus composite oracle plus greedy ablation. Human reviews reports
and overrides as needed. This phase proves that the credit assignment logic
is sound before adding model-based reasoning on top of it.

### Phase 3: LLM Synthesizer and Test Agent

The coordinator script becomes a powerful LLM synthesizer. The test agent is
added. Human gates on structural decisions only — decomposition approval, branch
spawns, dharma changes, and veto on major synthesis decisions.

### Phase 4: Full System

Research agent, transmutation key consolidation, sub-branch spawning, and
self-modification proposals. Human sets goals, defines success, and holds veto.
The system executes end to end.

---

## 16. Domain Generality

The architecture is domain-agnostic at its core. The branch agents stop being
"agents that modify code" and become something more general: agents that generate
variation in a parameter space and report scalar outcomes. The domain lives in
the oracle definition and the file ownership structure — not in the agents themselves.

This means the same architecture applies to:
- Codebase optimization (the original domain)
- Trading strategy development (signal generation, risk management, execution as branches)
- Prompt optimization (prompt variants as iterations, task performance as oracle)
- ML training pipelines (architecture, data, optimization as branches)
- Any problem that can be expressed as a feedback loop with a measurable output

The transmuter's job is to translate the abstract problem into that form.
Once that translation exists, the rest of the system runs identically regardless
of domain. This is the deeper value of strict oracle discipline — it is not just
a quality gate, it is what makes the system generalizable.

The honest boundary: problems where oracles genuinely do not exist — deeply
subjective creative problems, open-ended strategic decisions, anything where
the goal cannot be expressed as a scalar — remain outside scope. The system
does not solve the hard problem of measurement. It amplifies the power of
measurement where measurement already exists.

---

## 17. PoC: Where to Start

Do not build the full system. Build the minimum version that tests the hardest
assumption: can you decompose a real problem into two or three branches with
clean oracles, run them in parallel, and verify that combining the winners
actually improves the composite metric?

**You are the synthesizer in the PoC.** You pick winners, you run the composite
oracle, you write the updated guidance. This is not a shortcut — it is Phase 1
by design.

**Start with a problem you can evaluate by reading the output.** If you need to
run complex infrastructure to know if the result is better, the feedback loop is
too slow for early experiments. A deliberately broken Python file, a simple
backtest with weak rules, a tiny service with obvious inefficiencies — these
give you instant intuition about whether the system is finding real improvements
or gaming the oracle.

**Make the problem broken in known ways.** You control the ground truth. You know
what the right answer looks like. This means you can verify that the system found
it rather than just hoping the oracle is right. Designed problems are better than
real problems for the first few runs.

**Run branches serially if needed.** Parallel execution is nice but not required
for the PoC. The point is to validate that the decomposition is clean and the
improvements compose — not to optimize wall-clock time.

**Success criteria:** at least one branch finds a genuine local improvement,
at least one cross-branch combination improves the composite, you can identify
which branch contributed what, and there are no unresolvable merge conflicts.
If all four hold, the architecture is sound and adding layers is engineering work.

---

## 18. Honest Limitations

**The oracle problem is the ceiling.** Everything depends on measurable scalars.
The system is powerful inside measurable domains and unreliable outside them.
Goodhart's Law applies — once a metric is a target, it ceases to be a good measure.
Human validation of oracle quality at decomposition time is not optional.

**Coupling reveals itself late.** The transmuter tries to catch coupling at
decomposition time, but coupling often surfaces during experiments rather than
before them. The synthesizer catches mid-run coupling through ablation, but by
then branches have already diverged. This is a manageable cost, not a fatal flaw,
but it means the first run on any new problem type will likely discover coupling
that the transmuter missed.

**The synthesis layer is a single point of failure.** With intelligence centralized
at the synthesis level, a bad high-level call propagates to all branches.
The deterministic composite score is the primary mitigation — it will catch
a bad synthesis direction within one cycle. But that cycle costs compute.

**Test agent quality determines system quality.** If the test agent writes a bad
test suite, the entire system optimizes toward the wrong thing with high confidence.
Human validation of the test suite before major runs is not optional in early phases.

**The system is as fast as its slowest oracle.** If the composite oracle takes
twenty minutes to run, synthesis cycles take twenty minutes minimum. Oracle
design is not just a correctness problem — it is a speed problem.

---

## 19. Open Problems

**Proxy Metric Drift.** How do you detect when a branch's oracle has drifted from
the real goal over a long run? Oracle validation is a deployment-time check, not
a continuous one. Long runs on evolving problems may drift without triggering
any automatic warning.

**Credit Assignment for Interacting Branches.** Greedy ablation is an O(N)
approximation of theoretically correct Shapley value attribution, which is O(2^N).
For highly interacting branches the approximation may be systematically wrong.
No clean solution at reasonable compute cost yet.

**Transmutation Key Cross-Domain Contamination.** A key learned in one domain may
be incorrect or misleading for a different domain. Domain tagging helps but does
not fully solve this. A key about ML training coupling learned from one session
could incorrectly anchor the transmuter on a web performance problem.

**Branch Spawning Criteria.** When should a plateaued branch split versus be archived?
The iteration-count heuristic is arbitrary. The shape of the improvement curve,
the nature of the plateau, and the remaining run budget are all more informative
signals that are not yet used systematically.

**Self-Modification Stability in Later Phases.** When the synthesizer proposes
changes to its own program file, how do you prevent gradual erosion of good
behaviors through individually-reasonable small changes? Dharma catches explicit
violations but not implicit drift over many cycles.

**The Recursion Question.** Can this architecture be applied to improving itself?
The meta-problem — improve system research performance — decomposes into
sub-problems with computable oracles: transmuter decomposition quality,
synthesizer credit assignment accuracy, test agent coverage quality.
This is theoretically within scope and is the long-term research question
the architecture opens up.

---

## 20. Deferred Ideas — Documented for Later

These are ideas with clear value that are not being implemented now.
They are captured here so they don't get lost, not because they are urgent.
Revisit once the core pipeline is stable and the first real synthesis cycle has run.

---

### Drift Detection Between Local and Composite Score

The core signal to watch: when a branch's local metric improves but its marginal
contribution to the composite score is flat or negative, the branch is winning the
wrong game.

The mechanism is a greedy ablation run after each synthesis cycle — O(N) composite
oracle runs, one per branch. For each branch, revert its changes and re-run the
composite. The difference is that branch's marginal contribution. Drift is then
simply local improvement minus marginal contribution.

Two thresholds matter, not one. A warning threshold catches branches that are locally
improving but not moving the composite — the synthesizer adds a note to their guidance.
A critical threshold catches branches actively regressing the composite — this triggers
the explanation gate.

Single-cycle drift can be noise. What's more useful is the trend across cycles.
A branch that drifts consistently over three cycles has a fundamentally different
status than one that had a single anomalous cycle after a structural change.

The honest caveat: greedy ablation assumes branches are roughly independent.
For coupled branches the marginal contribution calculation is an approximation.
The transmuter catching coupling at decomposition time is the primary defense.
Drift detection is the backstop.

---

### Adaptive Iteration Depth

Currently iteration depth is a fixed number set at decomposition time.
The right design is adaptive — the transmuter sets a budget range based on
problem complexity, oracle speed, and expected variance, and the synthesizer
adjusts it each cycle based on what's actually happening.

Factors the transmuter should use to set the initial budget range:

Problem complexity scales with ownership scope — a branch owning many files with
a composite local metric needs more iterations to converge than a narrowly scoped
branch. Oracle speed determines how many iterations fit in a wall-clock budget.
Expected variance, informed by transmutation key history for similar problem types,
determines how many iterations are needed to separate signal from noise.

The synthesizer should reduce iteration depth in later cycles (convergence phase)
and can increase it for branches showing strong positive composite contribution
(they have earned more runway). Early cycles explore, late cycles converge.

A reasonable structure for the decomposition yaml:

```
iteration_budget:
  initial_rounds: 15
  min_rounds: 8
  max_rounds: 40
  time_budget_minutes: 30
  extension_policy: request_based
```

---

### Agent-Requested Iteration Extensions

Before hitting their iteration limit, branches can request additional iterations
if they are making meaningful progress. The request is lightweight — a structured
signal, not an essay.

```
EXTENSION_REQUEST
branch: <id>
current_local_delta: <pct>
trend: improving_consistently | improving_erratically | plateauing | reversing
confidence: high | medium | low
reason: <one line>
requested_additional_iterations: <N>
```

The synthesizer evaluates requests relative to each other, not in isolation.
If two branches both request extensions but only one can be granted, the one
with higher marginal composite contribution wins — regardless of which has the
better local story. A branch with a compelling local narrative but weak composite
contribution gets deprioritized over a branch quietly moving the composite needle.

A hard cap set by the transmuter at decomposition time applies to all extensions.
No branch can exceed this cap regardless of how many requests it makes or how
good its case looks. This prevents a single optimistic branch from consuming the
entire run budget.

---

### Token Consumption and Cost Per Cycle

At approximately 5k tokens per agent per API call for simple tests, the cost
structure across tiers looks roughly like this — using current approximate
model pricing as reference:

Branch agents run on cheap fast models. At roughly $0.25 per million input tokens,
15 iterations per branch costs around $0.02 per branch per round. Three branches
for one round is approximately $0.06. This tier dominates iteration count but
not cost.

The test agent runs on a mid-tier model with a larger input context (all branch
results plus test suite). Approximately $0.08 per synthesis cycle.

The synthesizer runs on a powerful model with the largest input context — decision
document, all branch results, test report, discovery logs. Approximately $0.68
per synthesis cycle. This is roughly 80% of total spend per cycle, which validates
the compute tiering decision. The money is being spent where the reasoning happens.

A full run of 10 synthesis cycles with 3 branches costs approximately $8-10.
Scaled to 5 branches and 20 iterations per round, approximately $12-15 per run.
These are manageable numbers for the value produced.

The main levers for reducing cost further: git and shell operations collapsed
into form-filling (already being implemented, saves 30-40% of branch token count),
structured results logs passed as tables rather than prose summaries, tiered
context loading so branches only receive their program file and mutable guidance
mid-round rather than full context every iteration, and a cheap summarization
pass on discovery logs before they reach the synthesizer.

Realistically branch cost can be reduced to 2-3k tokens per iteration with these
optimizations. Synthesizer cost is harder to reduce because the input context is
legitimately large — that is where the tokens should be spent.

---

## 21. What Changed from V2

| Topic | V2 | V3 |
|---|---|---|
| Coordinator role | Coordinator with reduced load | Renamed synthesizer, explicitly the most powerful component |
| Compute allocation | Not explicitly addressed | Cheap branches, powerful synthesizer, deterministic ground truth |
| Branch agent framing | Risk of becoming dumb instruments | Capable and scoped — autonomy within sub-problem, not across system |
| Ground truth layer | Composite oracle as one component | Deterministic composite score as its own architectural tier |
| Decision document | Not present | Explicit component bridging transmuter intent to synthesizer context |
| Context sharing | Synthesizer pushes to branches | Structured split: immutable intent + mutable guidance per branch |
| Phase 1 | Human reviews coordinator reports | Human IS the synthesizer — doing the job before automating it |
| Domain framing | Primarily code problems | Explicitly domain-agnostic once oracle is defined |

---

*Document version: 3.1*
*Status: Pipeline implemented and under active testing*
*PoC phase: Branch iteration loop operational, CI synchronization in progress*
*Next milestone: Stable synthesis cycle on first real problem*
