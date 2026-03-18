"""
Transmuter — Problem Decomposition & Task Orchestration pipeline.

6-stage pipeline:
  Stage 1: Parse input            (deterministic)
  Stage 2: Classify template      (keyword match, LLM fallback)
  Stage 3: Decompose into tasks   (LLM-assisted)
  Stage 4: Generate artifacts     (deterministic template fill)
  Stage 5: Human checkpoint       (interactive CLI)
  Stage 6: Output & exit          (deterministic)

Usage:
  # Spec mode (no LLM needed):
  python agents/transmuter.py --spec config/my_spec.yaml --run_tag tx_001

  # NL mode (LLM decomposes problem):
  python agents/transmuter.py --problem "Optimize sorting for integer arrays" --run_tag tx_001

  # Auto mode (skip human checkpoint):
  python agents/transmuter.py --problem "..." --run_tag tx_001 --auto
"""
import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / "keys.env")
except Exception:
    pass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TaskSpec:
    task_id: str
    template: str                     # "perf_benchmark", "finance_strategy", "custom"
    solution_file: str                # "solutions/sort.py"
    metric_name: str                  # "sort_time_ms"
    metric_direction: str             # "lower_is_better"
    contract: str                     # "def sort(arr: list) -> list"
    goal_description: str             # "Sort integer array efficiently"
    oracle_command: str               # resolved from template
    oracle_metric_pattern: str        # "^sort_time_ms:"
    ideas: list[str] = field(default_factory=list)
    stdlib_only: bool = True


# ---------------------------------------------------------------------------
# Template classification (Stage 2)
# ---------------------------------------------------------------------------

TEMPLATE_KEYWORDS = {
    "perf_benchmark": [
        "optimize", "faster", "performance", "speed", "timing", "benchmark",
        "sort", "search", "filter", "latency", "throughput",
    ],
    "finance_strategy": [
        "sharpe", "strategy", "trading", "portfolio", "returns", "backtest",
        "ma", "moving average", "finance", "signal", "nifty",
    ],
}

# Template → default oracle routing
TEMPLATE_ORACLE = {
    "perf_benchmark": {
        "oracle_command": "python3 oracles/evaluate.py --branch {task_id} --mode {mode}",
        "metric_pattern": "^{metric_name}:",
        "metric_suffix": "_time_ms",
        "metric_direction": "lower_is_better",
    },
    "finance_strategy": {
        "oracle_command": "python3 oracles/evaluate_finance.py --mode {mode}",
        "metric_pattern": "^{metric_name}:",
        "metric_suffix": "_sharpe_neg",
        "metric_direction": "lower_is_better",
    },
}


def classify_template(problem_text: str) -> tuple[str, float]:
    """Keyword-based template classification. Returns (template_name, confidence)."""
    text_lower = problem_text.lower()
    scores = {}
    for template, keywords in TEMPLATE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        scores[template] = score

    best = max(scores, key=scores.get)
    total_keywords = len(TEMPLATE_KEYWORDS.get(best, []))
    confidence = scores[best] / max(total_keywords, 1)

    if scores[best] == 0:
        return "custom", 0.0
    return best, confidence


def classify_template_llm(problem_text: str, model: str, client) -> str:
    """LLM fallback for template classification."""
    templates = list(TEMPLATE_KEYWORDS.keys())
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You classify optimization problems into task templates. "
                    f"Available templates: {templates}. "
                    "If none fit, respond with 'custom'. "
                    "Respond with ONLY the template name, nothing else."
                ),
            },
            {"role": "user", "content": problem_text},
        ],
        max_tokens=50,
    )
    result = (response.choices[0].message.content or "").strip().lower()
    if result in templates or result == "custom":
        return result
    return "custom"


# ---------------------------------------------------------------------------
# LLM decomposition (Stage 3)
# ---------------------------------------------------------------------------

