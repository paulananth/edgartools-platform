#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  deploy-azure-stack.sh --env <dev|prod> [--key-vault-only] [--skip-apply] [--start-validation-job]

Initializes and plans/applies the Azure Terraform root. If --start-validation-job
is provided, starts the bootstrap_recent_10 Container Apps Job after apply.
USAGE
}

ENVIRONMENT=""
KEY_VAULT_ONLY="false"
SKIP_APPLY="false"
START_VALIDATION_JOB="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --key-vault-only) KEY_VAULT_ONLY="true"; shift ;;
    --skip-apply) SKIP_APPLY="true"; shift ;;
    --start-validation-job) START_VALIDATION_JOB="true"; shift ;;
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

cd "$TF_ROOT"
terraform init
if [[ "$KEY_VAULT_ONLY" == "true" ]]; then
  terraform plan -target=module.resource_group -target=module.key_vault -out=tfplan
else
  terraform plan -out=tfplan
fi

if [[ "$SKIP_APPLY" == "false" ]]; then
  terraform apply tfplan
fi

if [[ "$START_VALIDATION_JOB" == "true" ]]; then
  JOB_NAME="$(terraform output -raw bootstrap_recent_10_container_app_job_name)"
  RESOURCE_GROUP="$(terraform output -raw resource_group_name)"
  az containerapp job start --name "$JOB_NAME" --resource-group "$RESOURCE_GROUP"
fi
