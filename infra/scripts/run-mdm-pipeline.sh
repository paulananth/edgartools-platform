#!/usr/bin/env bash
# Run the full MDM ingestion sequence end-to-end:
#
#   Step 1  bootstrap-recent-10   Populate silver.duckdb (skipped if already populated)
#   Step 2  mdm migrate           Apply schema + seed reference data
#   Step 3  mdm run               Load entities from silver into Azure SQL (company/adviser/…)
#   Step 4  mdm sync-graph        Push pending relationship instances to Neo4j
#   Step 5  mdm verify-graph      Query Neo4j for node/edge counts (pass/fail check)
#   Step 6  mdm counts            Print all MDM table row counts
#
# Usage:
#   ./run-mdm-pipeline.sh --env dev
#   ./run-mdm-pipeline.sh --env dev --cik-list 320193,789019,1018724
#   ./run-mdm-pipeline.sh --env dev --skip-bootstrap   # silver already populated
#   ./run-mdm-pipeline.sh --env dev --skip-migrate     # schema already current
#
# Options:
#   --env ENV            dev or prod (required)
#   --cik-list CIKS      Comma-separated CIK list for bootstrap (avoids full-universe run).
#                        Omit to run the full tracked universe.
#   --skip-bootstrap     Skip step 1 (use when silver.duckdb is already populated).
#   --skip-migrate       Skip step 2 (use when schema is already current).
#   --graph-limit N      Max relationships to sync to Neo4j in step 4 (default: 100).
#   --fail-fast          Exit immediately if any step fails (default: continue + report).

set -euo pipefail

ENVIRONMENT=""
CIK_LIST=""
SKIP_BOOTSTRAP=false
SKIP_MIGRATE=false
GRAPH_LIMIT=100
FAIL_FAST=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)             ENVIRONMENT="${2:?}";  shift 2 ;;
    --cik-list)        CIK_LIST="${2:?}";     shift 2 ;;
    --skip-bootstrap)  SKIP_BOOTSTRAP=true;  shift ;;
    --skip-migrate)    SKIP_MIGRATE=true;    shift ;;
    --graph-limit)     GRAPH_LIMIT="${2:?}"; shift 2 ;;
    --fail-fast)       FAIL_FAST=true;       shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -z "$ENVIRONMENT" ]] && { echo "ERROR: --env is required" >&2; exit 2; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_ROOT="${REPO_ROOT}/infra/terraform/azure/accounts/${ENVIRONMENT}"

tf_out()      { terraform -chdir="$TF_ROOT" output -raw  "$1" 2>/dev/null || true; }
tf_out_json() { terraform -chdir="$TF_ROOT" output -json "$1" 2>/dev/null || echo "{}"; }

SUBSCRIPTION="$(az account show --query id -o tsv 2>/dev/null)"

RESOURCE_GROUP="$(tf_out resource_group_name)"
WAREHOUSE_ROOT="$(tf_out warehouse_storage_root)"
STORAGE_ACCOUNT="$(echo "$WAREHOUSE_ROOT" | python3 -c \
  "import sys,re; m=re.search(r'@([^.]+)',sys.stdin.read()); print(m.group(1) if m else '')" 2>/dev/null || true)"

BOOT_JOB="$(tf_out_json container_app_job_names | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('bootstrap_recent_10',''))" 2>/dev/null || true)"

get_mdm_job() {
  tf_out_json mdm_container_app_job_names | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('$1',''))" 2>/dev/null || true
}
MIGRATE_JOB="$(get_mdm_job migrate)"
RUN_JOB="$(get_mdm_job run)"
SYNC_JOB="$(get_mdm_job sync_graph)"
VERIFY_JOB="$(get_mdm_job verify_graph)"
COUNTS_JOB="$(get_mdm_job counts)"

