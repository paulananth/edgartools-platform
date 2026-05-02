#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  deploy-azure-stack.sh --env <dev|prod> [--key-vault-only] [--skip-apply]

Initializes and plans/applies the Azure Terraform root. The root provisions passive
infrastructure only; image publishing, secret population, and job execution are
separate post-infra operator actions.
USAGE
}

ENVIRONMENT=""
KEY_VAULT_ONLY="false"
SKIP_APPLY="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --key-vault-only) KEY_VAULT_ONLY="true"; shift ;;
    --skip-apply) SKIP_APPLY="true"; shift ;;
    --start-validation-job) echo "--start-validation-job was removed; run validation through a post-infra operator script." >&2; exit 2 ;;
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
