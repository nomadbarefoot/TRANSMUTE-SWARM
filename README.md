# TRANSMUTE-SWARM

PoC implementation of the Swarm Research System from [SWARM_DESIGN_V2.md](../SWARM_DESIGN_V2.md). Extends the [autoresearch](https://github.com/karpathy/autoresearch) loop to multiple parallel branches with a composite oracle and deterministic coordinator.

## Quick start

1. **Setup**
   ```bash
   cd TRANSMUTE-SWARM
   python -m venv .venv && source .venv/bin/activate  # or: uv venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **API key**  
   Copy `keys.env` from the parent repo or create one with:
   ```bash
   echo 'OPENROUTER_API_KEY="your-key"' > keys.env
   ```
   `keys.env` is gitignored.

3. **Probe models** (run once to pick primary + fallback)
   ```bash
   python probe_models.py
   ```
   Writes `model_config.yaml`.

4. **Run branch agents** (local)
   ```bash
   python agent.py --branch_id sort --iterations 4 --run_tag poc_001
   python agent.py --branch_id search --iterations 4 --run_tag poc_001
   python agent.py --branch_id filter --iterations 4 --run_tag poc_001
   ```

5. **Coordinator** (after branches complete; needs results TSVs)
   ```bash
   python coordinator_script.py --run_tag poc_001 --branch_ids sort search filter
   ```
   For CI: coordinator workflow gets TSVs by downloading artifacts from the swarm run. When triggering coordinator manually, provide **Swarm workflow run ID** so it can download that run's artifacts (TSVs are not committed).

## Structure

- `evaluate.py` / `evaluate_composite.py` — fixed oracles (do not modify)
- `solutions/sort.py`, `solutions/search.py`, `solutions/filter.py` — branch-owned code; agents modify these
- `program_sort.md`, `program_search.md`, `program_filter.md` — agent instructions per branch
- `agent.py` — OpenRouter agentic loop (bash tool, primary + fallback model)
- `coordinator_script.py` — Phase 1 deterministic coordinator
- `probe_models.py` — tests OpenRouter free models; writes `model_config.yaml`
- `decomposition.yaml` — hand-written PoC decomposition

## GitHub Actions

- **swarm.yml** — `workflow_dispatch` with `run_tag`, `branch_ids` (default: sort,search,filter), `iterations` (default: 4); runs parallel branch agents, uploads results_*.tsv as artifacts. Secret: `OPENROUTER_API_KEY`.
- **coordinator.yml** — Triggered by swarm completion (`workflow_run`) or manually with `run_tag`, `branch_ids`, and **swarm_run_id** (to download results TSVs from swarm artifacts). Runs coordinator script, uploads report artifact.

## Design

See [SWARM_DESIGN_V2.md](../SWARM_DESIGN_V2.md) and the plan in `.cursor/plans/` for full architecture.