# Track results for summary
declare -A STEP_STATUS

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
# Returns the execution name on stdout; exits non-zero on failure.
# ---------------------------------------------------------------------------
start_job_rest() {
  local subscription="$1" rg="$2" job="$3" container="$4"
  shift 4

  local body
  if [[ $# -gt 0 ]]; then
    # Build {"template":{"containers":[{"name":"<c>","args":[...]}]}}
    body="$(python3 -c "
import json, sys
args = sys.argv[1:]
print(json.dumps({'template':{'containers':[{'name': args[0], 'args': args[1:]}]}}))
" -- "$container" "$@")"
  else
    body="{}"
  fi

  az rest \
    --method post \
    --url "https://management.azure.com/subscriptions/${subscription}/resourceGroups/${rg}/providers/Microsoft.App/jobs/${job}/start?api-version=2023-05-01" \
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
    STEP_STATUS["$label"]="SKIP"
    return 0
  fi

  local exec_name
  exec_name="$(start_job_rest "$SUBSCRIPTION" "$rg" "$job" "$container_name" "$@")"
  if [[ -z "$exec_name" ]]; then
    echo "  ERROR — failed to start job $job"
    STEP_STATUS["$label"]="FAIL"
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
      Succeeded) echo "  done: $status"; STEP_STATUS["$label"]="OK"; break ;;
      Failed|Stopped)
        echo "  ERROR: $status"; STEP_STATUS["$label"]="FAIL"
        _print_job_logs "$job" "$rg" "$exec_name" "$container_name" 40
        [[ "$FAIL_FAST" == "true" ]] && { print_summary; exit 1; }
        break ;;
    esac
    echo "  [${job}] ${status}…"; sleep 20
  done

  # Best-effort log output on success too (shows counts/stats)
  [[ "${STEP_STATUS[$label]}" == "OK" ]] && \
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
  for step in bootstrap migrate run sync-graph verify-graph counts; do
    local s="${STEP_STATUS[$step]:-SKIP}"
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
echo " Resource group : ${RESOURCE_GROUP}"
echo " Storage account: ${STORAGE_ACCOUNT}"
[[ -n "$CIK_LIST" ]] && echo " CIK list       : $(echo "$CIK_LIST" | tr ',' '\n' | wc -l | tr -d ' ') CIKs"
echo "================================================"

# ---------------------------------------------------------------------------
# STEP 1: Bootstrap (populate silver.duckdb)
# ---------------------------------------------------------------------------
echo ""
echo "==> [1/6] BOOTSTRAP (populate silver.duckdb)"

if [[ "$SKIP_BOOTSTRAP" == "true" ]]; then
  echo "  --skip-bootstrap set — checking current silver.duckdb size..."
  SIZE="$(silver_size)"
  if [[ "${SIZE:-0}" -gt 0 ]]; then
    echo "  silver.duckdb: ${SIZE} bytes — OK, skipping bootstrap"
    STEP_STATUS["bootstrap"]="SKIP"
  else
    echo "  WARNING: silver.duckdb is 0 bytes but --skip-bootstrap was set"
    echo "  MDM run will find no data. Remove --skip-bootstrap to re-run bootstrap."
    STEP_STATUS["bootstrap"]="SKIP"
  fi
else
  if [[ -n "$CIK_LIST" ]]; then
    echo "  Mode: explicit CIK list ($(echo "$CIK_LIST" | tr ',' '\n' | wc -l | tr -d ' ') CIKs)"
    run_job "bootstrap" "$BOOT_JOB" "$RESOURCE_GROUP" "edgar-warehouse" \
      bootstrap-recent-10 --cik-list "$CIK_LIST"
  else
    echo "  Mode: full tracked universe (WAREHOUSE_RUNTIME_MODE must be bronze_capture)"
    run_job "bootstrap" "$BOOT_JOB" "$RESOURCE_GROUP" "edgar-warehouse"
  fi

  echo ""
  SIZE="$(silver_size)"
  SIZE="${SIZE:-0}"
  if [[ "$SIZE" -gt 0 ]]; then
    MB=$(python3 -c "print(f'{${SIZE}/1048576:.1f}')" 2>/dev/null || echo "?")
    echo "  silver.duckdb: ${SIZE} bytes (${MB} MB) — POPULATED"
  else
    echo "  ERROR: silver.duckdb is still 0 bytes after bootstrap"
    echo "  Cannot proceed with MDM run — no silver data to read"
    STEP_STATUS["bootstrap"]="FAIL"
    if [[ "$FAIL_FAST" == "true" ]]; then print_summary; exit 1; fi
  fi
fi

# ---------------------------------------------------------------------------
# STEP 2: MDM migrate (schema + seed)
# ---------------------------------------------------------------------------
echo ""
echo "==> [2/6] MDM MIGRATE (schema + seed reference data)"

if [[ "$SKIP_MIGRATE" == "true" ]]; then
  echo "  --skip-migrate set — skipping"
  STEP_STATUS["migrate"]="SKIP"
else
  run_job "migrate" "$MIGRATE_JOB" "$RESOURCE_GROUP" "mdm"
fi

# ---------------------------------------------------------------------------
# STEP 3: MDM run (load entities from silver)
# ---------------------------------------------------------------------------
echo ""
echo "==> [3/6] MDM RUN (load entities: company → adviser → security → person → fund)"
echo "  (limit is baked into the job via Terraform mdm_run_limit)"
run_job "run" "$RUN_JOB" "$RESOURCE_GROUP" "mdm"

# ---------------------------------------------------------------------------
# STEP 4: MDM sync-graph (push pending relationships to Neo4j)
# ---------------------------------------------------------------------------
echo ""
echo "==> [4/6] MDM SYNC-GRAPH (push pending relationship instances to Neo4j)"
echo "  limit: ${GRAPH_LIMIT}"
run_job "sync-graph" "$SYNC_JOB" "$RESOURCE_GROUP" "mdm" \
  mdm sync-graph --limit "$GRAPH_LIMIT"

# ---------------------------------------------------------------------------
# STEP 5: Verify Neo4j graph
# ---------------------------------------------------------------------------
echo ""
echo "==> [5/6] MDM VERIFY-GRAPH (node + edge counts in Neo4j)"
run_job "verify-graph" "$VERIFY_JOB" "$RESOURCE_GROUP" "mdm"

# ---------------------------------------------------------------------------
# STEP 6: MDM counts (final row counts in Azure SQL)
# ---------------------------------------------------------------------------
echo ""
echo "==> [6/6] MDM COUNTS (Azure SQL table row counts)"
run_job "counts" "$COUNTS_JOB" "$RESOURCE_GROUP" "mdm"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print_summary
