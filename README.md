# TRANSMUTE-SWARM

PoC implementation of the Swarm Research System from `docs/SWARM_DESIGN.md`. Extends the [autoresearch](https://github.com/karpathy/autoresearch) loop to multiple parallel branches with a composite oracle and deterministic coordinator.

## Quick start

1. **Setup**
   ```bash
   cd TRANSMUTE-SWARM
   python -m venv .venv && source .venv/bin/activate  # or: uv venv && source .venv/bin/activate
   pip install -r config/requirements.txt
   ```

2. **API key**  
   Copy `keys.env` from the parent repo or create one with:
   ```bash
   echo 'OPENROUTER_API_KEY="your-key"' > keys.env
   ```
   `keys.env` is gitignored.

3. **Probe models** (run once to pick primary + fallback)
   ```bash
   python scripts/probe_models.py
   ```
   Writes `config/model_config.yaml`.

4. **Run branch agents** (local)
   ```bash
   python agents/agent.py --branch_id sort --iterations 4 --run_tag poc_001
   python agents/agent.py --branch_id search --iterations 4 --run_tag poc_001
   python agents/agent.py --branch_id filter --iterations 4 --run_tag poc_001
   ```

5. **Coordinator** (after branches complete; needs results TSVs)
   ```bash
   python agents/coordinator_script.py --run_tag poc_001 --branch_ids sort search filter
   ```
   For CI: coordinator workflow gets TSVs by downloading artifacts from the swarm run. When triggering coordinator manually, provide **Swarm workflow run ID** so it can download that run's artifacts (TSVs are not committed).

## Structure

- `docs/` — narrative design and timeline (e.g. `docs/SWARM_DESIGN.md`, `docs/TIMELINE.md`)
- `prompts/` — system prompts and instructions (e.g. `prompts/programs/program_sort.md`, `prompts/dharma.md`, `prompts/decomposition.yaml`)
- `reports/` — run and coordinator reports (e.g. `reports/run_analysis_poc5.md`)
- `agents/agent.py` — OpenRouter agentic loop (bash tool, primary + fallback model)
- `agents/coordinator_script.py` — Phase 1 deterministic coordinator
- `oracles/evaluate.py` / `oracles/evaluate_composite.py` — fixed oracles (do not modify)
- `solutions/sort.py`, `solutions/search.py`, `solutions/filter.py` — branch-owned code; agents modify these
- `discoveries/` — shared and per-branch discoveries
- `results/` — branch TSVs and token logs (e.g. `results/sort/results_sort.tsv`, `results/token_usage.tsv`)
- `config/` — environment and model configuration (e.g. `config/requirements.txt`, `config/model_config.yaml`)
- `assets/` — non-code binaries (e.g. `assets/progress.png`)

## GitHub Actions

- **swarm.yml** — `workflow_dispatch` with `run_tag`, `branch_ids` (default: sort,search,filter), `iterations` (default: 4); runs parallel branch agents, uploads `results_*.tsv` as artifacts. Secret: `OPENROUTER_API_KEY`.
- **coordinator.yml** — Triggered by swarm completion (`workflow_run`) or manually with `run_tag`, `branch_ids`, and **swarm_run_id** (to download results TSVs from swarm artifacts). Runs coordinator script, uploads report artifact.

## Design

See `docs/SWARM_DESIGN.md` and the plan in `.cursor/plans/` for full architecture.
