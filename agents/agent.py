"""
Branch agent runner for TRANSMUTE-SWARM. Uses OpenRouter (OpenAI-compatible API).
Reads program_<branch_id>.md and shared_context.md, runs the autoresearch loop via bash tool.
Supports primary + fallback model from model_config.yaml. Loads OPENROUTER_API_KEY from env or keys.env.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Keys live at the TRANSMUTE-SWARM root, one level up from this agents/ module
    load_dotenv(Path(__file__).resolve().parents[1] / "keys.env")
except Exception:
    pass

from openai import OpenAI
import yaml

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Execute a bash command in the repo root. Use this to modify files, run the oracle, git commit/reset, and read results. Always run from the repository root directory.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
}


def get_model_config(root: Path) -> dict:
    """Load primary and fallback from model_config.yaml. Defaults if file missing."""
    cfg_path = root / "model_config.yaml"
    if cfg_path.exists():
        with open(cfg_path) as f:
            return yaml.safe_load(f) or {}
    return {
        "primary": "stepfun/step-3.5-flash:free",
        "fallback": "openrouter/hunter-alpha",
    }


def run_bash(cwd: Path, command: str) -> str:
    """Run command in cwd; return combined stdout and stderr (truncated if huge)."""
    try:
        r = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        combined = f"stdout:\n{out}\n\nstderr:\n{err}\n\nreturncode: {r.returncode}"
        if len(combined) > 8000:
            combined = combined[:8000] + "\n... (truncated)"
        return combined
    except subprocess.TimeoutExpired:
        return "Timeout (300s) — command killed."
    except Exception as e:
        return f"Error: {e}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch_id", required=True, help="e.g. sort or search")
    parser.add_argument("--iterations", type=int, default=4, help="Max experiment iterations")
    parser.add_argument("--run_tag", default="poc_001", help="Run tag for branch naming")
    args = parser.parse_args()

    # Use TRANSMUTE-SWARM root (parent of agents/) as the working root
    root = Path(__file__).resolve().parents[1]
    branch_id = args.branch_id
    program_path = root / f"program_{branch_id}.md"
    shared_path = root / "discoveries" / "shared_context.md"

    if not program_path.exists():
        print(f"ERROR: {program_path} not found", file=sys.stderr)
        sys.exit(1)

    program_text = program_path.read_text()
    shared_text = shared_path.read_text() if shared_path.exists() else "(No shared context yet.)"

    system_content = f"""You are the branch agent for branch '{branch_id}' in TRANSMUTE-SWARM. You must follow the program instructions exactly.

## Program (your instructions)
{program_text}

## Shared context (findings from other branches)
{shared_text}

## Constraints
- You have at most {args.iterations} experiment iterations. Each iteration = one attempt to modify code, run the oracle, and keep or discard.
- Use the bash tool for EVERY action: read files, edit files (e.g. with sed or by writing content), run the oracle, git commit, git reset, grep results, append to results TSV.
- You modify ONLY the file(s) your program says you own. Do not modify evaluate.py, evaluate_composite.py, or the other branch's solution file.
- After each experiment, either keep the commit (if metric improved) or run `git reset --hard HEAD~1` to discard.
- When you have completed the requested number of iterations (or cannot improve further), reply with a single message: DONE. Summarize best metric achieved and key changes.
- Do not ask the user for permission. Act autonomously until DONE or iteration limit."""

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(base_url=OPENROUTER_BASE, api_key=key)
    cfg = get_model_config(root)
    primary = cfg.get("primary", "stepfun/step-3.5-flash:free")
    fallback = cfg.get("fallback", "openrouter/hunter-alpha")
    current_model = primary

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": f"Begin the experiment loop for branch {branch_id}. Run the baseline first (no code change), then iterate up to {args.iterations} times. Use only the bash tool."},
    ]

    max_tool_rounds = args.iterations * 15  # enough runway for baseline + several experiments (e.g. search binary search)
    tool_rounds = 0

    while True:
        try:
            response = client.chat.completions.create(
                model=current_model,
                messages=messages,
                tools=[TOOL_DEF],
                tool_choice="auto",
                max_tokens=4096,
            )
        except Exception:
            if current_model == primary:
                current_model = fallback
                continue
            raise

        choice = response.choices[0]
        msg = choice.message
        # Serialize assistant message for next request (OpenAI format)
        asst = {"role": "assistant", "content": msg.content or ""}
        if getattr(msg, "tool_calls", None):
            asst["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": getattr(tc.function, "name", "bash"), "arguments": getattr(tc.function, "arguments", "{}")}}
                for tc in msg.tool_calls
            ]
        messages.append(asst)

        if choice.finish_reason == "stop":
            if msg.content and "DONE" in (msg.content or "").upper():
                print("Agent signalled DONE.")
                break
            # No tool calls and didn't say DONE — maybe hit token limit; prompt again
            messages.append({"role": "user", "content": "Continue. Use the bash tool to run the next experiment or to report DONE."})
            continue

        if not getattr(msg, "tool_calls", None):
            messages.append({"role": "user", "content": "Continue. Use the bash tool for all actions, then report DONE when finished."})
            continue

        for tc in msg.tool_calls:
            tool_rounds += 1
            if tool_rounds > max_tool_rounds:
                print("Max tool rounds reached; stopping.")
                break
            name = getattr(tc.function, "name", None) if hasattr(tc, "function") else None
            args_str = getattr(tc.function, "arguments", "{}") if hasattr(tc, "function") else "{}"
            if name == "bash":
                try:
                    args = json.loads(args_str)
                    command = args.get("command", "")
                except json.JSONDecodeError:
                    command = args_str.strip().strip('"')
                result = run_bash(root, command)
            else:
                result = f"Unknown tool: {name}"
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

        if tool_rounds > max_tool_rounds:
            break

    print("Agent run complete.")


if __name__ == "__main__":
    main()

