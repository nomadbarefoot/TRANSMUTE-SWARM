#!/usr/bin/env bash
set -euo pipefail

# Run a single branch experiment:
# - Assumes the caller has already edited the owned solution file.
# - Runs the branch oracle, parses the metric, compares to best keep so far,
#   conditionally commits only on improvement, appends a TSV row via append_tsv.py,
#   and prints a short summary to stdout.
#
# Usage:
#   bash run_experiment.sh --branch sort --solution-path solutions/sort.py \
#       --description "Tried built-in sorted()" \
#       --log "Replaced bubble sort with built-in sorted()."
#
# Notes:
# - This script must be run from the TRANSMUTE-SWARM repo root.
# - Currently ignores any \"quick\"/scouting mode; that will be wired once
#   evaluate.py grows a --quick flag.

branch=""
solution_path=""
description=""
log_msg=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)
      branch="$2"
      shift 2
      ;;
    --solution-path)
      solution_path="$2"
      shift 2
      ;;
    --description)
      description="$2"
      shift 2
      ;;
    --log)
      log_msg="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$branch" || -z "$solution_path" || -z "$description" || -z "$log_msg" ]]; then
  echo "Usage: run_experiment.sh --branch <sort|search|filter> --solution-path <path> --description <msg> --log <msg>" >&2
  exit 1
fi

metric_name=""
case "$branch" in
  sort) metric_name="sort_time_ms" ;;
  search) metric_name="search_time_ms" ;;
  filter) metric_name="filter_time_ms" ;;
  *)
    echo "Unknown branch: $branch (expected sort, search, or filter)" >&2
    exit 1
    ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

tsv="results_${branch}.tsv"

# Compute best keep metric so far (lower is better).
best_before=""
if [[ -f "$tsv" ]]; then
  best_before="$(awk -F'\t' 'NR>1 && tolower($4)=="keep" { v=$2+0; if (m=="" || v<m) m=v } END { if (m!="") printf "%.6f", m }' "$tsv" || true)"
fi

# Run oracle and capture output.
status="crash"
metric_value="0.0"

python3 oracles/evaluate.py --branch "$branch" > run.log 2>&1 || true

metric_line="$(grep -E "^${metric_name}:" run.log | head -n 1 || true)"
if [[ -z "$metric_line" ]]; then
  status="crash"
else
  # Expect format: "<metric_name>:  <value>"
  metric_value="$(echo "$metric_line" | awk '{print $2}' )"
  if [[ -z "$metric_value" ]]; then
    status="crash"
  else
    # Compare to best_before (if any).
    if [[ -z "$best_before" ]]; then
      improved="yes"
    else
      awk_prog=$(cat <<'AWK'
      BEGIN {
        best = ARGV[1] + 0.0;
        cur = ARGV[2] + 0.0;
        if (cur < best) { exit 0 } else { exit 1 }
      }
AWK
)
      if echo "" | awk "$awk_prog" "$best_before" "$metric_value"; then
        improved="yes"
      else
        improved="no"
      fi
    fi

    if [[ "${improved:-yes}" == "yes" ]]; then
      status="keep"
    else
      status="discard"
    fi
  fi
fi

commit="none"

if [[ "$status" == "keep" ]]; then
  git add "$solution_path"
  git commit -m "$description" >/dev/null 2>&1 || {
    echo "git commit failed; treating as crash and reverting file." >&2
    git checkout -- "$solution_path" || true
    status="crash"
  }
  if [[ "$status" == "keep" ]]; then
    commit="$(git rev-parse --short HEAD)"
  fi
else
  # Discard or crash: revert solution changes.
  git checkout -- "$solution_path" || true
fi

# Append TSV row (commit may be \"none\" for discard/crash).
python3 append_tsv.py "$branch" "$commit" "$metric_value" "0.0" "$status" "$description" "$log_msg"

best_after="$best_before"
if [[ "$status" == "keep" ]]; then
  best_after="$metric_value"
fi

echo "status=$status"
echo "metric=$metric_value"
echo "best_before=${best_before:-none}"
echo "best_after=${best_after:-none}"
echo "commit=$commit"