DECOMPOSITION_SYSTEM_PROMPT = """\
You decompose optimization problems into concrete tasks for an autonomous agent swarm.

Each task must have:
- id: short snake_case identifier
- description: one-line goal
- solution_file: path under solutions/
- contract: Python function signature the solution must implement
- metric_name: metric column name (e.g. sort_time_ms)
- template: one of {templates}
- ideas: 2-4 domain-specific optimization hints

Rules:
- Start with 1-2 tasks max (simplicity over breadth)
- metric_name should end with the template's suffix (e.g. _time_ms for perf_benchmark)
- solution_file must be under solutions/
- contract must be a valid Python function signature

Respond with ONLY valid JSON matching this schema:
{{
  "tasks": [
    {{
      "id": "sort",
      "description": "Optimize integer array sorting",
      "solution_file": "solutions/sort.py",
      "contract": "def sort(arr: list) -> list",
      "metric_name": "sort_time_ms",
      "template": "perf_benchmark",
      "ideas": ["Use built-in list.sort()", "Avoid extra allocations"]
    }}
  ],
  "composite_weights": {{"sort": 1.0}}
}}
"""

FEW_SHOT_EXAMPLES = [
    {
        "role": "user",
        "content": "Optimize sorting for integer arrays",
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "tasks": [{
                "id": "sort",
                "description": "Optimize integer array sorting",
                "solution_file": "solutions/sort.py",
                "contract": "def sort(arr: list) -> list",
                "metric_name": "sort_time_ms",
                "template": "perf_benchmark",
                "ideas": ["Use built-in list.sort()", "Avoid extra allocations", "Consider input characteristics"],
            }],
            "composite_weights": {"sort": 1.0},
        }),
    },
    {
        "role": "user",
        "content": "Optimize MA crossover strategy on NIFTY50 daily data",
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "tasks": [{
                "id": "finance",
                "description": "Optimize MA crossover trading strategy for best risk-adjusted returns",
                "solution_file": "solutions/finance_ma.py",
                "contract": "def compute_signal(prices: list[float]) -> list[float]",
                "metric_name": "finance_sharpe_neg",
                "template": "finance_strategy",
                "ideas": [
                    "Tune short/long MA windows",
                    "Add RSI filter for entry timing",
                    "Avoid lookahead — signals must be causal",
                ],
            }],
            "composite_weights": {"finance": 1.0},
        }),
    },
]


def decompose_with_llm(problem_text: str, template: str, model: str, client) -> dict:
    """Use LLM to decompose a problem into tasks. Returns parsed JSON."""
    templates = list(TEMPLATE_KEYWORDS.keys())
    system = DECOMPOSITION_SYSTEM_PROMPT.format(templates=templates)

    messages = [
        {"role": "system", "content": system},
        *FEW_SHOT_EXAMPLES,
        {"role": "user", "content": problem_text},
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=8192,
    )

    msg = response.choices[0].message
    raw = (msg.content or "").strip()

    # If model used tool_calls instead of content, try extracting from tool_calls
    if not raw and getattr(msg, "tool_calls", None):
        for tc in msg.tool_calls:
            args = getattr(tc.function, "arguments", "") if hasattr(tc, "function") else ""
            if args:
                raw = args
                break

    if not raw:
        raise ValueError(f"LLM returned empty content. Full response: {response}")

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    return json.loads(raw)


# ---------------------------------------------------------------------------
# Artifact generation (Stage 4)
# ---------------------------------------------------------------------------

def resolve_oracle_config(task: TaskSpec) -> TaskSpec:
    """Fill oracle_command and oracle_metric_pattern from template defaults if empty."""
    tmpl_cfg = TEMPLATE_ORACLE.get(task.template, {})

    if not task.oracle_command and tmpl_cfg:
        task.oracle_command = tmpl_cfg["oracle_command"].format(
            task_id=task.task_id, mode="{mode}"
        )

    if not task.oracle_metric_pattern and tmpl_cfg:
        task.oracle_metric_pattern = tmpl_cfg["metric_pattern"].format(
            metric_name=task.metric_name
        )

    return task


def build_task_specs(decomposition: dict, default_template: str) -> list[TaskSpec]:
    """Convert LLM decomposition JSON into TaskSpec objects."""
    specs = []
    for t in decomposition.get("tasks", []):
        template = t.get("template", default_template)
        tmpl_cfg = TEMPLATE_ORACLE.get(template, {})
        metric_name = t.get("metric_name", f"{t['id']}_metric")

        spec = TaskSpec(
            task_id=t["id"],
            template=template,
            solution_file=t.get("solution_file", f"solutions/{t['id']}.py"),
            metric_name=metric_name,
            metric_direction=tmpl_cfg.get("metric_direction", "lower_is_better"),
            contract=t.get("contract", f"def {t['id']}()"),
            goal_description=t.get("description", ""),
            oracle_command="",
            oracle_metric_pattern="",
            ideas=t.get("ideas", []),
            stdlib_only=True,
        )
        spec = resolve_oracle_config(spec)
        specs.append(spec)
    return specs


