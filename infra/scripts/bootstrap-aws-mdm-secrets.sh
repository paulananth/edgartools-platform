#!/usr/bin/env bash
# bootstrap-aws-mdm-secrets.sh
#
# Reads the AWS-managed RDS master user secret created by Terraform and writes a
# complete PostgreSQL DSN to the operator-facing postgres_dsn Secrets Manager secret.
#
# Run once after `terraform apply` with mdm_enabled = true. Idempotent — safe to re-run.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bootstrap-aws-mdm-secrets.sh --env <dev|prod> [options]

Populates the MDM postgres_dsn Secrets Manager secret from the RDS master user secret
produced by Terraform. Run after `terraform apply` with mdm_enabled = true.

Options:
  --env <dev|prod>          Environment. Required.
  --aws-profile <profile>   AWS CLI profile. Default: AWS_PROFILE env var or instance role.
  --aws-region <region>     AWS region. Default: us-east-1.
  --terraform-root <path>   Terraform accounts root. Default: infra/terraform/accounts/<env>.
  --db-name <name>          PostgreSQL database name to include in the DSN. Default: mdm.
  --dry-run                 Print the masked DSN without writing to Secrets Manager.
  -h, --help                Show this help.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

log() {
  echo "==> $*" >&2
}

ENVIRONMENT=""
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
TF_ROOT=""
DB_NAME="mdm"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --terraform-root) TF_ROOT="${2:?}"; shift 2 ;;
    --db-name) DB_NAME="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$ENVIRONMENT" == "dev" || "$ENVIRONMENT" == "prod" ]] || { usage >&2; exit 2; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_ROOT="${TF_ROOT:-${REPO_ROOT}/infra/terraform/accounts/${ENVIRONMENT}}"

aws_cli() {
  local args=()
  [[ -n "$AWS_PROFILE_NAME" ]] && args+=(--profile "$AWS_PROFILE_NAME")
  aws "${args[@]}" --region "$AWS_REGION_NAME" "$@"
}

tf_raw() {
  terraform -chdir="$TF_ROOT" output -raw "$1" 2>/dev/null || true
}

is_empty() {
  [[ -z "${1:-}" || "${1:-}" == "null" || "${1:-}" == "None" ]]
}

log "Reading Terraform outputs from ${TF_ROOT}"
MASTER_SECRET_ARN="$(tf_raw mdm_db_master_user_secret_arn)"
DSN_SECRET_ARN="$(tf_raw mdm_postgres_dsn_secret_arn)"
DB_ENDPOINT="$(tf_raw mdm_db_endpoint)"

is_empty "$MASTER_SECRET_ARN" && fail "mdm_db_master_user_secret_arn not found in Terraform output. Is mdm_enabled = true and terraform apply complete?"
is_empty "$DSN_SECRET_ARN"    && fail "mdm_postgres_dsn_secret_arn not found in Terraform output."
is_empty "$DB_ENDPOINT"       && fail "mdm_db_endpoint not found in Terraform output."

log "Reading RDS master user credentials from Secrets Manager"
MASTER_SECRET_JSON="$(aws_cli secretsmanager get-secret-value \
  --secret-id "$MASTER_SECRET_ARN" \
  --query SecretString \
  --output text)"

DB_USER="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['username'])" "$MASTER_SECRET_JSON")"
DB_PASS="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['password'])" "$MASTER_SECRET_JSON")"
DB_PASS_ENC="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$DB_PASS")"

DSN="postgresql://${DB_USER}:${DB_PASS_ENC}@${DB_ENDPOINT}:5432/${DB_NAME}"

if [[ "$DRY_RUN" == "true" ]]; then
  log "DRY RUN — DSN (password masked):"
  echo "postgresql://${DB_USER}:***@${DB_ENDPOINT}:5432/${DB_NAME}"
  exit 0
fi

log "Writing DSN to ${DSN_SECRET_ARN}"
aws_cli secretsmanager put-secret-value \
  --secret-id "$DSN_SECRET_ARN" \
  --secret-string "$DSN" \
  --output text >/dev/null

log "Done. MDM_DATABASE_URL is now set in Secrets Manager (${DSN_SECRET_ARN})."
log "Next: run deploy-aws-application.sh --enable-mdm, then start the mdm-migrate state machine."
