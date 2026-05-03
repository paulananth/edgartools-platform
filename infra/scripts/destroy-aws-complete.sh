#!/usr/bin/env bash
set -euo pipefail

if uname -s | grep -qi "mingw\|msys\|cygwin"; then
  export MSYS_NO_PATHCONV=1
fi

usage() {
  cat <<'USAGE'
Usage:
  destroy-aws-complete.sh --env <dev|prod|all> [options]

Permanently destroys all EdgarTools AWS resources for the selected environment:
operator-managed AWS app resources, Terraform-managed AWS infrastructure, data
buckets, ECR images, secrets, RDS resources, and the Terraform state bucket.

Azure resources and Snowflake account/database objects are intentionally out of
scope. Snowflake Terraform state stored in the AWS state bucket is backed up
locally before the bucket is deleted.

Options:
  --env <dev|prod|all>       Environment to destroy. Required.
  --aws-profile <profile>    AWS CLI profile.
  --aws-region <region>      AWS region. Default: AWS_REGION, AWS_DEFAULT_REGION, or us-east-1.
  --backup-root <path>       Local state backup root. Default: infra/.aws-tfstate-backups.
  --dry-run                  Discover resources and print destructive commands without running them.
  --yes                      Skip the interactive confirmation prompt.
  -h, --help                 Show this help.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

warn() {
  echo "WARN: $*" >&2
}

log() {
  echo "==> $*" >&2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

is_empty() {
  [[ -z "${1:-}" || "${1:-}" == "None" || "${1:-}" == "null" ]]
}

render_cmd() {
  local rendered="" quoted arg
  for arg in "$@"; do
    printf -v quoted "%q" "$arg"
    rendered+="${quoted} "
  done
  printf '%s\n' "${rendered% }"
}

ENVIRONMENT=""
AWS_PROFILE_NAME=""
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
BACKUP_ROOT=""
DRY_RUN=false
ASSUME_YES=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --backup-root) BACKUP_ROOT="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --yes) ASSUME_YES=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$ENVIRONMENT" in
  dev|prod|all) ;;
  *) usage >&2; exit 2 ;;
esac

require_command aws
require_command terraform
require_command python3
require_command awk

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_ROOT="${BACKUP_ROOT:-${REPO_ROOT}/infra/.aws-tfstate-backups}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/edgartools-aws-destroy-XXXXXX")"

RESTORE_FILES=()
RESTORE_BACKUPS=()

