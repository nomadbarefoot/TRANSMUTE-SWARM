"""
Branch agent runner for TRANSMUTE-SWARM v2. Uses OpenRouter (OpenAI-compatible API).

Structured tool interface — no freeform bash:
  experiment  : submit solution code + run oracle (zero policy surface area)
  read_file   : read any repo file (validated path)
  explore     : read-only shell commands (grep, ls, cat, head, tail, find, wc)

Features:
  - Separate experiment budget (hard) vs. read budget (soft)
  - Sliding window context with state injection
  - Dead-end memory across iterations
  - Reflection checkpoint every N failed experiments
  - Exponential backoff retry before model fallback
  - Token usage tracking (results/token_usage.tsv)
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / "keys.env")
except Exception:
    pass

from openai import OpenAI
import yaml

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# ---------------------------------------------------------------------------
# Task registry (dynamic config from config/task_registry.yaml)
# ---------------------------------------------------------------------------

# Hardcoded fallbacks — used only if task_registry.yaml is missing
_FALLBACK_SOLUTION_FILES = {
    "sort": "solutions/sort.py",
    "search": "solutions/search.py",
    "filter": "solutions/filter.py",
    "finance": "solutions/finance_ma.py",
}

_FALLBACK_METRIC_COLS = {
    "sort": "sort_time_ms",
    "search": "search_time_ms",
    "filter": "filter_time_ms",
    "finance": "finance_sharpe_neg",
}


def load_task_registry(root: Path) -> dict:
    """Load task_registry.yaml, return dict of task_id -> config.
    Falls back to hardcoded mappings if file not found."""
    registry_path = root / "config" / "task_registry.yaml"
    if registry_path.exists():
        try:
            with open(registry_path) as f:
                data = yaml.safe_load(f) or {}
            return data.get("tasks", {})
        except Exception:
            pass
    return {}


def get_solution_file(task_id: str, registry: dict) -> str:
    """Get solution file path for a task from registry, fallback to hardcoded."""
    if task_id in registry:
        return registry[task_id].get("solution_file", _FALLBACK_SOLUTION_FILES.get(task_id, f"solutions/{task_id}.py"))
    return _FALLBACK_SOLUTION_FILES.get(task_id, f"solutions/{task_id}.py")


def get_metric_col(task_id: str, registry: dict) -> str:
    """Get metric column name for a task from registry, fallback to hardcoded."""
    if task_id in registry:
        return registry[task_id].get("metric_name", _FALLBACK_METRIC_COLS.get(task_id, f"{task_id}_metric"))
    return _FALLBACK_METRIC_COLS.get(task_id, f"{task_id}_metric")


def is_known_task(task_id: str, registry: dict) -> bool:
    """Check if a task_id is valid (in registry or fallback)."""
    return task_id in registry or task_id in _FALLBACK_SOLUTION_FILES

# Explore tool: allowed command prefixes (case-insensitive match on stripped command)
EXPLORE_ALLOWED_PREFIXES = (
    "cat ", "cat\t",
    "head ", "tail ",
    "grep ", "rg ",
    "ls ", "ls",
    "find ",
    "wc ",
    "sed -n ",
    "awk ",
    "python3 -c",
    "python -c",
)

# Explore tool: always-blocked tokens
EXPLORE_BLOCKED_TOKENS = (
    "sed -i", "perl -i",
    " > ", ">>", "| tee ",
    "rm ", "mv ", "cp ",
    "chmod ", "chown ",
    "git commit", "git reset", "git checkout --",
    "run_experiment.sh",
    "evaluate.py", "append_tsv.py",
)

# Sliding window: keep this many assistant+tool exchange pairs beyond the header
SLIDING_WINDOW_PAIRS = 6

# Reflection checkpoint: trigger after this many consecutive non-improving experiments
REFLECTION_INTERVAL = 3


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "experiment",
            "description": (
                "Submit your updated solution code and run the oracle evaluation. "
                "The system writes your code to the owned solution file and invokes run_experiment.sh. "
                "Use mode='baseline' for the first run (no change — baseline measurement). "
                "Use mode='quick' for scouting (auto-promotes to full if improved). "
                "Use mode='full' to force a full evaluation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "solution_code": {
                        "type": "string",
                        "description": "Complete content of your solution file.",
                    },
                    "description": {
                        "type": "string",
                        "description": "One-line description of this attempt.",
                    },
                    "log": {
                        "type": "string",
                        "description": "Longer explanation of what you changed and why.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["baseline", "quick", "full"],
                        "description": "Evaluation mode (default: quick).",
                    },
                },
                "required": ["solution_code", "description", "log"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a file from the repository. "
                "Use to inspect your solution, oracle outputs, or context files. "
                "Provide path relative to repo root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from repo root (e.g. 'solutions/sort.py').",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explore",
            "description": (
                "Run a read-only shell command for codebase exploration. "
                "Allowed: grep, rg, ls, cat, head, tail, find, wc, sed -n, awk. "
                "No writes, no git mutations, no experiment scripts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "A read-only shell command.",
                    }
                },
                "required": ["command"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Model config
# ---------------------------------------------------------------------------

def get_model_config(root: Path) -> dict:
    cfg_path = root / "config" / "model_config.yaml"
    if not cfg_path.exists():
        cfg_path = root / "model_config.yaml"
    if cfg_path.exists():
        with open(cfg_path) as f:
            return yaml.safe_load(f) or {}
    return {
        "primary": "stepfun/step-3.5-flash:free",
        "fallback": "openrouter/hunter-alpha",
    }


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def handle_experiment(
    root: Path,
    branch_id: str,
    solution_path: str,
    solution_code: str,
    description: str,
    log: str,
    mode: str,
    experiment_count: int,
    max_experiments: int,
) -> str:
    if experiment_count >= max_experiments:
        return (
            f"EXPERIMENT LIMIT REACHED: You have used all {max_experiments} experiment "
            "iterations. Call DONE now."
        )

    if mode != "baseline":
        try:
            full_path = root / solution_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(solution_code)
        except Exception as e:
            return f"ERROR writing solution file: {e}"

    # Escape description and log for shell
    import shlex
    cmd = (
        f"bash run_experiment.sh"
        f" --branch {shlex.quote(branch_id)}"
        f" --solution-path {shlex.quote(solution_path)}"
        f" --mode {shlex.quote(mode)}"
        f" --description {shlex.quote(description)}"
        f" --log {shlex.quote(log)}"
    )

    try:
        r = subprocess.run(
            cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=300
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        combined = "\n".join(filter(None, [out, err]))
        if len(combined) > 4000:
            combined = combined[:4000] + "\n... (truncated)"
        return combined or f"(no output, returncode={r.returncode})"
    except subprocess.TimeoutExpired:
        return "Timeout (300s) — experiment killed."
    except Exception as e:
        return f"Error running experiment: {e}"


def handle_read_file(root: Path, path: str) -> str:
    # Basic path validation
    if path.startswith("/"):
        return "BLOCKED: absolute paths are not allowed. Use paths relative to repo root."
    if ".." in path.split("/"):
        return "BLOCKED: '..' path traversal is not allowed."
    full_path = root / path
    if not full_path.exists():
        return f"File not found: {path}"
    if not full_path.is_file():
        return f"Not a file: {path}"
    try:
        content = full_path.read_text()
        if len(content) > 6000:
            content = content[:6000] + "\n... (truncated at 6000 chars)"
        return content
    except Exception as e:
        return f"Error reading file: {e}"


def handle_explore(root: Path, command: str) -> str:
    cmd = command.strip()
    lowered = cmd.lower()

    # Block dangerous tokens
    for blocked in EXPLORE_BLOCKED_TOKENS:
        if blocked in lowered:
            return f"BLOCKED: '{blocked}' is not permitted in explore commands."

    # Must start with an allowed prefix
    if not any(lowered.startswith(p.lower()) for p in EXPLORE_ALLOWED_PREFIXES):
        return (
            "BLOCKED: explore only allows read-only commands "
            "(grep, rg, ls, cat, head, tail, find, wc, sed -n, awk)."
        )

    try:
        r = subprocess.run(
            cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=30
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        combined = "\n".join(filter(None, [out, err]))
        if len(combined) > 4000:
            combined = combined[:4000] + "\n... (truncated)"
        return combined or "(no output)"
    except subprocess.TimeoutExpired:
        return "Timeout (30s)"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def load_trajectory(root: Path, branch_id: str) -> list[dict]:
    """Load results TSV rows as list of dicts."""
    tsv = root / "results" / f"results_{branch_id}.tsv"
    if not tsv.exists():
        return []
    try:
        with open(tsv) as f:
            reader = csv.DictReader(f, delimiter="\t")
            return list(reader)
    except Exception:
        return []


def parse_experiment_result(output: str) -> str:
    """Extract status= line from run_experiment.sh output."""
    for line in output.splitlines():
        if line.startswith("status="):
            return line.split("=", 1)[1].strip()
    return "unknown"


def build_state_block(
    branch_id: str,
    experiment_count: int,
    max_experiments: int,
    dead_ends: list[str],
    trajectory: list[dict],
    metric_col: str | None = None,
) -> str:
    lines = [f"## Agent State (experiment {experiment_count}/{max_experiments})"]

    keep_rows = [r for r in trajectory if r.get("status", "").lower() == "keep"]
    if keep_rows and metric_col:
        try:
            best = min(keep_rows, key=lambda r: float(r.get(metric_col, "inf")))
            lines.append(
                f"best_metric: {best[metric_col]} "
                f"(commit {best.get('commit', '?')}, \"{best.get('description', '?')}\")"
            )
        except (ValueError, TypeError):
            lines.append("best_metric: (parse error)")
    else:
        lines.append("best_metric: none yet")

    if trajectory:
        lines.append("\nrecent_attempts (last 5):")
        for row in trajectory[-5:]:
            metric_val = row.get(metric_col, "?") if metric_col else "?"
            lines.append(
                f"  {row.get('status','?'):8s}  {metric_val:>10}  \"{row.get('description','?')}\""
            )

    if dead_ends:
        lines.append(f"\ndead_ends: {dead_ends}")

    return "\n".join(lines)


def build_trajectory_table(trajectory: list[dict], branch_id: str, metric_col: str | None = None) -> str:
    """Build a markdown table of all results so far."""
    if not trajectory:
        return "(no results yet)"
    metric_col = metric_col or "metric"
    header = f"| # | {metric_col} | status | description |"
    sep = "|---|---|---|---|"
    rows = [header, sep]
    for i, row in enumerate(trajectory, 1):
        rows.append(
            f"| {i} | {row.get(metric_col, '?')} "
            f"| {row.get('status', '?')} "
            f"| {row.get('description', '?')} |"
        )
    return "\n".join(rows)


def apply_sliding_window(messages: list[dict], keep_pairs: int = SLIDING_WINDOW_PAIRS) -> list[dict]:
    """
    Keep system message + initial user message + last `keep_pairs` exchange pairs.
    An exchange pair = one assistant message (with tool calls) + its tool result messages.
    """
    if len(messages) <= 2:
        return messages

    header = messages[:2]
    tail = messages[2:]

    # Group tail into exchange pairs: each pair starts with an assistant message
    pairs: list[list[dict]] = []
    current: list[dict] = []
    for msg in tail:
        if msg["role"] == "assistant" and current:
            pairs.append(current)
            current = [msg]
        else:
            current.append(msg)
    if current:
        pairs.append(current)

    # Keep only the last `keep_pairs`
    kept = pairs[-keep_pairs:] if len(pairs) > keep_pairs else pairs
    result = header[:]
    for pair in kept:
        result.extend(pair)
    return result


def write_token_usage(
    root: Path,
    branch_id: str,
    run_tag: str,
    model_used: str,
    prompt_tokens: int,
    completion_tokens: int,
    iterations_completed: int,
) -> None:
    tsv = root / "results" / "token_usage.tsv"
    HEADER = "branch_id\trun_tag\tmodel\tprompt_tokens\tcompletion_tokens\texperiments_completed\ttimestamp\n"
    # Enforce correct header — overwrite if missing or schema has changed (old agent used different columns)
    if not tsv.exists() or tsv.stat().st_size == 0:
        tsv.write_text(HEADER)
    else:
        first_line = tsv.open().readline()
        if first_line.strip() != HEADER.strip():
            # Back up old file, start fresh with correct schema
            tsv.rename(tsv.with_suffix(".tsv.bak"))
            tsv.write_text(HEADER)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with tsv.open("a") as f:
        f.write(
            f"{branch_id}\t{run_tag}\t{model_used}\t"
            f"{prompt_tokens}\t{completion_tokens}\t{iterations_completed}\t{ts}\n"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch_id", required=True, help="e.g. sort or finance")
    parser.add_argument("--iterations", type=int, default=4, help="Max experiment iterations")
    parser.add_argument("--run_tag", default="poc_001", help="Run tag")
    cli = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    branch_id = cli.branch_id
    max_experiments = cli.iterations

    # Load task registry (dynamic config)
    registry = load_task_registry(root)

    if not is_known_task(branch_id, registry):
        known = list(registry.keys()) if registry else list(_FALLBACK_SOLUTION_FILES.keys())
        print(f"ERROR: unknown branch_id '{branch_id}'. Known: {known}", file=sys.stderr)
        sys.exit(1)

    solution_path = get_solution_file(branch_id, registry)
    metric_col = get_metric_col(branch_id, registry)
    program_path = root / "cogs" / branch_id / "program.md"
    shared_path = root / "discoveries" / "shared_context.md"

    if not program_path.exists():
        print(f"ERROR: {program_path} not found", file=sys.stderr)
        sys.exit(1)

    program_text = program_path.read_text()
    shared_text = shared_path.read_text() if shared_path.exists() else "(No shared context yet.)"

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(base_url=OPENROUTER_BASE, api_key=key)
    cfg = get_model_config(root)
    primary = cfg.get("primary", "stepfun/step-3.5-flash:free")
    fallback = cfg.get("fallback", "openrouter/hunter-alpha")
    current_model = primary
    model_used_for_report = primary

    system_content = f"""You are the branch agent for branch '{branch_id}' in TRANSMUTE-SWARM.

