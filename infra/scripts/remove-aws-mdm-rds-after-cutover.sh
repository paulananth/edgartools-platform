#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  remove-aws-mdm-rds-after-cutover.sh --env <dev|prod> --confirm-rds-removal [options]

Runs the strict Snowflake Postgres cutover audit, deletes the legacy AWS RDS MDM
instance with no final snapshot, then applies the AWS account Terraform root so
removed RDS-side resources are reconciled.

Options:
  --env <dev|prod>              Environment. Required.
  --aws-profile <profile>       AWS CLI profile.
  --aws-region <region>         AWS region. Default: us-east-1.
  --name-prefix <prefix>        Resource prefix. Default: edgartools-<env>.
  --manifest <path>             Deployment manifest. Default: infra/aws-<env>-application.json.
  --terraform-root <path>       Terraform accounts root. Default: infra/terraform/accounts/<env>.
  --expected-host <host>        Exact Snowflake Postgres host expected in the secret.
  --expected-host-suffix <suf>  Required host suffix. Default: .snowflake.app.
  --confirm-rds-removal         Required. Acknowledges no rollback and no final snapshot.
  --skip-terraform-apply        Delete the RDS instance only; operator will apply Terraform separately.
  --dry-run                     Print destructive commands after running non-destructive checks.
  -h, --help                    Show this help.
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
NAME_PREFIX=""
MANIFEST=""
TF_ROOT=""
EXPECTED_HOST=""
EXPECTED_HOST_SUFFIX=".snowflake.app"
CONFIRMED=false
SKIP_TERRAFORM_APPLY=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --name-prefix) NAME_PREFIX="${2:?}"; shift 2 ;;
    --manifest) MANIFEST="${2:?}"; shift 2 ;;
    --terraform-root) TF_ROOT="${2:?}"; shift 2 ;;
    --expected-host) EXPECTED_HOST="${2:?}"; shift 2 ;;
    --expected-host-suffix) EXPECTED_HOST_SUFFIX="${2:?}"; shift 2 ;;
    --confirm-rds-removal) CONFIRMED=true; shift ;;
    --skip-terraform-apply) SKIP_TERRAFORM_APPLY=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$ENVIRONMENT" == "dev" || "$ENVIRONMENT" == "prod" ]] || { usage >&2; exit 2; }
[[ "$CONFIRMED" == "true" ]] || fail "--confirm-rds-removal is required"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAME_PREFIX="${NAME_PREFIX:-edgartools-${ENVIRONMENT}}"
MANIFEST="${MANIFEST:-${REPO_ROOT}/infra/aws-${ENVIRONMENT}-application.json}"
TF_ROOT="${TF_ROOT:-${REPO_ROOT}/infra/terraform/accounts/${ENVIRONMENT}}"
AUDIT_SCRIPT="${REPO_ROOT}/infra/scripts/audit-mdm-snowflake-postgres-cutover.py"
RDS_INSTANCE_ID="${NAME_PREFIX}-mdm"

aws_cli() {
  local args=()
  [[ -n "$AWS_PROFILE_NAME" ]] && args+=(--profile "$AWS_PROFILE_NAME")
  aws "${args[@]}" --region "$AWS_REGION_NAME" "$@"
}

audit_args=(
  --env "$ENVIRONMENT"
  --aws-region "$AWS_REGION_NAME"
  --name-prefix "$NAME_PREFIX"
  --manifest "$MANIFEST"
  --expected-host-suffix "$EXPECTED_HOST_SUFFIX"
  --run-runtime-smoke
)
[[ -n "$AWS_PROFILE_NAME" ]] && audit_args+=(--aws-profile "$AWS_PROFILE_NAME")
[[ -n "$EXPECTED_HOST" ]] && audit_args+=(--expected-host "$EXPECTED_HOST")

log "Running strict Snowflake Postgres cutover audit"
python3 "$AUDIT_SCRIPT" "${audit_args[@]}"

describe_instance() {
  aws_cli rds describe-db-instances \
    --db-instance-identifier "$RDS_INSTANCE_ID" \
    --query 'DBInstances[0]' \
    --output json 2>/dev/null || true
}

INSTANCE_JSON="$(describe_instance)"
if [[ -z "$INSTANCE_JSON" || "$INSTANCE_JSON" == "null" ]]; then
  log "RDS instance ${RDS_INSTANCE_ID} is already absent"
else
  DELETION_PROTECTION="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("DeletionProtection", False))' <<< "$INSTANCE_JSON")"
  STATUS="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("DBInstanceStatus", ""))' <<< "$INSTANCE_JSON")"
  log "Legacy RDS instance found: ${RDS_INSTANCE_ID} (status=${STATUS}, deletion_protection=${DELETION_PROTECTION})"

  if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY RUN - would disable deletion protection if needed"
    log "DRY RUN - would delete ${RDS_INSTANCE_ID} with --skip-final-snapshot --delete-automated-backups"
  else
    if [[ "$DELETION_PROTECTION" == "True" || "$DELETION_PROTECTION" == "true" ]]; then
      log "Disabling deletion protection on ${RDS_INSTANCE_ID}"
      aws_cli rds modify-db-instance \
        --db-instance-identifier "$RDS_INSTANCE_ID" \
        --no-deletion-protection \
        --apply-immediately >/dev/null
      aws_cli rds wait db-instance-available --db-instance-identifier "$RDS_INSTANCE_ID"
    fi

    log "Deleting ${RDS_INSTANCE_ID} with no final snapshot"
    aws_cli rds delete-db-instance \
      --db-instance-identifier "$RDS_INSTANCE_ID" \
      --skip-final-snapshot \
      --delete-automated-backups >/dev/null
    aws_cli rds wait db-instance-deleted --db-instance-identifier "$RDS_INSTANCE_ID"
  fi
fi

if [[ "$SKIP_TERRAFORM_APPLY" == "true" ]]; then
  log "Skipping Terraform apply by request. Apply ${TF_ROOT} later to reconcile removed RDS resources."
  exit 0
fi

if [[ "$DRY_RUN" == "true" ]]; then
  log "DRY RUN - would run terraform -chdir=${TF_ROOT} apply"
  exit 0
fi

command -v terraform >/dev/null 2>&1 || fail "terraform is required unless --skip-terraform-apply is used"
log "Applying Terraform removal in ${TF_ROOT}"
terraform -chdir="$TF_ROOT" apply