restore_temporary_files() {
  local i src dst
  for ((i = ${#RESTORE_FILES[@]} - 1; i >= 0; i--)); do
    src="${RESTORE_BACKUPS[$i]}"
    dst="${RESTORE_FILES[$i]}"
    if [[ -f "$src" ]]; then
      cp "$src" "$dst"
      log "Restored ${dst#${REPO_ROOT}/}"
    fi
  done
}

cleanup() {
  local status=$?
  restore_temporary_files
  rm -rf "$TMP_DIR"
  exit "$status"
}
trap cleanup EXIT

aws_cli() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" "$@"
  else
    aws --region "$AWS_REGION_NAME" "$@"
  fi
}

render_aws_cmd() {
  local args=(aws)
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    args+=(--profile "$AWS_PROFILE_NAME")
  fi
  args+=(--region "$AWS_REGION_NAME" "$@")
  render_cmd "${args[@]}"
}

run_cmd() {
  if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY-RUN: $(render_cmd "$@")"
  else
    "$@"
  fi
}

run_cmd_quiet() {
  if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY-RUN: $(render_cmd "$@")"
  else
    "$@" >/dev/null
  fi
}

run_aws_quiet() {
  if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY-RUN: $(render_aws_cmd "$@")"
  else
    aws_cli "$@" >/dev/null
  fi
}

normalize_lines() {
  tr '\t' '\n' | awk 'NF && $0 != "None" && $0 != "null" && !seen[$0]++'
}

name_prefix() {
  printf 'edgartools-%s\n' "$1"
}

tf_root() {
  printf '%s/infra/terraform/accounts/%s\n' "$REPO_ROOT" "$1"
}

tf_output_raw() {
  local env="$1" output="$2" root
  root="$(tf_root "$env")"
  terraform -chdir="$root" output -raw "$output" 2>/dev/null || true
}

backend_bucket() {
  local env="$1" root backend bucket
  root="$(tf_root "$env")"
  backend="${root}/backend.hcl"
  if [[ -f "$backend" ]]; then
    bucket="$(
      awk -F= '
        $1 ~ /^[[:space:]]*bucket[[:space:]]*$/ {
          value=$2
          gsub(/[[:space:]"]/, "", value)
          print value
          exit
        }
      ' "$backend"
    )"
    if ! is_empty "$bucket"; then
      printf '%s\n' "$bucket"
      return 0
    fi
  fi
  printf 'edgartools-%s-tfstate\n' "$env"
}

discover_s3_buckets() {
  local env="$1" prefix names
  prefix="$(name_prefix "$env")"
  names="$(aws_cli s3api list-buckets --query "Buckets[?starts_with(Name, '${prefix}')].Name" --output text 2>/dev/null || true)"
  {
    printf '%s\n' "$(tf_output_raw "$env" bronze_bucket_name)"
    printf '%s\n' "$(tf_output_raw "$env" warehouse_bucket_name)"
    printf '%s\n' "$(tf_output_raw "$env" snowflake_export_bucket_name)"
    printf '%s\n' "$names" | normalize_lines
  } | normalize_lines
}

discover_data_buckets() {
  local env="$1" bucket state_bucket
  state_bucket="$(backend_bucket "$env")"
  while IFS= read -r bucket; do
    if [[ "$bucket" == "$state_bucket" || "$bucket" == "edgartools-${env}-tfstate" ]]; then
      continue
    fi
    printf '%s\n' "$bucket"
  done < <(discover_s3_buckets "$env")
}

discover_ecr_repositories() {
  local env="$1" prefix url names
  prefix="$(name_prefix "$env")"
  url="$(tf_output_raw "$env" ecr_repository_url)"
  names="$(aws_cli ecr describe-repositories --query "repositories[?starts_with(repositoryName, '${prefix}')].repositoryName" --output text 2>/dev/null || true)"
  {
    if ! is_empty "$url"; then
      printf '%s\n' "${url##*/}"
    fi
    printf '%s\n' "$names" | normalize_lines
  } | normalize_lines
}

discover_state_machines() {
  local env="$1" prefix names
  prefix="$(name_prefix "$env")"
  names="$(aws_cli stepfunctions list-state-machines --query "stateMachines[?starts_with(name, '${prefix}-')].stateMachineArn" --output text 2>/dev/null || true)"
  printf '%s\n' "$names" | normalize_lines
}

discover_step_log_groups() {
  local env="$1" prefix names
  prefix="$(name_prefix "$env")"
  names="$(aws_cli logs describe-log-groups --log-group-name-prefix "/aws/states/${prefix}" --query 'logGroups[].logGroupName' --output text 2>/dev/null || true)"
  printf '%s\n' "$names" | normalize_lines
}

discover_task_definitions() {
  local env="$1" status="$2" prefix names
  prefix="$(name_prefix "$env")"
  names="$(aws_cli ecs list-task-definitions --family-prefix "${prefix}-" --status "$status" --sort ASC --query 'taskDefinitionArns[]' --output text 2>/dev/null || true)"
  printf '%s\n' "$names" | normalize_lines
}

discover_ecs_clusters() {
  local env="$1" prefix output_name output_arn
  prefix="$(name_prefix "$env")"
  output_name="$(tf_output_raw "$env" cluster_name)"
  output_arn="$(tf_output_raw "$env" cluster_arn)"
  {
    printf '%s\n' "$output_name"
    printf '%s\n' "$output_arn"
    printf '%s\n' "${prefix}-warehouse"
  } | normalize_lines
}

discover_rds_instances() {
  local env="$1" prefix names
  prefix="$(name_prefix "$env")"
  names="$(aws_cli rds describe-db-instances --query "DBInstances[?starts_with(DBInstanceIdentifier, '${prefix}')].DBInstanceIdentifier" --output text 2>/dev/null || true)"
  printf '%s\n' "$names" | normalize_lines
}

discover_rds_clusters() {
  local env="$1" prefix names
  prefix="$(name_prefix "$env")"
  names="$(aws_cli rds describe-db-clusters --query "DBClusters[?starts_with(DBClusterIdentifier, '${prefix}')].DBClusterIdentifier" --output text 2>/dev/null || true)"
  printf '%s\n' "$names" | normalize_lines
}

discover_secrets() {
  local env="$1" prefix names
  prefix="$(name_prefix "$env")"
  names="$(aws_cli secretsmanager list-secrets --include-planned-deletion --query "SecretList[?starts_with(Name, '${prefix}')].Name" --output text 2>/dev/null || true)"
  printf '%s\n' "$names" | normalize_lines
}

print_lines() {
  local label="$1" values="$2"
  if is_empty "$values"; then
    log "${label}: none discovered"
  else
    log "${label}:"
    printf '%s\n' "$values" | sed 's/^/  - /' >&2
  fi
}

summarize_environment() {
  local env="$1" state_bucket
  state_bucket="$(backend_bucket "$env")"
  log "Discovery for ${env} ($(name_prefix "$env"))"
  print_lines "S3 data buckets" "$(discover_data_buckets "$env")"
  print_lines "ECR repositories" "$(discover_ecr_repositories "$env")"
  print_lines "Step Functions state machines" "$(discover_state_machines "$env")"
  print_lines "Step Functions log groups" "$(discover_step_log_groups "$env")"
  print_lines "Active ECS task definitions" "$(discover_task_definitions "$env" ACTIVE)"
  print_lines "Inactive ECS task definitions" "$(discover_task_definitions "$env" INACTIVE)"
  print_lines "RDS DB instances" "$(discover_rds_instances "$env")"
  print_lines "RDS DB clusters" "$(discover_rds_clusters "$env")"
  print_lines "Secrets Manager secrets" "$(discover_secrets "$env")"
  log "Terraform state bucket: ${state_bucket}"
}

confirm_destroy() {
  local expected answer
  if [[ "$DRY_RUN" == "true" || "$ASSUME_YES" == "true" ]]; then
    return 0
  fi

  cat >&2 <<EOF

This will permanently delete EdgarTools AWS resources for: ${ENVIRONMENT}

Deleted data includes S3 bucket contents and versions, ECR images, Secrets
Manager values, RDS databases without final snapshots, and AWS Terraform state
buckets after local backup.

EOF
  expected="destroy edgartools ${ENVIRONMENT}"
  read -r -p "Type '${expected}' to continue: " answer
  [[ "$answer" == "$expected" ]] || fail "confirmation did not match; refusing to destroy resources"
}

backup_file_for_restore() {
  local file="$1" i backup
  for ((i = 0; i < ${#RESTORE_FILES[@]}; i++)); do
    if [[ "${RESTORE_FILES[$i]}" == "$file" ]]; then
      return 0
    fi
  done
  backup="${TMP_DIR}/restore-${#RESTORE_FILES[@]}"
  cp "$file" "$backup"
  RESTORE_FILES+=("$file")
  RESTORE_BACKUPS+=("$backup")
}

patch_file_with_python() {
  local file="$1" mode="$2"
  backup_file_for_restore "$file"
  python3 - "$file" "$mode" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
mode = sys.argv[2]
text = path.read_text(encoding="utf-8")
original = text

if mode == "prod-storage-prevent-destroy":
    text = re.sub(
        r"^(\s*)prevent_destroy\s*=\s*true\s*$",
        r"\1# prevent_destroy = true # __destroy_aws_complete__",
        text,
        count=1,
        flags=re.MULTILINE,
    )
elif mode == "prod-runtime-force":
    text = re.sub(
        r"^(\s*ecr_force_delete\s*=\s*)false\s*$",
        r"\1true",
        text,
        count=1,
        flags=re.MULTILINE,
    )
elif mode == "mdm-destructive-delete":
    text = re.sub(
        r"^(\s*skip_final_snapshot\s*=\s*)false\s*$",
        r"\1true",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^(\s*deletion_protection\s*=\s*)true\s*$",
        r"\1false",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^(\s*apply_immediately\s*=\s*)false\s*$",
        r"\1true",
        text,
        count=1,
        flags=re.MULTILINE,
    )
else:
    raise SystemExit(f"unknown patch mode: {mode}")

if text != original:
    path.write_text(text, encoding="utf-8")
PY
}

apply_destroy_overrides() {
  local env="$1"
  if [[ "$DRY_RUN" == "true" ]]; then
    if [[ "$env" == "prod" ]]; then
      log "DRY-RUN: would temporarily disable prod bronze bucket prevent_destroy and force-delete runtime blockers"
    fi
    log "DRY-RUN: would temporarily configure MDM RDS destruction to skip final snapshots and disable deletion protection"
    return 0
  fi

  if [[ "$env" == "prod" ]]; then
    patch_file_with_python "${REPO_ROOT}/infra/terraform/modules/storage_buckets/main.tf" prod-storage-prevent-destroy
    patch_file_with_python "${REPO_ROOT}/infra/terraform/accounts/prod/main.tf" prod-runtime-force
    log "Temporarily relaxed prod Terraform destroy guards"
  fi

  patch_file_with_python "${REPO_ROOT}/infra/terraform/modules/mdm_database/main.tf" mdm-destructive-delete
  log "Temporarily configured MDM RDS resources for destructive deletion"
}

bucket_exists() {
  local bucket="$1"
  aws_cli s3api head-bucket --bucket "$bucket" >/dev/null 2>&1
}

empty_bucket() {
  local bucket="$1" list_file payload_file count
  if ! bucket_exists "$bucket"; then
    log "S3 bucket does not exist, skipping empty: ${bucket}"
    return 0
  fi

  log "Emptying S3 bucket versions and delete markers: ${bucket}"
  if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY-RUN: would delete all current objects, object versions, and delete markers from s3://${bucket}"
    return 0
  fi

  while true; do
    list_file="$(mktemp "${TMP_DIR}/s3-versions-XXXXXX.json")"
    payload_file="$(mktemp "${TMP_DIR}/s3-delete-XXXXXX.json")"
    aws_cli s3api list-object-versions --bucket "$bucket" --max-items 1000 --output json > "$list_file"
    count="$(
      python3 - "$list_file" "$payload_file" <<'PY'
import json
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
target = pathlib.Path(sys.argv[2])
data = json.loads(source.read_text(encoding="utf-8"))
objects = []
for group in ("Versions", "DeleteMarkers"):
    for item in data.get(group) or []:
        key = item.get("Key")
        version_id = item.get("VersionId")
        if key is not None and version_id is not None:
            objects.append({"Key": key, "VersionId": version_id})
target.write_text(json.dumps({"Objects": objects, "Quiet": True}), encoding="utf-8")
print(len(objects))
PY
    )"
    if [[ "$count" == "0" ]]; then
      break
    fi
    aws_cli s3api delete-objects --bucket "$bucket" --delete "file://${payload_file}" >/dev/null
  done

  aws_cli s3 rm "s3://${bucket}" --recursive >/dev/null 2>&1 || true
}

delete_bucket() {
  local bucket="$1"
  if ! bucket_exists "$bucket"; then
    log "S3 bucket already absent: ${bucket}"
    return 0
  fi
  empty_bucket "$bucket"
  log "Deleting S3 bucket: ${bucket}"
  run_aws_quiet s3api delete-bucket --bucket "$bucket"
}

delete_ecr_images() {
  local repo="$1" details_file payload_file count
  if ! aws_cli ecr describe-repositories --repository-names "$repo" >/dev/null 2>&1; then
    log "ECR repository does not exist, skipping images: ${repo}"
    return 0
  fi

  log "Deleting ECR images from repository: ${repo}"
  if [[ "$DRY_RUN" == "true" ]]; then
    count="$(aws_cli ecr describe-images --repository-name "$repo" --query 'length(imageDetails[])' --output text 2>/dev/null || printf '0')"
    log "DRY-RUN: would delete ${count} image detail(s) from ECR repository ${repo}"
    return 0
  fi

  while true; do
    details_file="$(mktemp "${TMP_DIR}/ecr-images-XXXXXX.json")"
    payload_file="$(mktemp "${TMP_DIR}/ecr-delete-XXXXXX.json")"
    aws_cli ecr describe-images --repository-name "$repo" --max-items 100 --output json > "$details_file"
    count="$(
      python3 - "$details_file" "$payload_file" <<'PY'
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
seen = set()
image_ids = []
for detail in data.get("imageDetails") or []:
    digest = detail.get("imageDigest")
    if digest and digest not in seen:
        seen.add(digest)
        image_ids.append({"imageDigest": digest})
pathlib.Path(sys.argv[2]).write_text(json.dumps(image_ids), encoding="utf-8")
print(len(image_ids))
PY
    )"
    if [[ "$count" == "0" ]]; then
      break
    fi
    aws_cli ecr batch-delete-image --repository-name "$repo" --image-ids "file://${payload_file}" >/dev/null
  done
}

delete_ecr_repository() {
  local repo="$1"
  if ! aws_cli ecr describe-repositories --repository-names "$repo" >/dev/null 2>&1; then
    log "ECR repository already absent: ${repo}"
    return 0
  fi
  delete_ecr_images "$repo"
  log "Deleting ECR repository: ${repo}"
  run_aws_quiet ecr delete-repository --repository-name "$repo" --force
}

stop_ecs_tasks() {
  local env="$1" cluster tasks task
  while IFS= read -r cluster; do
    if is_empty "$cluster"; then
      continue
    fi
    if ! aws_cli ecs describe-clusters --clusters "$cluster" --query 'clusters[0].status' --output text >/dev/null 2>&1; then
      continue
    fi
    tasks="$(aws_cli ecs list-tasks --cluster "$cluster" --desired-status RUNNING --query 'taskArns[]' --output text 2>/dev/null || true)"
    tasks="$(printf '%s\n' "$tasks" | normalize_lines)"
    if is_empty "$tasks"; then
      continue
    fi
    log "Stopping ECS tasks in cluster ${cluster}"
    while IFS= read -r task; do
      run_aws_quiet ecs stop-task --cluster "$cluster" --task "$task" --reason "edgartools complete AWS teardown"
    done <<< "$tasks"
    if [[ "$DRY_RUN" != "true" ]]; then
      aws_cli ecs wait tasks-stopped --cluster "$cluster" --tasks $tasks
    fi
  done < <(discover_ecs_clusters "$env")
}

delete_task_definitions() {
  local env="$1" active inactive arn batch
  active="$(discover_task_definitions "$env" ACTIVE)"
  if ! is_empty "$active"; then
    log "Deregistering active ECS task definitions"
    while IFS= read -r arn; do
      run_aws_quiet ecs deregister-task-definition --task-definition "$arn"
    done <<< "$active"
  fi

  inactive="$(
    {
      printf '%s\n' "$active"
      discover_task_definitions "$env" INACTIVE
    } | normalize_lines
  )"
  if is_empty "$inactive"; then
    return 0
  fi

  log "Deleting inactive ECS task definitions"
  batch=()
  while IFS= read -r arn; do
    batch+=("$arn")
    if (( ${#batch[@]} == 10 )); then
      run_aws_quiet ecs delete-task-definitions --task-definitions "${batch[@]}"
      batch=()
    fi
  done <<< "$inactive"
  if (( ${#batch[@]} > 0 )); then
    run_aws_quiet ecs delete-task-definitions --task-definitions "${batch[@]}"
  fi
}

stop_step_function_executions() {
  local state_machine_arn="$1" executions execution attempt
  executions="$(aws_cli stepfunctions list-executions --state-machine-arn "$state_machine_arn" --status-filter RUNNING --query 'executions[].executionArn' --output text 2>/dev/null || true)"
  executions="$(printf '%s\n' "$executions" | normalize_lines)"
  if is_empty "$executions"; then
    return 0
  fi

  log "Stopping running Step Functions executions for ${state_machine_arn}"
  while IFS= read -r execution; do
    run_aws_quiet stepfunctions stop-execution --execution-arn "$execution" --cause "edgartools complete AWS teardown"
  done <<< "$executions"

  if [[ "$DRY_RUN" == "true" ]]; then
    return 0
  fi

  for attempt in $(seq 1 30); do
    executions="$(aws_cli stepfunctions list-executions --state-machine-arn "$state_machine_arn" --status-filter RUNNING --query 'executions[].executionArn' --output text 2>/dev/null || true)"
    executions="$(printf '%s\n' "$executions" | normalize_lines)"
    if is_empty "$executions"; then
      return 0
    fi
    sleep 5
  done
  fail "Step Functions executions did not stop for ${state_machine_arn}"
}

delete_state_machines() {
  local env="$1" arn
  while IFS= read -r arn; do
    if is_empty "$arn"; then
      continue
    fi
    stop_step_function_executions "$arn"
    log "Deleting Step Functions state machine: ${arn}"
    run_aws_quiet stepfunctions delete-state-machine --state-machine-arn "$arn"
  done < <(discover_state_machines "$env")
}

delete_log_groups() {
  local env="$1" name
  while IFS= read -r name; do
    if is_empty "$name"; then
      continue
    fi
    log "Deleting CloudWatch log group: ${name}"
    run_aws_quiet logs delete-log-group --log-group-name "$name"
  done < <(discover_step_log_groups "$env")
}

delete_iam_role() {
  local role="$1" policies policy attachments attachment profiles profile
  if ! aws_cli iam get-role --role-name "$role" >/dev/null 2>&1; then
    return 0
  fi

  log "Deleting IAM role and attachments: ${role}"
  policies="$(aws_cli iam list-role-policies --role-name "$role" --query 'PolicyNames[]' --output text 2>/dev/null || true)"
  policies="$(printf '%s\n' "$policies" | normalize_lines)"
  while IFS= read -r policy; do
    [[ -n "$policy" ]] && run_aws_quiet iam delete-role-policy --role-name "$role" --policy-name "$policy"
  done <<< "$policies"

  attachments="$(aws_cli iam list-attached-role-policies --role-name "$role" --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null || true)"
  attachments="$(printf '%s\n' "$attachments" | normalize_lines)"
  while IFS= read -r attachment; do
    [[ -n "$attachment" ]] && run_aws_quiet iam detach-role-policy --role-name "$role" --policy-arn "$attachment"
  done <<< "$attachments"

  profiles="$(aws_cli iam list-instance-profiles-for-role --role-name "$role" --query 'InstanceProfiles[].InstanceProfileName' --output text 2>/dev/null || true)"
  profiles="$(printf '%s\n' "$profiles" | normalize_lines)"
  while IFS= read -r profile; do
    [[ -n "$profile" ]] && run_aws_quiet iam remove-role-from-instance-profile --instance-profile-name "$profile" --role-name "$role"
  done <<< "$profiles"

  run_aws_quiet iam delete-role --role-name "$role"
}

delete_iam_user() {
  local user="$1" values value
  if ! aws_cli iam get-user --user-name "$user" >/dev/null 2>&1; then
    return 0
  fi

  log "Deleting IAM user and credentials: ${user}"
  run_aws_quiet iam delete-login-profile --user-name "$user" || true

  values="$(aws_cli iam list-access-keys --user-name "$user" --query 'AccessKeyMetadata[].AccessKeyId' --output text 2>/dev/null || true)"
  values="$(printf '%s\n' "$values" | normalize_lines)"
  while IFS= read -r value; do
    [[ -n "$value" ]] && run_aws_quiet iam delete-access-key --user-name "$user" --access-key-id "$value"
  done <<< "$values"

  values="$(aws_cli iam list-user-policies --user-name "$user" --query 'PolicyNames[]' --output text 2>/dev/null || true)"
  values="$(printf '%s\n' "$values" | normalize_lines)"
  while IFS= read -r value; do
    [[ -n "$value" ]] && run_aws_quiet iam delete-user-policy --user-name "$user" --policy-name "$value"
  done <<< "$values"

  values="$(aws_cli iam list-attached-user-policies --user-name "$user" --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null || true)"
  values="$(printf '%s\n' "$values" | normalize_lines)"
  while IFS= read -r value; do
    [[ -n "$value" ]] && run_aws_quiet iam detach-user-policy --user-name "$user" --policy-arn "$value"
  done <<< "$values"

  values="$(aws_cli iam list-groups-for-user --user-name "$user" --query 'Groups[].GroupName' --output text 2>/dev/null || true)"
  values="$(printf '%s\n' "$values" | normalize_lines)"
  while IFS= read -r value; do
    [[ -n "$value" ]] && run_aws_quiet iam remove-user-from-group --user-name "$user" --group-name "$value"
  done <<< "$values"

  values="$(aws_cli iam list-ssh-public-keys --user-name "$user" --query 'SSHPublicKeys[].SSHPublicKeyId' --output text 2>/dev/null || true)"
  values="$(printf '%s\n' "$values" | normalize_lines)"
  while IFS= read -r value; do
    [[ -n "$value" ]] && run_aws_quiet iam delete-ssh-public-key --user-name "$user" --ssh-public-key-id "$value"
  done <<< "$values"

  values="$(aws_cli iam list-signing-certificates --user-name "$user" --query 'Certificates[].CertificateId' --output text 2>/dev/null || true)"
  values="$(printf '%s\n' "$values" | normalize_lines)"
  while IFS= read -r value; do
    [[ -n "$value" ]] && run_aws_quiet iam delete-signing-certificate --user-name "$user" --certificate-id "$value"
  done <<< "$values"

  values="$(aws_cli iam list-service-specific-credentials --user-name "$user" --query 'ServiceSpecificCredentials[].ServiceSpecificCredentialId' --output text 2>/dev/null || true)"
  values="$(printf '%s\n' "$values" | normalize_lines)"
  while IFS= read -r value; do
    [[ -n "$value" ]] && run_aws_quiet iam delete-service-specific-credential --user-name "$user" --service-specific-credential-id "$value"
  done <<< "$values"

  values="$(aws_cli iam list-mfa-devices --user-name "$user" --query 'MFADevices[].SerialNumber' --output text 2>/dev/null || true)"
  values="$(printf '%s\n' "$values" | normalize_lines)"
  while IFS= read -r value; do
    if [[ -n "$value" ]]; then
      run_aws_quiet iam deactivate-mfa-device --user-name "$user" --serial-number "$value"
      run_aws_quiet iam delete-virtual-mfa-device --serial-number "$value" || true
    fi
  done <<< "$values"

  run_aws_quiet iam delete-user --user-name "$user"
}

delete_step_functions_role() {
  local env="$1" prefix
  prefix="$(name_prefix "$env")"
  delete_iam_role "${prefix}-step-functions"
}

force_delete_secrets() {
  local env="$1" secret
  while IFS= read -r secret; do
    if is_empty "$secret"; then
      continue
    fi
    log "Force deleting Secrets Manager secret: ${secret}"
    if [[ "$DRY_RUN" == "true" ]]; then
      log "DRY-RUN: $(render_aws_cmd secretsmanager delete-secret --secret-id "$secret" --force-delete-without-recovery)"
      continue
    fi
    if ! aws_cli secretsmanager delete-secret --secret-id "$secret" --force-delete-without-recovery >/dev/null 2>&1; then
      aws_cli secretsmanager restore-secret --secret-id "$secret" >/dev/null 2>&1 || true
      aws_cli secretsmanager delete-secret --secret-id "$secret" --force-delete-without-recovery >/dev/null
    fi
  done < <(discover_secrets "$env")
}

delete_rds_instances() {
  local env="$1" db protection status
  while IFS= read -r db; do
    if is_empty "$db"; then
      continue
    fi
    status="$(aws_cli rds describe-db-instances --db-instance-identifier "$db" --query 'DBInstances[0].DBInstanceStatus' --output text 2>/dev/null || true)"
    if [[ "$status" == "deleting" ]]; then
      continue
    fi
    log "Deleting RDS DB instance without final snapshot: ${db}"
    if [[ "$DRY_RUN" == "true" ]]; then
      log "DRY-RUN: would disable deletion protection, delete automated backups, and skip final snapshot for ${db}"
      continue
    fi
    protection="$(aws_cli rds describe-db-instances --db-instance-identifier "$db" --query 'DBInstances[0].DeletionProtection' --output text)"
    if [[ "$protection" == "True" ]]; then
      aws_cli rds modify-db-instance --db-instance-identifier "$db" --no-deletion-protection --apply-immediately >/dev/null
      aws_cli rds wait db-instance-available --db-instance-identifier "$db"
    fi
    aws_cli rds delete-db-instance --db-instance-identifier "$db" --skip-final-snapshot --delete-automated-backups >/dev/null
    aws_cli rds wait db-instance-deleted --db-instance-identifier "$db"
  done < <(discover_rds_instances "$env")
}

delete_rds_clusters() {
  local env="$1" cluster protection status
  while IFS= read -r cluster; do
    if is_empty "$cluster"; then
      continue
    fi
    status="$(aws_cli rds describe-db-clusters --db-cluster-identifier "$cluster" --query 'DBClusters[0].Status' --output text 2>/dev/null || true)"
    if [[ "$status" == "deleting" ]]; then
      continue
    fi
    log "Deleting RDS DB cluster without final snapshot: ${cluster}"
    if [[ "$DRY_RUN" == "true" ]]; then
      log "DRY-RUN: would disable deletion protection and skip final snapshot for ${cluster}"
      continue
    fi
    protection="$(aws_cli rds describe-db-clusters --db-cluster-identifier "$cluster" --query 'DBClusters[0].DeletionProtection' --output text)"
    if [[ "$protection" == "True" ]]; then
      aws_cli rds modify-db-cluster --db-cluster-identifier "$cluster" --no-deletion-protection --apply-immediately >/dev/null
    fi
    aws_cli rds delete-db-cluster --db-cluster-identifier "$cluster" --skip-final-snapshot >/dev/null
    aws_cli rds wait db-cluster-deleted --db-cluster-identifier "$cluster"
  done < <(discover_rds_clusters "$env")
}

delete_prefixed_iam_resources() {
  local env="$1" prefix names name policies policy
  prefix="$(name_prefix "$env")"

  names="$(aws_cli iam list-users --query "Users[?starts_with(UserName, '${prefix}')].UserName" --output text 2>/dev/null || true)"
  names="$(printf '%s\n' "$names" | normalize_lines)"
  while IFS= read -r name; do
    [[ -n "$name" ]] && delete_iam_user "$name"
  done <<< "$names"

  names="$(aws_cli iam list-roles --query "Roles[?starts_with(RoleName, '${prefix}')].RoleName" --output text 2>/dev/null || true)"
  names="$(printf '%s\n' "$names" | normalize_lines)"
  while IFS= read -r name; do
    [[ -n "$name" ]] && delete_iam_role "$name"
  done <<< "$names"

  policies="$(aws_cli iam list-policies --scope Local --query "Policies[?starts_with(PolicyName, '${prefix}')].Arn" --output text 2>/dev/null || true)"
  policies="$(printf '%s\n' "$policies" | normalize_lines)"
  while IFS= read -r policy; do
    if [[ -n "$policy" ]]; then
      log "Deleting IAM managed policy: ${policy}"
      delete_managed_policy "$policy"
    fi
  done <<< "$policies"
}

delete_managed_policy() {
  local policy_arn="$1" values value
  values="$(aws_cli iam list-entities-for-policy --policy-arn "$policy_arn" --query 'PolicyRoles[].RoleName' --output text 2>/dev/null || true)"
  values="$(printf '%s\n' "$values" | normalize_lines)"
  while IFS= read -r value; do
    [[ -n "$value" ]] && run_aws_quiet iam detach-role-policy --role-name "$value" --policy-arn "$policy_arn"
  done <<< "$values"

  values="$(aws_cli iam list-entities-for-policy --policy-arn "$policy_arn" --query 'PolicyUsers[].UserName' --output text 2>/dev/null || true)"
  values="$(printf '%s\n' "$values" | normalize_lines)"
  while IFS= read -r value; do
    [[ -n "$value" ]] && run_aws_quiet iam detach-user-policy --user-name "$value" --policy-arn "$policy_arn"
  done <<< "$values"

  values="$(aws_cli iam list-entities-for-policy --policy-arn "$policy_arn" --query 'PolicyGroups[].GroupName' --output text 2>/dev/null || true)"
  values="$(printf '%s\n' "$values" | normalize_lines)"
  while IFS= read -r value; do
    [[ -n "$value" ]] && run_aws_quiet iam detach-group-policy --group-name "$value" --policy-arn "$policy_arn"
  done <<< "$values"

  values="$(aws_cli iam list-policy-versions --policy-arn "$policy_arn" --query 'Versions[?!IsDefaultVersion].VersionId' --output text 2>/dev/null || true)"
  values="$(printf '%s\n' "$values" | normalize_lines)"
  while IFS= read -r value; do
    [[ -n "$value" ]] && run_aws_quiet iam delete-policy-version --policy-arn "$policy_arn" --version-id "$value"
  done <<< "$values"

  run_aws_quiet iam delete-policy --policy-arn "$policy_arn"
}

delete_operator_app_layer() {
  local env="$1"
  stop_ecs_tasks "$env"
  delete_state_machines "$env"
  delete_log_groups "$env"
  delete_step_functions_role "$env"
  delete_task_definitions "$env"
}

terraform_init_args() {
  local env="$1" root backend state_bucket
  root="$(tf_root "$env")"
  backend="${root}/backend.hcl"
  if [[ -f "$backend" ]]; then
    printf '%s\0' -backend-config="$backend"
  else
    state_bucket="$(backend_bucket "$env")"
    printf '%s\0' \
      -backend-config="bucket=${state_bucket}" \
      -backend-config="key=accounts/${env}/terraform.tfstate" \
      -backend-config="region=${AWS_REGION_NAME}" \
      -backend-config="encrypt=true"
  fi
}

run_terraform_destroy() {
  local env="$1" root init_args arg
  root="$(tf_root "$env")"
  [[ -d "$root" ]] || fail "Terraform root does not exist: ${root}"

  init_args=()
  while IFS= read -r -d '' arg; do
    init_args+=("$arg")
  done < <(terraform_init_args "$env")

  log "Initializing Terraform root: ${root#${REPO_ROOT}/}"
  run_cmd terraform -chdir="$root" init -input=false -reconfigure -no-color "${init_args[@]}"

  log "Destroying Terraform root: ${root#${REPO_ROOT}/}"
  run_cmd terraform -chdir="$root" destroy -auto-approve -input=false -no-color -var "aws_region=${AWS_REGION_NAME}"
}

backup_state_bucket_versions() {
  local bucket="$1" backup_dir="$2" listing="$3" manifest key version_id idx dest rel
  manifest="${backup_dir}/versioned-objects.tsv"
  printf 'index\tkey\tversion_id\tlocal_path\n' > "$manifest"
  python3 - "$listing" <<'PY' | while IFS=$'\t' read -r idx key version_id; do
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
for idx, item in enumerate(data.get("Versions") or [], start=1):
    key = item.get("Key")
    version_id = item.get("VersionId")
    if key and version_id:
        print(f"{idx}\t{key}\t{version_id}")
PY
    rel="versions/${key}.version-${idx}"
    dest="${backup_dir}/${rel}"
    mkdir -p "$(dirname "$dest")"
    aws_cli s3api get-object --bucket "$bucket" --key "$key" --version-id "$version_id" "$dest" >/dev/null
    printf '%s\t%s\t%s\t%s\n' "$idx" "$key" "$version_id" "$rel" >> "$manifest"
  done
}

backup_state_bucket() {
  local env="$1" bucket backup_dir listing
  bucket="$(backend_bucket "$env")"
  if ! bucket_exists "$bucket"; then
    log "Terraform state bucket does not exist, skipping backup: ${bucket}"
    return 0
  fi

  backup_dir="${BACKUP_ROOT}/${RUN_ID}/${env}/${bucket}"
  log "Backing up Terraform state bucket ${bucket} to ${backup_dir#${REPO_ROOT}/}"
  if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY-RUN: would sync current objects from s3://${bucket}/ and copy every object version locally"
    return 0
  fi

  mkdir -p "${backup_dir}/current" "${backup_dir}/versions"
  aws_cli s3 sync "s3://${bucket}/" "${backup_dir}/current/" --only-show-errors
  listing="${backup_dir}/object-versions.json"
  aws_cli s3api list-object-versions --bucket "$bucket" --output json > "$listing"
  backup_state_bucket_versions "$bucket" "$backup_dir" "$listing"
}

pre_destroy_fixes() {
  local env="$1" data_buckets="$2" ecr_repos="$3" bucket repo

  while IFS= read -r bucket; do
    [[ -n "$bucket" ]] && empty_bucket "$bucket"
  done <<< "$data_buckets"

  while IFS= read -r repo; do
    [[ -n "$repo" ]] && delete_ecr_images "$repo"
  done <<< "$ecr_repos"

  force_delete_secrets "$env"
  delete_rds_instances "$env"
  delete_rds_clusters "$env"
  apply_destroy_overrides "$env"
}

cleanup_remaining_resources() {
  local env="$1" data_buckets="$2" ecr_repos="$3" bucket repo combined_buckets combined_repos
  delete_operator_app_layer "$env"
  force_delete_secrets "$env"

  combined_repos="$(
    {
      printf '%s\n' "$ecr_repos"
      discover_ecr_repositories "$env"
    } | normalize_lines
  )"
  while IFS= read -r repo; do
    [[ -n "$repo" ]] && delete_ecr_repository "$repo"
  done <<< "$combined_repos"

  combined_buckets="$(
    {
      printf '%s\n' "$data_buckets"
      discover_data_buckets "$env"
    } | normalize_lines
  )"
  while IFS= read -r bucket; do
    [[ -n "$bucket" ]] && delete_bucket "$bucket"
  done <<< "$combined_buckets"
}

delete_state_bucket() {
  local env="$1" bucket
  bucket="$(backend_bucket "$env")"
  delete_bucket "$bucket"
}

destroy_environment() {
  local env="$1" data_buckets ecr_repos
  log "Starting complete AWS teardown for ${env}"

  data_buckets="$(discover_data_buckets "$env")"
  ecr_repos="$(discover_ecr_repositories "$env")"

  delete_operator_app_layer "$env"
  pre_destroy_fixes "$env" "$data_buckets" "$ecr_repos"
  run_terraform_destroy "$env"
  cleanup_remaining_resources "$env" "$data_buckets" "$ecr_repos"
  backup_state_bucket "$env"
  delete_state_bucket "$env"
  delete_prefixed_iam_resources "$env"
  log "Finished complete AWS teardown for ${env}"
}

if [[ -n "$AWS_PROFILE_NAME" ]]; then
  export AWS_PROFILE="$AWS_PROFILE_NAME"
fi
export AWS_REGION="$AWS_REGION_NAME"
export AWS_DEFAULT_REGION="$AWS_REGION_NAME"

TARGET_ENVS=()
if [[ "$ENVIRONMENT" == "all" ]]; then
  TARGET_ENVS=(dev prod)
else
  TARGET_ENVS=("$ENVIRONMENT")
fi

ACCOUNT_ID="$(aws_cli sts get-caller-identity --query Account --output text)"
log "Using AWS account ${ACCOUNT_ID} in region ${AWS_REGION_NAME}"

for env in "${TARGET_ENVS[@]}"; do
  summarize_environment "$env"
done

confirm_destroy

for env in "${TARGET_ENVS[@]}"; do
  destroy_environment "$env"
done

log "Complete AWS teardown finished. State backups are under ${BACKUP_ROOT}/${RUN_ID}"
