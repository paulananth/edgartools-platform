#!/usr/bin/env bash
# Run the full MDM ingestion sequence end-to-end.
#
# Architecture:
#   sec_tracked_universe in silver.duckdb controls which companies are bootstrapped.
#   seed-universe populates it; bootstrap-recent-10 reads from it.
#   Never pass a CIK list at runtime — the seed table IS the scope control.
#
# Steps:
#   1  seed-universe         Seed sec_tracked_universe in silver.duckdb (scope control)
#   2  bootstrap-recent-10   Fetch 10 most recent submissions per tracked company → silver.duckdb
#   3  mdm migrate           Apply schema + seed reference data in Azure SQL
#   4  mdm run               Load entities from silver into Azure SQL
#   5  mdm sync-graph        Push pending relationship instances to Neo4j
#   6  mdm verify-graph      Query Neo4j for node/edge counts
#   7  mdm counts            Print all MDM table row counts
#
# Usage:
#   ./run-mdm-pipeline.sh --env dev --universe-limit 100
#   ./run-mdm-pipeline.sh --env dev --skip-seed --skip-bootstrap   # silver already populated
#   ./run-mdm-pipeline.sh --env dev --skip-migrate                 # schema already current
#
# Options:
#   --env ENV              dev or prod (required)
#   --universe-limit N     Limit companies seeded into sec_tracked_universe (default: all).
#                          Use 100 for dev to avoid OOM on full 7993-company universe.
#   --skip-seed            Skip step 1 (sec_tracked_universe already seeded).
#   --skip-bootstrap       Skip step 2 (silver.duckdb already populated).
#   --skip-migrate         Skip step 3 (schema already current).
#   --graph-limit N        Max relationships to sync to Neo4j in step 5 (default: 100).
#   --mdm-run-limit N      Override mdm run with --limit N. Default uses deployed job args.
#   --resource-group RG    Resource group override.
#   --name-prefix PREFIX   Runtime resource prefix. Default: edgartools-<env>.
#   --fail-fast            Exit immediately if any step fails.

set -euo pipefail