def generate_program_md(spec: TaskSpec, root: Path) -> str:
    """Generate program.md content from template."""
    tmpl_path = root / "config" / "templates" / spec.template / "program.md.tmpl"
    if not tmpl_path.exists():
        # Fallback: generate a minimal program.md
        return _minimal_program_md(spec)

    tmpl = tmpl_path.read_text()
    ideas_block = "\n".join(f"- {idea}" for idea in spec.ideas) if spec.ideas else "- (explore approaches)"
    stdlib_note = "" if spec.stdlib_only else " (external packages allowed)"

    return tmpl.format(
        task_id=spec.task_id,
        solution_file=spec.solution_file,
        metric_name=spec.metric_name,
        contract=spec.contract,
        goal_description=spec.goal_description,
        ideas_block=ideas_block,
        stdlib_note=stdlib_note,
    )


def _minimal_program_md(spec: TaskSpec) -> str:
    """Generate a minimal program.md when no template exists."""
    ideas = "\n".join(f"- {idea}" for idea in spec.ideas) if spec.ideas else "- (explore approaches)"
    return f"""# Branch: {spec.task_id} (TRANSMUTE-SWARM)

You are the {spec.task_id}-branch agent.

## Scope
- **You own only** `{spec.solution_file}`.
- Do not modify oracle files or other solution files.

## Goal
Minimize `{spec.metric_name}` (lower is better). {spec.goal_description}
Contract: `{spec.contract}`

## Ideas
{ideas}

## Rules
- Do not call oracle scripts, git commands, or write TSVs directly.
- `run_experiment.sh` handles git + results (called internally by the `experiment` tool).
- After iterations, reply `DONE` and summarize best metric + key change.
"""


def generate_scaffold(spec: TaskSpec, root: Path) -> str:
    """Generate solution scaffold from template."""
    tmpl_path = root / "config" / "templates" / spec.template / "scaffold.py.tmpl"
    if not tmpl_path.exists():
        return f'{spec.contract}:\n    """Baseline implementation — optimize this."""\n    raise NotImplementedError("Replace with your implementation")\n'

    tmpl = tmpl_path.read_text()
    return tmpl.format(
        task_id=spec.task_id,
        contract=spec.contract,
        metric_name=spec.metric_name,
    )


def update_task_registry(specs: list[TaskSpec], root: Path) -> None:
    """Merge new task entries into config/task_registry.yaml.

    Only adds tasks that don't already exist in the registry.
    Existing tasks are left untouched to preserve manual edits.
    """
    registry_path = root / "config" / "task_registry.yaml"
    if registry_path.exists():
        with open(registry_path) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    tasks = data.setdefault("tasks", {})
    for spec in specs:
        if spec.task_id in tasks:
            continue  # Don't overwrite existing entries
        # Ensure oracle_command has {mode} placeholder for registry
        oracle_cmd = spec.oracle_command
        if "{mode}" not in oracle_cmd:
            # Try to restore the placeholder from resolved commands
            for mode_val in ("full", "quick", "baseline"):
                if mode_val in oracle_cmd:
                    oracle_cmd = oracle_cmd.replace(mode_val, "{mode}", 1)
                    break
        tasks[spec.task_id] = {
            "solution_file": spec.solution_file,
            "metric_name": spec.metric_name,
            "metric_direction": spec.metric_direction,
            "oracle_command": oracle_cmd,
            "oracle_metric_pattern": spec.oracle_metric_pattern,
            "tsv_header": f"commit\t{spec.metric_name}\tmemory_gb\tstatus\tdescription\tlog",
        }

    with open(registry_path, "w") as f:
        # Write a comment header, then the YAML
        f.write("# Task registry — single source of truth for all task configurations.\n")
        f.write("# Auto-generated/updated by transmuter.py. Manual edits are fine.\n\n")
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def generate_decomposition_yaml(specs: list[TaskSpec], composite_weights: dict, run_tag: str, problem: str, root: Path) -> Path:
    """Write config/decomposition.yaml for this run."""
    decomp = {
        "run_tag": run_tag,
        "problem": problem,
        "composite_metric": {
            "oracle": "python3 oracles/evaluate_composite.py",
            "direction": "lower_is_better",
        },
        "branches": [],
        "composite_weights": composite_weights,
    }
    for spec in specs:
        decomp["branches"].append({
            "id": spec.task_id,
            "owns": [spec.solution_file],
            "metric": {
                "name": spec.metric_name,
                "oracle": spec.oracle_command.replace("{mode}", "full"),
                "direction": spec.metric_direction,
            },
        })

    path = root / "config" / "decomposition.yaml"
    with open(path, "w") as f:
        f.write(f"# Generated by transmuter.py for run_tag: {run_tag}\n")
        yaml.dump(decomp, f, default_flow_style=False, sort_keys=False)
    return path


