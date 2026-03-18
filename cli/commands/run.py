"""
swarm run — wraps the Transmuter pipeline with Rich progress output.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cli.console import ACCENT, DIM, SECONDARY, console, error, success, warn

_ROOT = Path(__file__).resolve().parents[2]


def _load_model_config() -> dict:
    try:
        import yaml
        cfg_path = _ROOT / "config" / "model_config.yaml"
        if cfg_path.exists():
            with open(cfg_path) as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    return {}


def _stage(n: int, total: int, label: str, done: bool = False) -> None:
    status = "[bold green]✓[/]" if done else "  "
    console.print(f"  {status} [dim]Stage {n}/{total}[/]  [{SECONDARY}]{label}[/]")


def _dispatch_cogs(specs: list, run_tag: str, iterations: int, root: Path) -> None:
    """Run cog_manager create then spawn agent.py per Cog sequentially."""
    cog_ids = ",".join(s.task_id for s in specs)
    python = sys.executable

    # Step 1: create branches
    create_cmd = [
        python, str(root / "agents" / "cog_manager.py"),
        "create", "--run_tag", run_tag, "--cog_ids", cog_ids, "--push",
    ]
    console.print(f"\n  [dim]$ {' '.join(create_cmd)}[/]")
    subprocess.run(create_cmd, cwd=str(root))

    # Step 2: spawn agent per Cog
    for s in specs:
        agent_cmd = [
            python, str(root / "agents" / "agent.py"),
            "--branch_id", s.task_id,
            "--iterations", str(iterations),
            "--run_tag", run_tag,
        ]
        console.print(f"\n  [dim]$ {' '.join(agent_cmd)}[/]")
        subprocess.run(agent_cmd, cwd=str(root))


def run(
    problem: str = typer.Option(None, "--problem", help="Natural language problem description"),
    spec: Path = typer.Option(None, "--spec", help="Path to spec YAML (bypasses LLM)"),
    run_tag: str = typer.Option(None, "--run_tag", help="Run tag for this transmutation"),
    auto: bool = typer.Option(False, "--auto", help="Skip human checkpoint"),
    iterations: int = typer.Option(4, "--iterations", help="Iterations per Cog when dispatching"),
) -> None:
    """Decompose a problem into Cog tasks and generate artifacts."""
    # Interactive prompts for missing required inputs
    if not problem and not spec:
        problem = typer.prompt("  Problem description")
    if not run_tag:
        default_tag = "tx_" + datetime.now().strftime("%Y%m%d_%H%M")
        run_tag = typer.prompt("  Run tag", default=default_tag)

    # Import transmuter functions (not the CLI main)
    sys.path.insert(0, str(_ROOT))
    try:
        from agents.transmuter import (
            build_task_specs,
            classify_template,
            classify_template_llm,
            decompose_with_llm,
            generate_decomposition_yaml,
            generate_program_md,
            generate_scaffold,
            load_spec,
            update_task_registry,
        )
    except ImportError as e:
        error(f"Cannot import transmuter: {e}")
        raise typer.Exit(1)

    TOTAL = 6

    # -----------------------------------------------------------------------
    # Stage 1: Parse input
    # -----------------------------------------------------------------------
    _stage(1, TOTAL, "parse input")

    if spec:
        with console.status(f"[{DIM}]loading spec {spec}...[/]"):
            specs, composite_weights, problem_text = load_spec(spec)
        _stage(1, TOTAL, f"spec mode — loaded {len(specs)} task(s) from {spec}", done=True)
        need_llm = False
    else:
        problem_text = problem
        need_llm = True
        _stage(1, TOTAL, "NL mode — will use LLM for classification + decomposition", done=True)

    client = None
    model = None
    if need_llm:
        cfg = _load_model_config()
        model = cfg.get("transmuter", cfg.get("primary", "stepfun/step-3.5-flash:free"))
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            # Try loading from keys.env
            try:
                from dotenv import load_dotenv
                load_dotenv(_ROOT / "keys.env")
                key = os.environ.get("OPENROUTER_API_KEY")
            except Exception:
                pass
        if not key:
            error("OPENROUTER_API_KEY not set — set it in keys.env or the environment")
            raise typer.Exit(1)
        from openai import OpenAI
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)

    # -----------------------------------------------------------------------
    # Stage 2: Classify template
    # -----------------------------------------------------------------------
    if need_llm:
        _stage(2, TOTAL, "classify template")
        template, confidence = classify_template(problem_text)
        if confidence < 0.15:
            with console.status(f"[{DIM}]LLM classification...[/]"):
                template = classify_template_llm(problem_text, model, client)
            _stage(2, TOTAL, f"LLM classified → [bold]{template}[/]", done=True)
        else:
            _stage(2, TOTAL, f"keyword match → [bold]{template}[/] [dim](confidence={confidence:.2f})[/]", done=True)
    else:
        _stage(2, TOTAL, "skipped (spec mode)", done=True)

    # -----------------------------------------------------------------------
    # Stage 3: Decompose into tasks (LLM)
    # -----------------------------------------------------------------------
    if need_llm:
        _stage(3, TOTAL, "decompose (LLM)...")
        with console.status(f"[{DIM}]decomposing with LLM ({model})...[/]"):
            decomposition = decompose_with_llm(problem_text, template, model, client)
        composite_weights = decomposition.get("composite_weights", {})
        specs = build_task_specs(decomposition, template)
        _stage(3, TOTAL, f"decomposed → [bold yellow]{len(specs)}[/] task(s)", done=True)
    else:
        _stage(3, TOTAL, "skipped (spec mode)", done=True)

    # -----------------------------------------------------------------------
    # Stage 4: Generate artifacts
    # -----------------------------------------------------------------------
    _stage(4, TOTAL, "generate artifacts")
    generated_files: list[str] = []

    for spec_item in specs:
        program_dir = _ROOT / "cogs" / spec_item.task_id
        program_dir.mkdir(parents=True, exist_ok=True)
        program_path = program_dir / "program.md"
        if not program_path.exists():
            content = generate_program_md(spec_item, _ROOT)
            program_path.write_text(content)
            generated_files.append(str(program_path.relative_to(_ROOT)))
        else:
            generated_files.append(str(program_path.relative_to(_ROOT)) + " (exists, kept)")

        sol_path = _ROOT / spec_item.solution_file
        if not sol_path.exists():
            sol_path.parent.mkdir(parents=True, exist_ok=True)
            scaffold = generate_scaffold(spec_item, _ROOT)
            sol_path.write_text(scaffold)
            generated_files.append(str(sol_path.relative_to(_ROOT)) + " (scaffold)")
        else:
            generated_files.append(str(sol_path.relative_to(_ROOT)) + " (exists, kept)")

    update_task_registry(specs, _ROOT)
    generated_files.append("config/task_registry.yaml (updated)")

    decomp_path = generate_decomposition_yaml(specs, composite_weights, run_tag, problem_text, _ROOT)
    generated_files.append(str(decomp_path.relative_to(_ROOT)))

    _stage(4, TOTAL, f"artifacts written — {len(generated_files)} file(s)", done=True)

    # Show tasks table
    console.print()
    tasks_table = Table(border_style=DIM, show_header=True, header_style=SECONDARY, expand=False)
    tasks_table.add_column("Task ID", style=ACCENT)
    tasks_table.add_column("Template")
    tasks_table.add_column("Metric", style=SECONDARY)
    tasks_table.add_column("Direction", style=DIM)
    tasks_table.add_column("Contract", style=DIM)
    for s in specs:
        tasks_table.add_row(s.task_id, s.template, s.metric_name, s.metric_direction, s.contract)
    console.print(Panel(tasks_table, title=f"[{SECONDARY}]Transmuter Plan — {run_tag}[/]", border_style=DIM))

    # -----------------------------------------------------------------------
    # Stage 5: Human checkpoint
    # -----------------------------------------------------------------------
    _stage(5, TOTAL, "human checkpoint")
    if auto:
        _stage(5, TOTAL, "skipped (--auto)", done=True)
    else:
        files_text = "\n".join(f"  [dim]{f}[/]" for f in generated_files)
        console.print(f"\n[dim]Generated files:[/]\n{files_text}\n")
        proceed = typer.confirm("  Proceed?", default=True)
        if not proceed:
            warn("Aborted by user.")
            raise typer.Exit(0)
        _stage(5, TOTAL, "confirmed", done=True)

    # -----------------------------------------------------------------------
    # Stage 6: Dispatch
    # -----------------------------------------------------------------------
    _stage(6, TOTAL, "dispatch")

    # Auto-scan for stale artifacts
    try:
        from agents.calcinator import auto_scan
        auto_scan(_ROOT)
    except Exception:
        pass

    cog_ids = ",".join(s.task_id for s in specs)
    branch_ids = " ".join(s.task_id for s in specs)

    if auto:
        # Print commands only — no interactive prompt in auto mode
        dispatch_lines = [
            f"  [dim]python3 agents/cog_manager.py create --run_tag {run_tag} --cog_ids {cog_ids} --push[/]",
        ]
        for s in specs:
            dispatch_lines.append(
                f"  [dim]python3 agents/agent.py --branch_id {s.task_id} --iterations {iterations} --run_tag {run_tag}[/]"
            )
        dispatch_lines.append(
            f"  [dim]python3 agents/coordinator_script.py --run_tag {run_tag} --branch_ids {branch_ids}[/]"
        )
        console.print()
        console.print(Panel("\n".join(dispatch_lines), title=f"[{SECONDARY}]Dispatch Commands[/]", border_style=DIM))
        _stage(6, TOTAL, "done (--auto: commands printed, not executed)", done=True)
        success(f"Run [bold yellow]{run_tag}[/] ready to dispatch.")
        return

    # Interactive dispatch
    console.print()
    iterations = typer.prompt("  Iterations per Cog", default=iterations, type=int)
    dispatch = typer.confirm("  Dispatch Cogs now?", default=True)

    if dispatch:
        _stage(6, TOTAL, f"dispatching {len(specs)} Cog(s)...")
        _dispatch_cogs(specs, run_tag, iterations, _ROOT)
        _stage(6, TOTAL, "done", done=True)
        success(f"Run [bold yellow]{run_tag}[/] dispatched.")
    else:
        dispatch_lines = [
            f"  [dim]python3 agents/cog_manager.py create --run_tag {run_tag} --cog_ids {cog_ids} --push[/]",
        ]
        for s in specs:
            dispatch_lines.append(
                f"  [dim]python3 agents/agent.py --branch_id {s.task_id} --iterations {iterations} --run_tag {run_tag}[/]"
            )
        dispatch_lines.append(
            f"  [dim]python3 agents/coordinator_script.py --run_tag {run_tag} --branch_ids {branch_ids}[/]"
        )
        console.print()
        console.print(Panel("\n".join(dispatch_lines), title=f"[{SECONDARY}]Dispatch Commands[/]", border_style=DIM))
        _stage(6, TOTAL, "done", done=True)
        success(f"Run [bold yellow]{run_tag}[/] ready to dispatch.")
