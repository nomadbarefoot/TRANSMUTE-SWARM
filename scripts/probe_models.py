"""
Model availability and quality tester for TRANSMUTE-SWARM.
Tests OpenRouter free models for availability, tool-use support, and instruction following.
Writes config/model_config.yaml with primary and fallback recommendation.
Run once before the first swarm run. Loads OPENROUTER_API_KEY from env or keys.env.
"""
import os
import re
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / "keys.env")
except Exception:
    pass

from openai import OpenAI

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
CANDIDATES = [
    "stepfun/step-3.5-flash:free",
    "openrouter/hunter-alpha",
    "arcee-ai/trinity-large-preview:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
]
AVAILABILITY_TIMEOUT = 30
TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Execute a bash command. Returns stdout and stderr.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
}
INSTRUCTION_PROMPT = """You have a Python file with a bubble sort implementation. Your task:
1. Propose ONE concrete code change to improve performance (e.g. use a different algorithm).
2. State the exact command you would run to test it (e.g. python3 evaluate.py --branch sort).
3. State the expected metric value or direction (e.g. "sort_time_ms should decrease by at least 10%").

Reply in a short, structured way with: CHANGE:, COMMAND:, EXPECTED:."""


def get_client():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("ERROR: OPENROUTER_API_KEY not set. Set it in env or keys.env.", file=sys.stderr)
        sys.exit(1)
    return OpenAI(base_url=OPENROUTER_BASE, api_key=key)


def test_availability(client: OpenAI, model: str) -> tuple[bool, float]:
    """Basic ping. Returns (success, latency_sec)."""
    start = time.time()
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say exactly: hello"}],
            max_tokens=20,
            timeout=AVAILABILITY_TIMEOUT,
        )
        latency = time.time() - start
        if r.choices and r.choices[0].message.content:
            return True, latency
        return False, latency
    except Exception:
        latency = time.time() - start
        return False, latency


def test_tool_use(client: OpenAI, model: str) -> tuple[bool, float]:
    """Check if model returns a valid tool call. Returns (success, latency_sec)."""
    start = time.time()
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "Run the command: echo 42"},
            ],
            tools=[TOOL_DEF],
            tool_choice="auto",
            max_tokens=200,
            timeout=AVAILABILITY_TIMEOUT,
        )
        latency = time.time() - start
        choice = r.choices[0] if r.choices else None
        if not choice:
            return False, latency
        msg = choice.message
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tc = msg.tool_calls[0]
            if getattr(tc, "function", None):
                args = getattr(tc.function, "arguments", None) or ""
                if "command" in args or "echo" in args:
                    return True, latency
        return False, latency
    except Exception:
        latency = time.time() - start
        return False, latency


def score_instruction_following(text: str) -> int:
    """Score 0-6: (a) code change 2pt, (b) command 2pt, (c) expected metric 2pt."""
    text = (text or "").lower()
    score = 0
    if re.search(r"change:|quicksort|mergesort|algorithm|def sort|\.sort|in place", text):
        score += 2
    elif re.search(r"change|replace|improve|different", text):
        score += 1
    if re.search(r"command:|evaluate\.py|python3?\\s+.*evaluate|run\\s+.*evaluate", text):
        score += 2
    elif re.search(r"python|run|command", text):
        score += 1
    if re.search(r"expected:|decrease|lower|sort_time_ms|time_ms|metric|improve", text):
        score += 2
    elif re.search(r"expect|result|should", text):
        score += 1
    return min(6, score)


def test_instruction_quality(client: OpenAI, model: str) -> tuple[int, float]:
    """Returns (score 0-6, latency_sec)."""
    start = time.time()
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": INSTRUCTION_PROMPT}],
            max_tokens=400,
            timeout=AVAILABILITY_TIMEOUT,
        )
        latency = time.time() - start
        content = (r.choices[0].message.content or "").strip()
        score = score_instruction_following(content)
        return score, latency
    except Exception:
        return -1, time.time() - start


def main():
    client = get_client()
    root = Path(__file__).resolve().parents[1]
    results = []

    print("Model Probe Report — TRANSMUTE-SWARM")
    print("=" * 60)

    for model in CANDIDATES:
        avail, lat_avail = test_availability(client, model)
        if not avail:
            results.append((model, "TIMEOUT/FAIL", "-", "-", lat_avail))
            continue
        tool_ok, lat_tool = test_tool_use(client, model)
        if not tool_ok:
            results.append((model, "YES", "NO", "-", lat_avail))
            continue
        qual, lat_qual = test_instruction_quality(client, model)
        results.append((model, "YES", "YES", f"{qual}/6" if qual >= 0 else "-", lat_avail + lat_tool + lat_qual))

    # Print table
    print(f"{'Model':<45} {'Available':<10} {'Tool Use':<10} {'Quality':<8} {'Latency':<8}")
    for model, a, t, q, lat in results:
        lat_s = f"{lat:.1f}s" if isinstance(lat, (int, float)) else "-"
        print(f"{model:<45} {a:<10} {t:<10} {q:<8} {lat_s:<8}")

    # Recommendation: best two that have tool use and availability
    eligible = [(m, r) for m, r in zip(CANDIDATES, results) if r[1] == "YES" and r[2] == "YES"]
    if len(eligible) >= 2:
        # Sort by quality (parse "5/6") then by latency
        def key(elem):
            _, (_, _, q, lat) = elem
            qn = int(q.split("/")[0]) if q and q != "-" and "/" in q else 0
            return (-qn, lat if isinstance(lat, (int, float)) else 999)
        eligible.sort(key=key)
        primary = eligible[0][0]
        fallback = eligible[1][0]
    elif len(eligible) == 1:
        primary = fallback = eligible[0][0]
    else:
        print("\nRECOMMENDATION: No model with tool use available. Run again or check API key.")
        sys.exit(1)

    print("\nRECOMMENDATION:")
    print(f"  PRIMARY:  {primary}")
    print(f"  FALLBACK: {fallback}")

    # Write config/model_config.yaml
    import yaml
    from datetime import datetime, timezone
    config = {
        "primary": primary,
        "fallback": fallback,
        "tested_on": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    config_path = root / "config" / "model_config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False)
    print(f"\nWrote {config_path}")
