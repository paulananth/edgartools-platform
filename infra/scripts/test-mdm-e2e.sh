#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  test-mdm-e2e.sh --env <dev|prod> [--skip-neo4j] [--skip-migrate] [--start-container-jobs]

Hydrates MDM secrets from Azure Key Vault/Terraform outputs, checks Azure SQL
and Neo4j connectivity, applies MDM migrations, and prints MDM table counts.

Set EDGAR_WAREHOUSE_CMD to override the local command, for example:
  EDGAR_WAREHOUSE_CMD="uv run --extra mdm edgar-warehouse"
USAGE
}

ENVIRONMENT=""
SKIP_NEO4J="false"
SKIP_MIGRATE="false"
START_CONTAINER_JOBS="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
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
CMD="${EDGAR_WAREHOUSE_CMD:-edgar-warehouse}"

# Auto-install the package if edgar-warehouse is not on PATH
if [[ "$CMD" == "edgar-warehouse" ]] && ! command -v edgar-warehouse &>/dev/null; then
  echo "edgar-warehouse not found; installing from ${REPO_ROOT} ..." >&2
  pip install -e "${REPO_ROOT}[mdm]" --quiet
fi

terraform_output() {
  terraform -chdir="$TF_ROOT" output -raw "$1"
}

secret_value() {
  az keyvault secret show --id "$1" --query value -o tsv --only-show-errors
}

json_field() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(payload[sys.argv[2]])
PY
}

run_cmd() {
  # shellcheck disable=SC2086
  $CMD "$@"
}

DB_SECRET_ID="$(terraform_output mdm_database_url_secret_id)"
NEO4J_SECRET_ID="$(terraform_output mdm_neo4j_secret_id)"
API_SECRET_ID="$(terraform_output mdm_api_keys_secret_id)"

if [[ -z "$DB_SECRET_ID" || "$DB_SECRET_ID" == "null" ]]; then
  echo "ERROR: MDM is not enabled or mdm_database_url_secret_id is unavailable." >&2
  exit 1
fi

export MDM_DATABASE_URL
MDM_DATABASE_URL="$(secret_value "$DB_SECRET_ID")"

if [[ "$SKIP_NEO4J" == "false" ]]; then
  NEO4J_JSON="$(secret_value "$NEO4J_SECRET_ID")"
  export NEO4J_URI NEO4J_USER NEO4J_PASSWORD
  NEO4J_URI="$(json_field "$NEO4J_JSON" uri)"
  NEO4J_USER="$(json_field "$NEO4J_JSON" user)"
  NEO4J_PASSWORD="$(json_field "$NEO4J_JSON" password)"
fi

if [[ -n "${API_SECRET_ID:-}" && "$API_SECRET_ID" != "null" ]]; then
  export MDM_API_KEYS
  MDM_API_KEYS="$(secret_value "$API_SECRET_ID")"
fi

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
  RESOURCE_GROUP="$(terraform_output resource_group_name)"
  JOBS_JSON="$(terraform -chdir="$TF_ROOT" output -json mdm_container_app_job_names)"
  python3 - "$JOBS_JSON" "$RESOURCE_GROUP" <<'PY'
import json
import subprocess
import sys

jobs = json.loads(sys.argv[1])
resource_group = sys.argv[2]
for key in ("migrate", "run", "counts", "backfill_relationships", "sync_graph"):
    name = jobs.get(key)
    if not name:
        continue
    print(f"Starting MDM Container Apps Job {key}: {name}", flush=True)
    subprocess.run(
        ["az", "containerapp", "job", "start", "--name", name, "--resource-group", resource_group],
        check=True,
    )
PY
fi
