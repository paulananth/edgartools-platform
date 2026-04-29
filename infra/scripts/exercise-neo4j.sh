#!/usr/bin/env bash
# Exercise the Neo4j graph layer against Azure infrastructure.
#
# All secrets come from Azure Key Vault via Terraform — no local ODBC driver
# or credentials are required.
#
# Steps:
#   1. Pull job names + resource group from Terraform state
#   2. Run  mdm-graph-load   (backfill-relationships --limit N)
#   3. Run  mdm-counts       (show mdm_relationship_instance row count)
#   4. Run  mdm-graph-verify (query Neo4j for node/edge counts)
#   5. Print Log Analytics output from each job
#
# Usage:
#   ./exercise-neo4j.sh --env <dev|prod> [--limit N]
#
# Prerequisites:
#   az login  (already authenticated)
#   terraform state initialised for the target environment
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  exercise-neo4j.sh --env <dev|prod> [--limit N]

Options:
  --env   dev or prod (required)
  --limit Max relationships to backfill (default: 100)
USAGE
}

ENVIRONMENT=""
LIMIT="100"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)   ENVIRONMENT="${2:?}"; shift 2 ;;
    --limit) LIMIT="${2:?}";       shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  usage >&2; exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_ROOT="${REPO_ROOT}/infra/terraform/azure/accounts/${ENVIRONMENT}"

terraform_output()      { terraform -chdir="$TF_ROOT" output -raw  "$1"; }
terraform_output_json() { terraform -chdir="$TF_ROOT" output -json "$1"; }

SUBSCRIPTION="$(az account show --query id -o tsv 2>/dev/null)"

# Start a Container App Job via REST API with an optional container args override.
# Bypasses the Azure CLI parser, which eats flags like --limit and --cik-list.
# Usage: start_job_rest <rg> <job> <container> [arg1 arg2 ...]
# Prints the execution name on stdout.
start_job_rest() {
  local rg="$1" job="$2" container="$3"
  shift 3
  local body
  if [[ $# -gt 0 ]]; then
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
    --url "https://management.azure.com/subscriptions/${SUBSCRIPTION}/resourceGroups/${rg}/providers/Microsoft.App/jobs/${job}/start?api-version=2023-05-01" \
    --body "${body}" \
    --query "name" -o tsv 2>/dev/null
}

# Start a job (no args override) and block until Succeeded or Failed.
# Returns the execution name on the last stdout line.
run_job() {
  local job="$1" rg="$2"
  local exec_name
  exec_name="$(start_job_rest "$rg" "$job" "")"
  echo "    started: ${exec_name}"

  while true; do
    local status
    status="$(az containerapp job execution show \
      --name "${job}" --resource-group "${rg}" \
      --job-execution-name "${exec_name}" \
      --query "properties.status" -o tsv 2>/dev/null || echo "Running")"
    echo "    [${job}] ${status}"
    case "$status" in
      Succeeded) echo "    done."; break ;;
      Failed|Stopped) echo "ERROR: ${job} ended with ${status}" >&2; return 1 ;;
    esac
    sleep 15
  done

  echo "${exec_name}"
}

# Query Log Analytics for a job execution's console output.
# Waits up to 90 s for logs to flush before querying.
fetch_job_logs() {
  local workspace="$1" exec_name="$2"
  sleep 20
  az monitor log-analytics query \
    --workspace "${workspace}" \
    --analytics-query "ContainerAppConsoleLogs_CL
      | where Log_s != ''
      | where TimeGenerated > ago(10m)
      | where Log_s !has 'WARNING' and Log_s !has 'INFO' and Log_s !has 'DEBUG'
      | where ContainerAppName_s has '$(echo "${exec_name}" | cut -d- -f1-4)'
      | order by TimeGenerated asc
      | project Log_s" \
    --query "tables[0].rows[*][0]" -o tsv 2>/dev/null || echo "    (logs not yet available)"
}

# ---------------------------------------------------------------------------
# 1. Resolve infrastructure
# ---------------------------------------------------------------------------
echo "==> Resolving infrastructure for env=${ENVIRONMENT} ..."

RESOURCE_GROUP="$(terraform_output resource_group_name)"
JOBS_JSON="$(terraform_output_json mdm_container_app_job_names)"

get_job() { echo "$JOBS_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['$1'])"; }

