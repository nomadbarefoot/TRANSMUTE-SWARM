#!/usr/bin/env bash
set -euo pipefail

# Run a single branch experiment:
# - Assumes the caller has already edited the owned solution file (except for baseline).
# - Runs the branch oracle, parses the metric, compares to best keep so far,
#   conditionally commits only on improvement, appends a TSV row via append_tsv.py,
#   and prints a short summary to stdout.
#
# Usage:
#   bash run_experiment.sh --branch sort --solution-path solutions/sort.py \
#       --mode quick --description "Tried built-in sorted()" \
#       --log "Replaced bubble sort with built-in sorted()."
#
# Notes:
# - This script must be run from the TRANSMUTE-SWARM repo root.
# - --mode baseline records a keep row with current HEAD and does not commit.

branch=""
solution_path=""
description=""
log_msg=""
mode="full"
log_dir=""

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
    --mode)
      mode="$2"
      shift 2
      ;;
    --log-dir)
      log_dir="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$branch" || -z "$solution_path" || -z "$description" || -z "$log_msg" ]]; then
  echo "Usage: run_experiment.sh --branch <sort|search|filter> --solution-path <path> --mode <baseline|quick|full> --description <msg> --log <msg>" >&2
  exit 1
fi

case "$mode" in
  baseline|quick|full) ;;
  *)
    echo "Unknown mode: $mode (expected baseline, quick, or full)" >&2
    exit 1
    ;;
 esac

metric_name=""
case "$branch" in
  sort) metric_name="sort_time_ms" ;;
  search) metric_name="search_time_ms" ;;
  filter) metric_name="filter_time_ms" ;;
  finance) metric_name="finance_sharpe_neg" ;;
  *)
    echo "Unknown branch: $branch (expected sort, search, filter, or finance)" >&2
    exit 1
    ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

results_dir="$repo_root/results"
if [[ -z "$log_dir" ]]; then
  log_dir="$results_dir/logs"
fi
mkdir -p "$results_dir" "$log_dir"

tsv="$results_dir/results_${branch}.tsv"
branch_log="$log_dir/${branch}.log"

# Compute best keep metric so far (lower is better).
best_before=""
if [[ -f "$tsv" ]]; then
  best_before="$(awk -F'\t' 'NR>1 && tolower($4)=="keep" { v=$2+0; if (m=="" || v<m) m=v } END { if (m!="") printf "%.6f", m }' "$tsv" || true)"
fi

run_oracle() {
  local oracle_mode="$1"
  local out_file="$2"
  if [[ "$branch" == "finance" ]]; then
    python3 oracles/evaluate_finance.py --mode "$oracle_mode" > "$out_file" 2>&1 || return 1
  else
    python3 oracles/evaluate.py --branch "$branch" --mode "$oracle_mode" > "$out_file" 2>&1 || return 1
  fi
}

parse_metric() {
  local out_file="$1"
  local line
  line="$(grep -E "^${metric_name}:" "$out_file" | head -n 1 || true)"
  if [[ -z "$line" ]]; then
    echo ""
  else
    echo "$line" | awk '{print $2}'
  fi
}

append_log() {
  local label="$1"
  local out_file="$2"
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  {
    echo "===== ${ts} mode=${label} desc=${description} ====="
    cat "$out_file"
    echo
  } >> "$branch_log"
}

status="crash"
metric_value="0.0"
quick_value=""
promoted="no"

oracle_mode="$mode"
if [[ "$mode" == "baseline" ]]; then
  oracle_mode="full"
fi

run_tmp="$(mktemp "$log_dir/${branch}_tmp.XXXXXX")"
trap 'rm -f "$run_tmp"' EXIT

if run_oracle "$oracle_mode" "$run_tmp"; then
  append_log "$oracle_mode" "$run_tmp"
  metric_value="$(parse_metric "$run_tmp")"
  if [[ -z "$metric_value" ]]; then
    metric_value="0.0"
    status="crash"
  else
    status="discard"
  fi
else
  append_log "$oracle_mode" "$run_tmp"
  status="crash"
fi

if [[ "$mode" == "quick" && "$status" != "crash" ]]; then
  quick_value="$metric_value"
  improved="no"
  if [[ -z "$best_before" ]]; then
    improved="yes"
  else
    if echo "" | awk 'BEGIN { best=ARGV[1]+0.0; cur=ARGV[2]+0.0; exit(cur < best ? 0 : 1) }' "$best_before" "$metric_value"; then
      improved="yes"
    fi
  fi

  if [[ "$improved" == "yes" ]]; then
    promoted="yes"
    run_tmp_full="$(mktemp "$log_dir/${branch}_tmp_full.XXXXXX")"
    if run_oracle "full" "$run_tmp_full"; then
      append_log "full" "$run_tmp_full"
      metric_value="$(parse_metric "$run_tmp_full")"
      if [[ -z "$metric_value" ]]; then
        metric_value="0.0"
        status="crash"
      else
        status="discard"
      fi
    else
      append_log "full" "$run_tmp_full"
      status="crash"
    fi
    rm -f "$run_tmp_full"
  fi
fi

if [[ "$status" != "crash" ]]; then
  improved="yes"
  if [[ -n "$best_before" ]]; then
    if echo "" | awk 'BEGIN { best=ARGV[1]+0.0; cur=ARGV[2]+0.0; exit(cur < best ? 0 : 1) }' "$best_before" "$metric_value"; then
      improved="yes"
    else
      improved="no"
    fi
  fi

  if [[ "$mode" == "baseline" ]]; then
    status="keep"
  else
    if [[ "$improved" == "yes" ]]; then
      status="keep"
    else
      status="discard"
    fi
  fi
fi

commit="none"
if [[ "$mode" == "baseline" ]]; then
  if [[ "$status" == "keep" ]]; then
    commit="$(git rev-parse --short HEAD)"
  fi
elif [[ "$status" == "keep" ]]; then
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

if [[ "$mode" == "quick" && "$promoted" == "yes" ]]; then
  log_msg="${log_msg} | quick=${quick_value} full=${metric_value}"
fi

# Append TSV row (commit may be "none" for discard/crash).
python3 scripts/append_tsv.py "$branch" "$commit" "$metric_value" "0.0" "$status" "$description" "$log_msg"

best_after="$best_before"
if [[ "$status" == "keep" ]]; then
  if [[ -z "$best_before" ]]; then
    best_after="$metric_value"
  else
    if echo "" | awk 'BEGIN { best=ARGV[1]+0.0; cur=ARGV[2]+0.0; exit(cur < best ? 0 : 1) }' "$best_before" "$metric_value"; then
      best_after="$metric_value"
    fi
  fi
fi

echo "status=$status"
echo "metric=$metric_value"
echo "best_before=${best_before:-none}"
echo "best_after=${best_after:-none}"
echo "commit=$commit"
