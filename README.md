# TRANSMUTE-SWARM

Tiered autonomous research system: parallel **Cogs** (cheap LLM agents) optimize isolated solution files against fixed **oracles**, then a deterministic **coordinator** synthesizes the best commits.

The current implementation is driven by:

- `agents/agent.py` (Cog loop; OpenRouter tool calling)
- `run_experiment.sh` (the only supported path for oracle runs + commit/revert + TSV append)
- `agents/coordinator_script.py` (deterministic synthesis; no LLM)

Architecture details (derived from code) live in `DOCS/architecture.md`.

## Quick start (local)

### Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r config/requirements.txt
```

### API key

Create `keys.env` (gitignored):

```bash
echo 'OPENROUTER_API_KEY="your-key"' > keys.env
```

### Probe models (optional, recommended)

```bash
python3 scripts/probe_models.py
```

This writes `config/model_config.yaml` with a primary + fallback OpenRouter model.

### Run Cogs (local)

```bash
python3 agents/agent.py --branch_id sort   --iterations 4 --run_tag poc_001
python3 agents/agent.py --branch_id search --iterations 4 --run_tag poc_001
python3 agents/agent.py --branch_id filter --iterations 4 --run_tag poc_001
```

Outputs:

- `results/results_<cog_id>.tsv`
- `results/logs/<cog_id>.log`

### Run coordinator (local)

```bash
python3 agents/coordinator_script.py --run_tag poc_001 --branch_ids sort search filter
```

This writes `coordinator_report_<cycle>.md` at repo root and creates `integration/<run_tag>` locally.

### CLI usage

The project ships a Typer-based CLI (`swarm`) defined in `pyproject.toml`:

- `swarm scan` / `swarm clean` — rich UI wrapper around the Calcinator artifact manager
- additional subcommands live under `cli/commands/`

You can either:

- install the package (editable) and call `swarm`:

```bash
pip install -e .
swarm --help
```

- or use the repo-local launcher script:

```bash
./swarm scan
./swarm clean --dry-run
```

## Repository layout (runtime-relevant)

- **`agents/`**
  - `agent.py`: Cog runner (tools: `experiment`, `read_file`, `explore`)
  - `cog_manager.py`: creates/lists/cleans branches `cogs/<run_tag>/<cog_id>`
  - `coordinator_script.py`: deterministic synthesis (best-per-cog + composite + ablation)
  - `calcinator.py`: artifact lifecycle manager (scan/archive/purge results, logs, discoveries)
- **`cogs/<cog_id>/program.md`**: per-Cog instructions injected into the agent prompt
- **`solutions/`**: Cog-owned solution modules (one file per Cog)
- **`oracles/`**: immutable evaluation harnesses (branch + composite)
- **`results/`**: TSV trajectories + logs
- **`scripts/`**: supporting utilities (`append_tsv.py`, `probe_models.py`, data fetchers)
- **`config/`**: dependency + model config + decomposition scratchpad
- **`DOCS/`**: documentation (see `DOCS/architecture.md`)
 - **`cli/`**: Typer-based CLI and Rich console helpers (`swarm scan`, `swarm clean`, etc.)

## GitHub Actions

- **`Swarm Research`** (`.github/workflows/swarm.yml`)
  - creates/pushes `cogs/<run_tag>/<cog_id>` branches
  - runs one Cog per matrix entry
  - uploads `results/results_<cog_id>.tsv` artifacts
- **`Coordinator`** (`.github/workflows/coordinator.yml`)
  - triggered by swarm completion or manual dispatch
  - downloads the TSV artifacts into `results/` (preferred), with a fallback to reading TSVs from `origin/cogs/<run_tag>/<cog_id>`
  - runs `agents/coordinator_script.py` and uploads `coordinator_report_*.md`

## Known mismatches (currently in codebase)

- **Finance Cog path**: `oracles/evaluate_finance.py` loads `solutions/finance_ma.py`, but `agents/agent.py` maps `finance` to `solutions/finance.py` (missing). If you intend to run the finance Cog, this should be reconciled.
- **Legacy wording in `cogs/*/program.md`**: programs mention running `bash run_experiment.sh ...`, but the Cog runner uses a structured `experiment` tool; `explore` blocks direct `run_experiment.sh` invocation.

