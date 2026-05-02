#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  test-mdm-e2e.sh --env <dev|prod> [--skip-neo4j] [--skip-migrate] [--start-container-jobs]

Hydrates MDM secrets from Azure Key Vault runtime secret names, checks Azure SQL
and Neo4j connectivity, applies MDM migrations, and prints MDM table counts.

Set EDGAR_WAREHOUSE_CMD to override the local command, for example:
  EDGAR_WAREHOUSE_CMD="uv run --extra mdm edgar-warehouse"
USAGE
}

ENVIRONMENT=""
RESOURCE_GROUP=""
NAME_PREFIX=""
SKIP_NEO4J="false"
SKIP_MIGRATE="false"
START_CONTAINER_JOBS="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --resource-group) RESOURCE_GROUP="${2:?}"; shift 2 ;;
    --name-prefix) NAME_PREFIX="${2:?}"; shift 2 ;;
    --skip-neo4j) SKIP_NEO4J="true"; shift ;;
    --skip-migrate) SKIP_MIGRATE="true"; shift ;;
    --start-container-jobs) START_CONTAINER_JOBS="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  usage >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_ROOT="${REPO_ROOT}/infra/terraform/azure/accounts/${ENVIRONMENT}"
NAME_PREFIX="${NAME_PREFIX:-edgartools-${ENVIRONMENT}}"
CMD="${EDGAR_WAREHOUSE_CMD:-edgar-warehouse}"

# Auto-install the package if edgar-warehouse is not on PATH
if [[ "$CMD" == "edgar-warehouse" ]] && ! command -v edgar-warehouse &>/dev/null; then
  echo "edgar-warehouse not found; installing from ${REPO_ROOT} ..." >&2
  pip install -e "${REPO_ROOT}[mdm]" --quiet
fi

terraform_output() {
  terraform -chdir="$TF_ROOT" output -raw "$1" 2>/dev/null || true
}

run_cmd() {
  # shellcheck disable=SC2086
  $CMD "$@"
}

KEY_VAULT="$(terraform_output key_vault_name)"

secret_name() {
  az keyvault secret show \
    --vault-name "$KEY_VAULT" \
    --name "$1" \
    --query value -o tsv --only-show-errors
}

if [[ -z "$KEY_VAULT" || "$KEY_VAULT" == "null" ]]; then
  echo "ERROR: Key Vault output is unavailable; run Azure infra apply or pass environment with Terraform outputs." >&2
  exit 1
fi

export MDM_DATABASE_URL
MDM_DATABASE_URL="$(secret_name mdm-database-url)"

if [[ "$SKIP_NEO4J" == "false" ]]; then
  export NEO4J_URI NEO4J_USER NEO4J_PASSWORD
  NEO4J_URI="$(secret_name mdm-neo4j-uri)"
  NEO4J_USER="$(secret_name mdm-neo4j-user)"
  NEO4J_PASSWORD="$(secret_name mdm-neo4j-password)"
fi

export MDM_API_KEYS
MDM_API_KEYS="$(secret_name mdm-api-keys-csv 2>/dev/null || true)"

if [[ "$SKIP_NEO4J" == "true" ]]; then
  run_cmd mdm check-connectivity
else
  run_cmd mdm check-connectivity --neo4j
fi

if [[ "$SKIP_MIGRATE" == "false" ]]; then
  run_cmd mdm migrate
fi

run_cmd mdm counts

if [[ "$START_CONTAINER_JOBS" == "true" ]]; then
  RESOURCE_GROUP="${RESOURCE_GROUP:-$(terraform_output resource_group_name)}"
  RESOURCE_GROUP="${RESOURCE_GROUP:-${NAME_PREFIX}-rg}"
  python3 - "$NAME_PREFIX" "$RESOURCE_GROUP" <<'PY'
import subprocess
import sys

prefix, resource_group = sys.argv[1:]
jobs = {
    "migrate": f"{prefix}-mdm-migrate",
    "run": f"{prefix}-mdm-run",
    "counts": f"{prefix}-mdm-counts",
    "backfill_relationships": f"{prefix}-mdm-graph-load",
    "sync_graph": f"{prefix}-mdm-graph-sync",
}
for key, name in jobs.items():
    print(f"Starting MDM Container Apps Job {key}: {name}", flush=True)
    subprocess.run(
        ["az", "containerapp", "job", "start", "--name", name, "--resource-group", resource_group],
        check=True,
    )
PY
fi