ENVIRONMENT=""
RESOURCE_GROUP=""
NAME_PREFIX=""
UNIVERSE_LIMIT=""
SKIP_SEED=false
SKIP_BOOTSTRAP=false
SKIP_MIGRATE=false
GRAPH_LIMIT=100
MDM_RUN_LIMIT=""
FAIL_FAST=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)              ENVIRONMENT="${2:?}";     shift 2 ;;
    --resource-group)   RESOURCE_GROUP="${2:?}";  shift 2 ;;
    --name-prefix)      NAME_PREFIX="${2:?}";     shift 2 ;;
    --universe-limit)   UNIVERSE_LIMIT="${2:?}";  shift 2 ;;
    --skip-seed)        SKIP_SEED=true;          shift ;;
    --skip-bootstrap)   SKIP_BOOTSTRAP=true;     shift ;;
    --skip-migrate)     SKIP_MIGRATE=true;       shift ;;
    --graph-limit)      GRAPH_LIMIT="${2:?}";    shift 2 ;;
    --mdm-run-limit)    MDM_RUN_LIMIT="${2:?}";  shift 2 ;;
    --fail-fast)        FAIL_FAST=true;          shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -z "$ENVIRONMENT" ]] && { echo "ERROR: --env is required" >&2; exit 2; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_ROOT="${REPO_ROOT}/infra/terraform/azure/accounts/${ENVIRONMENT}"
NAME_PREFIX="${NAME_PREFIX:-edgartools-${ENVIRONMENT}}"

tf_out()      { terraform -chdir="$TF_ROOT" output -raw  "$1" 2>/dev/null || true; }
tf_out_json() { terraform -chdir="$TF_ROOT" output -json "$1" 2>/dev/null || echo "{}"; }

SUBSCRIPTION="$(az account show --query id -o tsv 2>/dev/null)"

RESOURCE_GROUP="${RESOURCE_GROUP:-$(tf_out resource_group_name)}"
RESOURCE_GROUP="${RESOURCE_GROUP:-${NAME_PREFIX}-rg}"
WAREHOUSE_ROOT="$(tf_out warehouse_storage_root)"
STORAGE_ACCOUNT="$(echo "$WAREHOUSE_ROOT" | python3 -c \
  "import sys,re; m=re.search(r'@([^.]+)',sys.stdin.read()); print(m.group(1) if m else '')" 2>/dev/null || true)"

json_output_value() {
  local output_name="$1" key="$2" default_value="$3"
  tf_out_json "$output_name" | python3 - "$key" "$default_value" <<'PY' 2>/dev/null || true
import json
import sys

key, default = sys.argv[1:]
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
if not isinstance(data, dict):
    data = {}
print(data.get(key) or default)
PY
}

SEED_JOB="$(json_output_value container_app_job_names seed_universe "${NAME_PREFIX}-seed-universe")"
BOOT_JOB="$(json_output_value container_app_job_names bootstrap_recent_10 "${NAME_PREFIX}-boot-recent-10")"
MIGRATE_JOB="$(json_output_value mdm_container_app_job_names migrate "${NAME_PREFIX}-mdm-migrate")"
RUN_JOB="$(json_output_value mdm_container_app_job_names run "${NAME_PREFIX}-mdm-run")"
SYNC_JOB="$(json_output_value mdm_container_app_job_names sync_graph "${NAME_PREFIX}-mdm-graph-sync")"
VERIFY_JOB="$(json_output_value mdm_container_app_job_names verify_graph "${NAME_PREFIX}-mdm-graph-verify")"
COUNTS_JOB="$(json_output_value mdm_container_app_job_names counts "${NAME_PREFIX}-mdm-counts")"

# Track results for summary
# Step status — stored as plain variables (STEP_<name>) for bash 3.2 compat
# (macOS ships bash 3.2 which does not support declare -A associative arrays)
_step_set()  { eval "STEP_${1}=${2}"; }
_step_get()  { eval "echo \${STEP_${1}:-SKIP}"; }

# ---------------------------------------------------------------------------
# Helper: start a Container App Job via REST API with an optional args override.
#
# Why REST API and not `az containerapp job start --args`?
# The Azure CLI argument parser treats any token starting with -- as its OWN
# flag, so passing container flags like --cik-list or --limit through --args
# silently fails or errors.  Using `az rest` sends the args as a JSON array
# directly to the ARM API, bypassing the CLI parser entirely.
#
# Usage:
#   start_job_rest <subscription> <rg> <job> <container> [arg1 arg2 ...]
# Returns the execution name on stdout.
#
# Body format note (5-whys root cause of previous silent failure):
#   Why the {"template":{...}} wrapper was wrong: ARM API type is
#   StartJobExecutionTemplate — the body IS the template content directly.
#   Wrapping in {"template":{...}} returns HTTP 400 "Unknown properties".
#   Correct format: {"containers":[{"name":"...","image":"...","args":[...]}]}
#   The "image" field is required; without it Azure ignores the container override.
# ---------------------------------------------------------------------------
start_job_rest() {
  local subscription="$1" rg="$2" job="$3" container="$4"
  shift 4

  local body
  if [[ $# -gt 0 ]]; then
    # Fetch the image from the job definition so we can include it in the override
    local image
    image="$(az containerapp job show --name "$job" --resource-group "$rg" \
      --query "properties.template.containers[0].image" -o tsv 2>/dev/null)"
    body="$(python3 -c "
import json, sys
container, image, *args = sys.argv[1:]
print(json.dumps({'containers':[{'name': container, 'image': image, 'args': args}]}))
" "$container" "$image" "$@")"
  else
    body="{}"
  fi

  az rest \
    --method post \
    --url "https://management.azure.com/subscriptions/${subscription}/resourceGroups/${rg}/providers/Microsoft.App/jobs/${job}/start?api-version=2024-03-01" \
    --body "${body}" \
    --query "name" -o tsv 2>/dev/null
}

# ---------------------------------------------------------------------------
# Helper: start a job, poll to completion, print logs, set STEP_STATUS.
# container_name is used for log streaming (edgar-warehouse or mdm).
# All extra positional args after container_name are forwarded as container args.
# ---------------------------------------------------------------------------
run_job() {
  local label="$1" job="$2" rg="$3" container_name="$4"
  shift 4   # remaining args → container args

  if [[ -z "$job" ]]; then
    echo "  SKIP — job name not found in terraform outputs"
    _step_set "$label" SKIP
    return 0
  fi

  local exec_name
  exec_name="$(start_job_rest "$SUBSCRIPTION" "$rg" "$job" "$container_name" "$@")"
  if [[ -z "$exec_name" ]]; then
    echo "  ERROR — failed to start job $job"
    _step_set "$label" FAIL
    [[ "$FAIL_FAST" == "true" ]] && { print_summary; exit 1; }
    return 0
  fi
  echo "  started: ${exec_name}"

  local status="Running"
  while true; do
    status="$(az containerapp job execution show \
      --name "$job" --resource-group "$rg" \
      --job-execution-name "$exec_name" \
      --query "properties.status" -o tsv 2>/dev/null || echo "Running")"
    case "$status" in
      Succeeded) echo "  done: $status"; _step_set "$label" OK; break ;;
      Failed|Stopped)
        echo "  ERROR: $status"; _step_set "$label" FAIL
        _print_job_logs "$job" "$rg" "$exec_name" "$container_name" 40
        [[ "$FAIL_FAST" == "true" ]] && { print_summary; exit 1; }
        break ;;
    esac
    echo "  [${job}] ${status}…"; sleep 20
  done

  # Best-effort log output on success too (shows counts/stats)
  [[ "$(_step_get $label)" == "OK" ]] && \
    _print_job_logs "$job" "$rg" "$exec_name" "$container_name" 60
}

# Internal: stream and pretty-print last N lines from a job execution.
_print_job_logs() {
  local job="$1" rg="$2" exec_name="$3" container="$4" tail_n="${5:-60}"
  az containerapp job logs show \
    --name "$job" --resource-group "$rg" \
    --execution "$exec_name" --container "$container" \
    --tail "$tail_n" 2>/dev/null | \
  python3 -c "
import sys, json
lines = []
for raw in sys.stdin:
    try:
        log = json.loads(raw.strip()).get('Log','')
    except Exception:
        log = raw.strip()
    if not log or 'Connecting to' in log or 'Successfully Connected' in log:
        continue
    lines.append(log)
for log in lines[-${tail_n}:]:
    try:
        inner = json.loads(log)
        for k,v in sorted(inner.items()):
            print(f'    {k:<42}: {v}')
    except Exception:
        print(f'    {log[-150:]}')
" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Helper: check silver.duckdb size
# ---------------------------------------------------------------------------
silver_size() {
  az storage blob show \
    --container-name warehouse \
    --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --name "warehouse/silver/sec/silver.duckdb" \
    --query "properties.contentLength" -o tsv 2>/dev/null || echo "0"
}

# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------
print_summary() {
  echo ""
  echo "================================================"
  echo " PIPELINE RUN SUMMARY — env=${ENVIRONMENT}"
  echo "================================================"
  local all_ok=true
  for step in seed bootstrap migrate run sync-graph verify-graph counts; do
    local s="$(_step_get $step)"
    local icon="✓"
    [[ "$s" == "FAIL" ]] && { icon="✗"; all_ok=false; }
    [[ "$s" == "SKIP" ]] && icon="-"
    printf "  %-20s %s  %s\n" "$step" "$icon" "$s"
  done
  echo ""
  if [[ "$all_ok" == "true" ]]; then
    echo "  All completed steps succeeded."
  else
    echo "  One or more steps FAILED — run ./check-pipeline-health.sh --env ${ENVIRONMENT} for details."
  fi
  echo "================================================"
}

echo "================================================"
echo " MDM Pipeline Run — env=${ENVIRONMENT}"
echo " Resource group  : ${RESOURCE_GROUP}"
echo " Storage account : ${STORAGE_ACCOUNT}"
[[ -n "$UNIVERSE_LIMIT" ]] && echo " Universe limit  : ${UNIVERSE_LIMIT} companies"
echo "================================================"

# ---------------------------------------------------------------------------
# STEP 1: Seed universe (populate sec_tracked_universe in silver.duckdb)
# sec_tracked_universe is the scope control for bootstrap-recent-10.
# --universe-limit scopes dev to N companies, avoiding OOM on the full universe.
# ---------------------------------------------------------------------------
echo ""
echo "==> [1/7] SEED UNIVERSE (populate sec_tracked_universe in silver.duckdb)"

if [[ "$SKIP_SEED" == "true" ]]; then
  echo "  --skip-seed set — skipping"
  _step_set seed SKIP
else
  # Idempotency: skip if silver already has a non-empty tracked universe
  SILVER_BYTES="$(silver_size)"; SILVER_BYTES="${SILVER_BYTES:-0}"
  if [[ "$SILVER_BYTES" -gt 0 ]]; then
    echo "  silver.duckdb already populated (${SILVER_BYTES} bytes) — skipping seed (data unchanged at source)"
    _step_set seed SKIP
  elif [[ -n "$UNIVERSE_LIMIT" ]]; then
    echo "  universe-limit: ${UNIVERSE_LIMIT} companies"
    run_job "seed" "$SEED_JOB" "$RESOURCE_GROUP" "edgar-warehouse" \
      seed-universe --limit "$UNIVERSE_LIMIT"
  else
    echo "  universe-limit: all (full SEC universe — may OOM in dev; use --universe-limit)"
    run_job "seed" "$SEED_JOB" "$RESOURCE_GROUP" "edgar-warehouse"
  fi
fi

# ---------------------------------------------------------------------------
# STEP 2: Bootstrap (fetch 10 most recent submissions per tracked company)
# Reads sec_tracked_universe; uses --no-include-reference-refresh so it does
# NOT rebuild the universe from the full SEC tickers file.
# ---------------------------------------------------------------------------
echo ""
echo "==> [2/7] BOOTSTRAP (fetch submissions for tracked companies → silver.duckdb)"

if [[ "$SKIP_BOOTSTRAP" == "true" ]]; then
  SIZE="$(silver_size)"; SIZE="${SIZE:-0}"
  if [[ "$SIZE" -gt 0 ]]; then
    echo "  --skip-bootstrap: silver.duckdb is ${SIZE} bytes — OK"
  else
    echo "  WARNING: --skip-bootstrap set but silver.duckdb is 0 bytes — MDM will find no data"
  fi
  _step_set bootstrap SKIP
else
  run_job "bootstrap" "$BOOT_JOB" "$RESOURCE_GROUP" "edgar-warehouse"

  SIZE="$(silver_size)"; SIZE="${SIZE:-0}"
  if [[ "$SIZE" -gt 0 ]]; then
    MB=$(python3 -c "print(f'{${SIZE}/1048576:.1f}')" 2>/dev/null || echo "?")
    echo "  silver.duckdb: ${SIZE} bytes (${MB} MB) — POPULATED"
  else
    echo "  ERROR: silver.duckdb still 0 bytes after bootstrap"
    _step_set bootstrap FAIL
    [[ "$FAIL_FAST" == "true" ]] && { print_summary; exit 1; }
  fi
fi

# ---------------------------------------------------------------------------
# STEP 3: MDM migrate (schema + seed)
# ---------------------------------------------------------------------------
echo ""
echo "==> [3/7] MDM MIGRATE (schema + seed reference data)"

if [[ "$SKIP_MIGRATE" == "true" ]]; then
  echo "  --skip-migrate set — skipping"
  _step_set migrate SKIP
else
  run_job "migrate" "$MIGRATE_JOB" "$RESOURCE_GROUP" "mdm"
fi

# ---------------------------------------------------------------------------
# STEP 4: MDM run (load entities from silver)
# ---------------------------------------------------------------------------
echo ""
echo "==> [4/7] MDM RUN (load entities: company → adviser → security → person → fund)"
if [[ -n "$MDM_RUN_LIMIT" ]]; then
  echo "  limit override: ${MDM_RUN_LIMIT}"
  run_job "run" "$RUN_JOB" "$RESOURCE_GROUP" "mdm" \
    mdm run --entity-type all --limit "$MDM_RUN_LIMIT"
else
  echo "  using deployed job default args; pass --mdm-run-limit to override"
  run_job "run" "$RUN_JOB" "$RESOURCE_GROUP" "mdm"
fi

# ---------------------------------------------------------------------------
# STEP 5: MDM sync-graph (push pending relationships to Neo4j)
# ---------------------------------------------------------------------------
echo ""
echo "==> [5/7] MDM SYNC-GRAPH (push pending relationship instances to Neo4j)"
echo "  limit: ${GRAPH_LIMIT}"
run_job "sync-graph" "$SYNC_JOB" "$RESOURCE_GROUP" "mdm" \
  mdm sync-graph --limit "$GRAPH_LIMIT"

# ---------------------------------------------------------------------------
# STEP 6: Verify Neo4j graph
# ---------------------------------------------------------------------------
echo ""
echo "==> [6/7] MDM VERIFY-GRAPH (node + edge counts in Neo4j)"
run_job "verify-graph" "$VERIFY_JOB" "$RESOURCE_GROUP" "mdm"

# ---------------------------------------------------------------------------
# STEP 7: MDM counts (final row counts in Azure SQL)
# ---------------------------------------------------------------------------
echo ""
echo "==> [7/7] MDM COUNTS (Azure SQL table row counts)"
run_job "counts" "$COUNTS_JOB" "$RESOURCE_GROUP" "mdm"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print_summary