## Program (your instructions)
{program_text}

## Shared context
{shared_text}

## Tools
- `experiment`: Write solution code and run the oracle. This counts against your experiment budget.
- `read_file`: Read any repo file. Does NOT count against experiment budget.
- `explore`: Read-only shell commands (grep, ls, cat, etc.). Does NOT count against experiment budget.

## Rules
- You own exactly one file: `{solution_path}`. Do not reference other solution files.
- Your experiment budget is {max_experiments} calls to `experiment`. Use them wisely.
- Use `read_file` and `explore` freely for reconnaissance before committing to an experiment.
- The oracle is the only arbiter. Lower metric = better.
- When done (budget exhausted or no further improvement possible), reply with a message containing "DONE" and summarize your best result.
- Do not ask for permission. Act autonomously."""

    messages = [
        {"role": "system", "content": system_content},
        {
            "role": "user",
            "content": (
                f"Begin the experiment loop for branch '{branch_id}'. "
                f"First, read your solution file to understand the baseline, then call experiment with mode='baseline'. "
                f"Then iterate up to {max_experiments} times to improve the metric. "
                f"You have {max_experiments} experiment calls total."
            ),
        },
    ]

    experiment_count = 0
    read_count = 0
    read_limit = max_experiments * 4
    dead_ends: list[str] = []
    experiments_since_improvement = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    print(f"[agent] branch={branch_id} max_experiments={max_experiments} run_tag={cli.run_tag}")
    print(f"[agent] model={primary} fallback={fallback}")
    print(f"[agent] solution={solution_path}")

    while True:
        # --- Build state injection ---
        trajectory = load_trajectory(root, branch_id)
        state_block = build_state_block(
            branch_id, experiment_count, max_experiments, dead_ends, trajectory,
            metric_col=metric_col,
        )

        # Inject state as a user message (replace any prior state injection)
        state_msg = {
            "role": "user",
            "content": (
                f"{state_block}\n\n"
                f"## Your Results So Far\n{build_trajectory_table(trajectory, branch_id, metric_col=metric_col)}"
            ),
        }
        # Apply sliding window, then append fresh state
        windowed = apply_sliding_window(messages)
        api_messages = windowed + [state_msg]

        # --- API call with fallback ---
        try:
            response = client.chat.completions.create(
                model=current_model,
                messages=api_messages,
                tools=TOOL_DEFS,
                tool_choice="auto",
                max_tokens=4096,
            )
        except Exception as exc:
            if current_model == primary:
                print(f"[agent] Primary model failed ({exc}); switching to fallback: {fallback}")
                current_model = fallback
                model_used_for_report = fallback
                continue
            print(f"[agent] Fatal: fallback also failed: {exc}", file=sys.stderr)
            raise

        # Track token usage
        if hasattr(response, "usage") and response.usage:
            total_prompt_tokens += getattr(response.usage, "prompt_tokens", 0) or 0
            total_completion_tokens += getattr(response.usage, "completion_tokens", 0) or 0

        choice = response.choices[0]
        msg = choice.message

        # Serialize assistant message
        asst: dict = {"role": "assistant", "content": msg.content or ""}
        if getattr(msg, "tool_calls", None):
            asst["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": getattr(tc.function, "name", ""),
                        "arguments": getattr(tc.function, "arguments", "{}"),
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(asst)

        # --- Handle finish_reason=stop ---
        if choice.finish_reason == "stop":
            content = msg.content or ""
            if "DONE" in content.upper():
                print("[agent] Agent signalled DONE.")
                break
            # No tool call and no DONE — nudge
            messages.append({
                "role": "user",
                "content": "Continue. Use the experiment tool to run the next iteration, or report DONE if finished.",
            })
            continue

        # --- Handle tool calls ---
        if not getattr(msg, "tool_calls", None):
            messages.append({
                "role": "user",
                "content": "Use one of the available tools (experiment, read_file, explore), then report DONE when finished.",
            })
            continue

        for tc in msg.tool_calls:
            name = getattr(tc.function, "name", "") if hasattr(tc, "function") else ""
            args_str = getattr(tc.function, "arguments", "{}") if hasattr(tc, "function") else "{}"
            try:
                tool_args = json.loads(args_str)
            except json.JSONDecodeError:
                tool_args = {}

            if name == "experiment":
                experiment_count += 1
                sol_code = tool_args.get("solution_code", "")
                desc = tool_args.get("description", "(no description)")
                log = tool_args.get("log", "(no log)")
                mode = tool_args.get("mode", "quick")

                print(f"[agent] experiment {experiment_count}/{max_experiments}: {desc!r} mode={mode}")
                result = handle_experiment(
                    root, branch_id, solution_path,
                    sol_code, desc, log, mode,
                    experiment_count - 1,  # pass pre-increment count for limit check
                    max_experiments,
                )
                print(f"[agent] result: {result[:200]}")

                # Update dead-end memory and improvement tracking
                status = parse_experiment_result(result)
                if status in ("discard", "crash"):
                    experiments_since_improvement += 1
                    dead_ends.append(f"{desc} (→ {status})")
                elif status == "keep":
                    experiments_since_improvement = 0

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

                # Reflection checkpoint
                if (
                    experiments_since_improvement > 0
                    and experiments_since_improvement % REFLECTION_INTERVAL == 0
                    and experiment_count < max_experiments
                ):
                    remaining = max_experiments - experiment_count
                    reflection = (
                        f"REFLECTION CHECKPOINT (experiment {experiment_count}/{max_experiments}, "
                        f"{experiments_since_improvement} consecutive non-improvements, "
                        f"{remaining} experiments remaining)\n"
                        "You've made several attempts without improvement. Before continuing:\n"
                        "1. What fundamentally different approach have you NOT tried?\n"
                        "2. Would a completely different algorithm or data structure beat incremental tuning?\n"
                        "Consider a bold change for the next iteration rather than another small tweak."
                    )
                    messages.append({"role": "user", "content": reflection})

                # Hard stop if budget exhausted
                if experiment_count >= max_experiments:
                    messages.append({
                        "role": "user",
                        "content": (
                            f"You have used all {max_experiments} experiment iterations. "
                            "Reply with DONE and summarize your best result."
                        ),
                    })

            elif name == "read_file":
                read_count += 1
                path = tool_args.get("path", "")
                result = handle_read_file(root, path)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            elif name == "explore":
                read_count += 1
                command = tool_args.get("command", "")
                result = handle_explore(root, command)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            else:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Unknown tool: {name}. Available: experiment, read_file, explore.",
                })

        # Soft read limit warning
        if read_count >= read_limit:
            messages.append({
                "role": "user",
                "content": (
                    f"You have made {read_count} read operations. "
                    "Please proceed to experiments rather than more exploration."
                ),
            })

    # --- Write token usage ---
    write_token_usage(
        root, branch_id, cli.run_tag, model_used_for_report,
        total_prompt_tokens, total_completion_tokens, experiment_count
    )

    print(
        f"[agent] Run complete. "
        f"experiments={experiment_count} reads={read_count} "
        f"prompt_tokens={total_prompt_tokens} completion_tokens={total_completion_tokens}"
    )


if __name__ == "__main__":
    main()