# ---------------------------------------------------------------------------
# Spec-mode parser (Stage 1 alternative — no LLM)
# ---------------------------------------------------------------------------

def load_spec(spec_path: Path) -> tuple[list[TaskSpec], dict, str]:
    """Load a hand-written spec YAML and convert to TaskSpecs.

    Returns (specs, composite_weights, problem_description).
    """
    with open(spec_path) as f:
        data = yaml.safe_load(f) or {}

    problem = data.get("problem", "(from spec file)")
    composite_weights = data.get("composite_weights", {})
    specs = []

    for branch in data.get("branches", []):
        bid = branch["id"]
        metric = branch.get("metric", {})
        template = branch.get("template", "perf_benchmark")

        spec = TaskSpec(
            task_id=bid,
            template=template,
            solution_file=branch.get("owns", [f"solutions/{bid}.py"])[0],
            metric_name=metric.get("name", f"{bid}_metric"),
            metric_direction=metric.get("direction", "lower_is_better"),
            contract=branch.get("contract", f"def {bid}()"),
            goal_description=branch.get("description", ""),
            oracle_command=metric.get("oracle", ""),
            oracle_metric_pattern=branch.get("oracle_metric_pattern", ""),
            ideas=branch.get("ideas", []),
            stdlib_only=branch.get("stdlib_only", True),
        )
        spec = resolve_oracle_config(spec)
        if bid not in composite_weights:
            composite_weights[bid] = 1.0
        specs.append(spec)

    return specs, composite_weights, problem


# ---------------------------------------------------------------------------
# Human checkpoint (Stage 5)
# ---------------------------------------------------------------------------