RUN_JOB="$(get_job run)"
BACKFILL_JOB="$(get_job backfill_relationships)"
COUNTS_JOB="$(get_job counts)"
VERIFY_JOB="$(get_job verify_graph)"

LOG_WORKSPACE="$(az monitor log-analytics workspace list \
  --resource-group "${RESOURCE_GROUP}" \
  --query "[0].customerId" -o tsv 2>/dev/null || echo "")"

echo "    resource_group  : ${RESOURCE_GROUP}"
echo "    run job         : ${RUN_JOB}"
echo "    backfill job    : ${BACKFILL_JOB}"
echo "    counts job      : ${COUNTS_JOB}"
echo "    verify job      : ${VERIFY_JOB}"
echo "    log workspace   : ${LOG_WORKSPACE:-none}"

# ---------------------------------------------------------------------------
# 2. Run entity pipeline (loads companies, advisers, persons, securities, funds)
# ---------------------------------------------------------------------------
echo ""
echo "==> [1/4] Running MDM entity pipeline (limit set by Terraform mdm_run_limit) ..."
RUN_EXEC="$(run_job "${RUN_JOB}" "${RESOURCE_GROUP}")"

if [[ -n "${LOG_WORKSPACE}" ]]; then
  echo "--- run output ---"
  fetch_job_logs "${LOG_WORKSPACE}" "${RUN_EXEC}"
  echo "-----------------"
fi

# ---------------------------------------------------------------------------
# 3. Backfill relationship instances -> Neo4j
#    Pass --limit at runtime to honour the script's --limit flag.
# ---------------------------------------------------------------------------
echo ""
echo "==> [2/4] Backfilling up to ${LIMIT} graph relationships ..."
BACKFILL_EXEC="$(start_job_rest "${RESOURCE_GROUP}" "${BACKFILL_JOB}" "mdm" \
  mdm backfill-relationships --limit "${LIMIT}")"
echo "    started: ${BACKFILL_EXEC}"

while true; do
  _status="$(az containerapp job execution show \
    --name "${BACKFILL_JOB}" --resource-group "${RESOURCE_GROUP}" \
    --job-execution-name "${BACKFILL_EXEC}" \
    --query "properties.status" -o tsv 2>/dev/null || echo "Running")"
  echo "    [${BACKFILL_JOB}] ${_status}"
  case "$_status" in
    Succeeded) echo "    done."; break ;;
    Failed|Stopped) echo "ERROR: ${BACKFILL_JOB} ended with ${_status}" >&2; exit 1 ;;
  esac
  sleep 15
done

if [[ -n "${LOG_WORKSPACE}" ]]; then
  echo "--- backfill output ---"
  fetch_job_logs "${LOG_WORKSPACE}" "${BACKFILL_EXEC}"
  echo "-----------------------"
fi

# ---------------------------------------------------------------------------
# 4. MDM table counts  (confirms mdm_relationship_instance rows written)
# ---------------------------------------------------------------------------
echo ""
echo "==> [3/4] Running MDM table counts ..."
COUNTS_EXEC="$(run_job "${COUNTS_JOB}" "${RESOURCE_GROUP}")"

if [[ -n "${LOG_WORKSPACE}" ]]; then
  echo "--- counts output ---"
  fetch_job_logs "${LOG_WORKSPACE}" "${COUNTS_EXEC}"
  echo "---------------------"
fi

# ---------------------------------------------------------------------------
# 5. Verify Neo4j graph
# ---------------------------------------------------------------------------
echo ""
echo "==> [4/4] Verifying Neo4j graph node/edge counts ..."
VERIFY_EXEC="$(run_job "${VERIFY_JOB}" "${RESOURCE_GROUP}")"

if [[ -n "${LOG_WORKSPACE}" ]]; then
  echo "--- verify-graph output ---"
  fetch_job_logs "${LOG_WORKSPACE}" "${VERIFY_EXEC}"
  echo "---------------------------"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "==> All steps complete."
echo "    run      : ${RUN_EXEC}"
echo "    backfill : ${BACKFILL_EXEC}"
echo "    counts   : ${COUNTS_EXEC}"
echo "    verify   : ${VERIFY_EXEC}"
echo ""
echo "To inspect full job logs in Azure portal:"
echo "  Resource group : ${RESOURCE_GROUP}"
echo "  Jobs           : ${RUN_JOB}  ${BACKFILL_JOB}  ${COUNTS_JOB}  ${VERIFY_JOB}"
