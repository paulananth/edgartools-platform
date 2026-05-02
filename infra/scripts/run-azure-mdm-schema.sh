#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  run-azure-mdm-schema.sh --env <dev|prod> [--resource-group <rg>] [--name-prefix <prefix>] [--no-seed]

Starts the post-infra MDM schema migration Container Apps Job and waits for it
to finish. The job itself is created by deploy-azure-runtime.sh.
USAGE
}

ENVIRONMENT=""
RESOURCE_GROUP=""
NAME_PREFIX=""
NO_SEED="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --resource-group) RESOURCE_GROUP="${2:?}"; shift 2 ;;
    --name-prefix) NAME_PREFIX="${2:?}"; shift 2 ;;
    --no-seed) NO_SEED="true"; shift ;;
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

tf_out() {
  terraform -chdir="$TF_ROOT" output -raw "$1" 2>/dev/null || true
}

RESOURCE_GROUP="${RESOURCE_GROUP:-$(tf_out resource_group_name)}"
if [[ -z "$RESOURCE_GROUP" || "$RESOURCE_GROUP" == "null" ]]; then
  echo "ERROR: --resource-group is required when Terraform outputs are unavailable." >&2
  exit 2
fi

JOB_NAME="${NAME_PREFIX}-mdm-migrate"
CONTAINER_NAME="mdm"
ARGS=(mdm migrate)
if [[ "$NO_SEED" == "true" ]]; then
  ARGS+=(--no-seed)
fi

SUBSCRIPTION_ID="$(az account show --query id -o tsv --only-show-errors)"
IMAGE="$(
  az containerapp job show \
    --name "$JOB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.template.containers[0].image" \
    -o tsv \
    --only-show-errors
)"

body="$(python3 - "$CONTAINER_NAME" "$IMAGE" "${ARGS[@]}" <<'PY'
import json
import sys

container_name, image, *args = sys.argv[1:]
print(json.dumps({"containers": [{"name": container_name, "image": image, "args": args}]}))
PY
)"

echo "Starting schema job: ${JOB_NAME}"
execution_name="$(
  az rest \
    --method post \
    --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.App/jobs/${JOB_NAME}/start?api-version=2024-03-01" \
    --body "$body" \
    --query name \
    -o tsv \
    --only-show-errors
)"

if [[ -z "$execution_name" ]]; then
  echo "ERROR: could not determine Container Apps Job execution name." >&2
  exit 1
fi

while true; do
  status="$(
    az containerapp job execution show \
      --name "$JOB_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --job-execution-name "$execution_name" \
      --query properties.status \
      -o tsv \
      --only-show-errors
  )"
  case "$status" in
    Succeeded)
      echo "Schema deployment succeeded: ${execution_name}"
      exit 0
      ;;
    Failed|Stopped|Canceled)
      echo "Schema deployment failed: ${execution_name} (${status})" >&2
      az containerapp job logs show \
        --name "$JOB_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --execution "$execution_name" \
        --container "$CONTAINER_NAME" \
        --tail 200 \
        --only-show-errors || true
      exit 1
      ;;
    *)
      echo "  ${execution_name}: ${status}"
      sleep 10
      ;;
  esac
done