def human_checkpoint(specs: list[TaskSpec], run_tag: str, generated_files: list[str]) -> bool:
    """Interactive checkpoint. Returns True to proceed, False to abort."""
    print("\n=== TRANSMUTER PLAN ===")
    print(f"Run tag: {run_tag}")
    print(f"Tasks: {len(specs)}")

    for i, spec in enumerate(specs, 1):
        print(f"\n  [{i}] {spec.task_id} ({spec.template})")
        print(f"      File: {spec.solution_file}")
        print(f"      Metric: {spec.metric_name} ({spec.metric_direction})")
        print(f"      Contract: {spec.contract}")
        oracle_display = spec.oracle_command.replace("{mode}", "<mode>")
        print(f"      Oracle: {oracle_display}")
        if spec.ideas:
            print(f"      Ideas: {', '.join(spec.ideas[:3])}")

    print(f"\nGenerated files:")
    for f in generated_files:
        print(f"  {f}")

    print()
    try:
        answer = input("Proceed? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Transmuter — Problem Decomposition & Task Orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # From a spec file (no LLM):
  python agents/transmuter.py --spec config/decomposition.yaml --run_tag tx_001

  # From natural language (uses LLM for decomposition):
  python agents/transmuter.py --problem "Optimize sorting for integer arrays" --run_tag tx_001

  # Skip human checkpoint:
  python agents/transmuter.py --problem "..." --run_tag tx_001 --auto
""",
    )
    parser.add_argument("--problem", type=str, help="Natural language problem description")
    parser.add_argument("--spec", type=Path, help="Path to spec YAML (bypasses LLM)")
    parser.add_argument("--run_tag", required=True, help="Run tag for this transmutation")
    parser.add_argument("--auto", action="store_true", help="Skip human checkpoint")
    args = parser.parse_args()

    if not args.problem and not args.spec:
        parser.error("Provide either --problem or --spec")

    root = Path(__file__).resolve().parents[1]

    # -----------------------------------------------------------------------
    # Stage 1: Parse input
    # -----------------------------------------------------------------------
    print("[transmuter] Stage 1: Parse input")

    if args.spec:
        # Spec mode — no LLM needed
        print(f"[transmuter] Spec mode: loading {args.spec}")
        specs, composite_weights, problem = load_spec(args.spec)
        print(f"[transmuter] Loaded {len(specs)} task(s) from spec")

    else:
        # NL mode — need LLM for stages 2-3
        problem = args.problem

        # Load model config
        cfg = _load_model_config(root)
        model = cfg.get("transmuter", cfg.get("primary", "stepfun/step-3.5-flash:free"))

        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
            sys.exit(1)

        from openai import OpenAI
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)

        # -------------------------------------------------------------------
        # Stage 2: Classify template
        # -------------------------------------------------------------------
        print("[transmuter] Stage 2: Classify template")
        template, confidence = classify_template(problem)
        print(f"[transmuter] Keyword match: {template} (confidence={confidence:.2f})")

        if confidence < 0.15:
            print("[transmuter] Low confidence — using LLM classifier")
            template = classify_template_llm(problem, model, client)
            print(f"[transmuter] LLM classified: {template}")

        # -------------------------------------------------------------------
        # Stage 3: Decompose into tasks (LLM)
        # -------------------------------------------------------------------
        print("[transmuter] Stage 3: Decompose into tasks")
        decomposition = decompose_with_llm(problem, template, model, client)
        composite_weights = decomposition.get("composite_weights", {})
        specs = build_task_specs(decomposition, template)
        print(f"[transmuter] Decomposed into {len(specs)} task(s)")

    # -----------------------------------------------------------------------
    # Stage 4: Generate artifacts
    # -----------------------------------------------------------------------
    print("[transmuter] Stage 4: Generate artifacts")
    generated_files = []

    for spec in specs:
        # program.md
        program_dir = root / "cogs" / spec.task_id
        program_dir.mkdir(parents=True, exist_ok=True)
        program_path = program_dir / "program.md"
        if not program_path.exists():
            program_content = generate_program_md(spec, root)
            program_path.write_text(program_content)
            generated_files.append(str(program_path.relative_to(root)))
        else:
            generated_files.append(str(program_path.relative_to(root)) + " (exists, kept)")

        # solution scaffold (only if file doesn't exist)
        sol_path = root / spec.solution_file
        if not sol_path.exists():
            sol_path.parent.mkdir(parents=True, exist_ok=True)
            scaffold = generate_scaffold(spec, root)
            sol_path.write_text(scaffold)
            generated_files.append(str(sol_path.relative_to(root)) + " (scaffold)")
        else:
            generated_files.append(str(sol_path.relative_to(root)) + " (exists, kept)")

    # Update task registry
    update_task_registry(specs, root)
    generated_files.append("config/task_registry.yaml (updated)")

    # Write decomposition.yaml
    decomp_path = generate_decomposition_yaml(specs, composite_weights, args.run_tag, problem, root)
    generated_files.append(str(decomp_path.relative_to(root)))

    # -----------------------------------------------------------------------
    # Stage 5: Human checkpoint
    # -----------------------------------------------------------------------
    if not args.auto:
        print("[transmuter] Stage 5: Human checkpoint")
        if not human_checkpoint(specs, args.run_tag, generated_files):
            print("[transmuter] Aborted by user.")
            sys.exit(0)
    else:
        print("[transmuter] Stage 5: Skipped (--auto)")

    # -----------------------------------------------------------------------
    # Stage 6: Output & exit
    # -----------------------------------------------------------------------
    print("[transmuter] Stage 6: Output")

    # Auto-scan for stale artifacts after generation
    try:
        from agents.calcinator import auto_scan
        auto_scan(root)
    except Exception:
        pass

    print("\nGenerated artifacts written. To dispatch:\n")

    cog_ids = ",".join(spec.task_id for spec in specs)
    branch_ids = " ".join(spec.task_id for spec in specs)

    print(f"  python3 agents/cog_manager.py create --run_tag {args.run_tag} --cog_ids {cog_ids} --push")
    for spec in specs:
        print(f"  python3 agents/agent.py --branch_id {spec.task_id} --iterations 4 --run_tag {args.run_tag}")
    print(f"  python3 agents/coordinator_script.py --run_tag {args.run_tag} --branch_ids {branch_ids}")
    print()


def _load_model_config(root: Path) -> dict:
    """Load model_config.yaml."""
    cfg_path = root / "config" / "model_config.yaml"
    if cfg_path.exists():
        with open(cfg_path) as f:
            return yaml.safe_load(f) or {}
    return {}


if __name__ == "__main__":
    main()
