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

# Run a job and block until Succeeded or Failed.
# Prints job name + execution name + final status.
# Returns 0 on Succeeded, 1 on Failed/Stopped.
run_job() {
  local job="$1" rg="$2"
  local exec_name
  exec_name="$(az containerapp job start \
    --name "${job}" --resource-group "${rg}" \
    --query "name" -o tsv)"
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

  echo "${exec_name}"   # last line = execution name for log query
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

BACKFILL_JOB="$(get_job backfill_relationships)"
COUNTS_JOB="$(get_job counts)"
VERIFY_JOB="$(get_job verify_graph)"

LOG_WORKSPACE="$(az monitor log-analytics workspace list \
  --resource-group "${RESOURCE_GROUP}" \
  --query "[0].customerId" -o tsv 2>/dev/null || echo "")"

echo "    resource_group  : ${RESOURCE_GROUP}"
echo "    backfill job    : ${BACKFILL_JOB}"
echo "    counts job      : ${COUNTS_JOB}"
echo "    verify job      : ${VERIFY_JOB}"
echo "    log workspace   : ${LOG_WORKSPACE:-none}"

# ---------------------------------------------------------------------------
# 2. Backfill relationship instances -> Neo4j
# ---------------------------------------------------------------------------
echo ""
echo "==> [1/3] Backfilling up to ${LIMIT} graph relationships ..."
BACKFILL_EXEC="$(run_job "${BACKFILL_JOB}" "${RESOURCE_GROUP}")"

if [[ -n "${LOG_WORKSPACE}" ]]; then
  echo "--- backfill output ---"
  fetch_job_logs "${LOG_WORKSPACE}" "${BACKFILL_EXEC}"
  echo "-----------------------"
fi

# ---------------------------------------------------------------------------
# 3. MDM table counts  (confirms mdm_relationship_instance rows written)
# ---------------------------------------------------------------------------
echo ""
echo "==> [2/3] Running MDM table counts ..."
COUNTS_EXEC="$(run_job "${COUNTS_JOB}" "${RESOURCE_GROUP}")"

if [[ -n "${LOG_WORKSPACE}" ]]; then
  echo "--- counts output ---"
  fetch_job_logs "${LOG_WORKSPACE}" "${COUNTS_EXEC}"
  echo "---------------------"
fi

# ---------------------------------------------------------------------------
# 4. Verify Neo4j graph
# ---------------------------------------------------------------------------
echo ""
echo "==> [3/3] Verifying Neo4j graph node/edge counts ..."
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
echo "    backfill : ${BACKFILL_EXEC}"
echo "    counts   : ${COUNTS_EXEC}"
echo "    verify   : ${VERIFY_EXEC}"
echo ""
echo "To inspect full job logs in Azure portal:"
echo "  Resource group : ${RESOURCE_GROUP}"
echo "  Jobs           : ${BACKFILL_JOB}  ${COUNTS_JOB}  ${VERIFY_JOB}"
