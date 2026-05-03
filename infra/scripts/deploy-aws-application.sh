#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  deploy-aws-application.sh --env <dev|prod> [options]

Deploys active AWS application components outside Terraform:
  - optional warehouse Docker image build and ECR push
  - ECS Fargate task definitions for warehouse task profiles
  - Step Functions log group and state machines

Terraform outputs are used only for passive infrastructure discovery. Pass
--no-terraform-discovery and explicit resource flags to avoid Terraform CLI use.
Use the sec_platform_deployer AWS profile/principal for normal application rollout.

Options:
  --env <dev|prod>                  Environment name. Required.
  --aws-profile <profile>           AWS CLI profile. Normal rollout profile: sec_platform_deployer.
  --aws-region <region>             AWS region. Default: AWS_REGION, AWS_DEFAULT_REGION, or us-east-1.
  --terraform-root <path>           AWS Terraform root. Default: infra/terraform/accounts/<env>.
  --access-terraform-root <path>    AWS access Terraform root. Default: infra/terraform/access/aws/accounts/<env>.
  --no-terraform-discovery          Require explicit flags; do not run terraform output.
  --name-prefix <prefix>            Resource prefix. Default: edgartools-<env>.
  --cluster-name <name>             ECS cluster name.
  --cluster-arn <arn>               ECS cluster ARN.
  --ecr-repository-url <url>        ECR repository URL.
  --public-subnet-ids <ids>         Comma-separated subnet IDs for Fargate awsvpc config.
  --security-group-id <id>          ECS task security group ID.
  --security-group-ids <ids>        Comma-separated ECS task security group IDs.
  --bronze-bucket-name <name>       Bronze bucket name.
  --warehouse-bucket-name <name>    Warehouse bucket name.
  --snowflake-export-bucket-name <name>
                                    Snowflake export bucket name.
  --edgar-identity-secret-arn <arn> EDGAR identity secret ARN.
  --execution-role-arn <arn>        ECS task execution role ARN. Must be sec_platform_runner_execution.
  --task-role-arn <arn>             ECS task role ARN. Must be sec_platform_runner_task.
  --step-functions-role-arn <arn>   Step Functions role ARN. Must be sec_platform_runner_step_functions.
  --log-group-name <name>           ECS task log group name.
  --image-tag <tag>                 Image tag for build/push. Default: git short SHA.
  --image-ref <ref>                 Existing image ref to deploy. Skips build unless --build-image is set.
  --build-image                     Build and push the warehouse image before deployment.
  --skip-build                      Do not build; requires --image-ref.
  --publish-mode <auto|linux|crane> Image publish mode. Default: auto.
  --push-attempts <count>           Image push retry count. Default: 1.
  --platform <platform>             Docker target platform. Default: linux/amd64.
  --context <path>                  Docker build context. Default: repo root.
  --dockerfile <path>               Dockerfile path. Default: repo root Dockerfile.
  --warehouse-runtime-mode <mode>   bronze_capture or infrastructure_validation. Default: bronze_capture.
  --warehouse-bronze-cik-limit <n>  Optional WAREHOUSE_BRONZE_CIK_LIMIT.
  --bootstrap-batch-concurrency <n> Distributed Map bootstrap concurrency. Default: 10.
  --enable-mdm                      Deploy MDM ECS task definitions and state machines; fail if MDM secret ARNs are missing.
  --skip-mdm                        Do not deploy MDM ECS task definitions or state machines.
  --mdm-postgres-dsn-secret-arn <arn>
                                    Secrets Manager ARN injected as MDM_DATABASE_URL.
  --mdm-neo4j-secret-arn <arn>      Secrets Manager ARN injected as NEO4J_SECRET_JSON.
  --mdm-api-keys-secret-arn <arn>   Secrets Manager ARN injected as MDM_API_KEYS.
  --mdm-silver-duckdb <uri>         MDM_SILVER_DUCKDB. Default: s3://<warehouse-bucket>/warehouse/silver/sec/silver.duckdb.
  --mdm-run-limit <n>               Default limit for mdm run state machine. Default: 100; 0 means no default limit.
  --mdm-graph-limit <n>             Default limit for mdm graph backfill/sync. Default: 100; 0 means no default limit.
  --output-file <path>              Write deployment summary JSON.
  -h, --help                        Show this help.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

log() {
  echo "==> $*" >&2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

is_empty() {
  [[ -z "${1:-}" || "${1:-}" == "null" || "${1:-}" == "None" ]]
}

first_nonempty() {
  local value
  for value in "$@"; do
    if ! is_empty "$value"; then
      printf '%s\n' "$value"
      return 0
    fi
  done
  return 0
}

ENVIRONMENT=""
AWS_PROFILE_NAME=""
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
TF_ROOT=""
ACCESS_TF_ROOT=""
USE_TERRAFORM_DISCOVERY=true
NAME_PREFIX=""
CLUSTER_NAME=""
CLUSTER_ARN=""
ECR_REPOSITORY_URL=""
PUBLIC_SUBNET_IDS_CSV=""
PUBLIC_SUBNET_IDS_JSON=""
SECURITY_GROUP_IDS_CSV=""
SECURITY_GROUP_IDS_JSON=""
BRONZE_BUCKET_NAME=""
WAREHOUSE_BUCKET_NAME=""
SNOWFLAKE_EXPORT_BUCKET_NAME=""
EDGAR_IDENTITY_SECRET_ARN=""
EXECUTION_ROLE_ARN=""
TASK_ROLE_ARN=""
STEP_FUNCTIONS_ROLE_ARN=""
LOG_GROUP_NAME=""
IMAGE_TAG=""
IMAGE_REF=""
BUILD_IMAGE=""
PUBLISH_MODE="auto"
PUSH_ATTEMPTS=1
PLATFORM="linux/amd64"
BUILD_CONTEXT=""
DOCKERFILE_PATH=""
WAREHOUSE_RUNTIME_MODE="bronze_capture"
WAREHOUSE_BRONZE_CIK_LIMIT=""
BOOTSTRAP_BATCH_CONCURRENCY=10
MDM_DEPLOYMENT_MODE="auto"
MDM_POSTGRES_DSN_SECRET_ARN=""
MDM_NEO4J_SECRET_ARN=""
MDM_API_KEYS_SECRET_ARN=""
MDM_SILVER_DUCKDB=""
MDM_RUN_LIMIT=100
MDM_GRAPH_LIMIT=100
OUTPUT_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --terraform-root) TF_ROOT="${2:?}"; shift 2 ;;
    --access-terraform-root) ACCESS_TF_ROOT="${2:?}"; shift 2 ;;
    --no-terraform-discovery) USE_TERRAFORM_DISCOVERY=false; shift ;;
    --name-prefix) NAME_PREFIX="${2:?}"; shift 2 ;;
    --cluster-name) CLUSTER_NAME="${2:?}"; shift 2 ;;
    --cluster-arn) CLUSTER_ARN="${2:?}"; shift 2 ;;
    --ecr-repository-url) ECR_REPOSITORY_URL="${2:?}"; shift 2 ;;
    --public-subnet-ids) PUBLIC_SUBNET_IDS_CSV="${2:?}"; shift 2 ;;
    --security-group-id) SECURITY_GROUP_IDS_CSV="${2:?}"; shift 2 ;;
    --security-group-ids) SECURITY_GROUP_IDS_CSV="${2:?}"; shift 2 ;;
    --bronze-bucket-name) BRONZE_BUCKET_NAME="${2:?}"; shift 2 ;;
    --warehouse-bucket-name) WAREHOUSE_BUCKET_NAME="${2:?}"; shift 2 ;;
    --snowflake-export-bucket-name) SNOWFLAKE_EXPORT_BUCKET_NAME="${2:?}"; shift 2 ;;
    --edgar-identity-secret-arn) EDGAR_IDENTITY_SECRET_ARN="${2:?}"; shift 2 ;;
    --execution-role-arn) EXECUTION_ROLE_ARN="${2:?}"; shift 2 ;;
    --task-role-arn) TASK_ROLE_ARN="${2:?}"; shift 2 ;;
    --step-functions-role-arn) STEP_FUNCTIONS_ROLE_ARN="${2:?}"; shift 2 ;;
    --log-group-name) LOG_GROUP_NAME="${2:?}"; shift 2 ;;
    --image-tag) IMAGE_TAG="${2:?}"; shift 2 ;;
    --image-ref) IMAGE_REF="${2:?}"; shift 2 ;;
    --build-image) BUILD_IMAGE=true; shift ;;
    --skip-build) BUILD_IMAGE=false; shift ;;
    --publish-mode) PUBLISH_MODE="${2:?}"; shift 2 ;;
    --push-attempts) PUSH_ATTEMPTS="${2:?}"; shift 2 ;;
    --platform) PLATFORM="${2:?}"; shift 2 ;;
    --context) BUILD_CONTEXT="${2:?}"; shift 2 ;;
    --dockerfile) DOCKERFILE_PATH="${2:?}"; shift 2 ;;
    --warehouse-runtime-mode) WAREHOUSE_RUNTIME_MODE="${2:?}"; shift 2 ;;
    --warehouse-bronze-cik-limit) WAREHOUSE_BRONZE_CIK_LIMIT="${2:?}"; shift 2 ;;
    --bootstrap-batch-concurrency) BOOTSTRAP_BATCH_CONCURRENCY="${2:?}"; shift 2 ;;
    --enable-mdm) MDM_DEPLOYMENT_MODE="enabled"; shift ;;
    --skip-mdm) MDM_DEPLOYMENT_MODE="disabled"; shift ;;
    --mdm-postgres-dsn-secret-arn) MDM_POSTGRES_DSN_SECRET_ARN="${2:?}"; shift 2 ;;
    --mdm-neo4j-secret-arn) MDM_NEO4J_SECRET_ARN="${2:?}"; shift 2 ;;
    --mdm-api-keys-secret-arn) MDM_API_KEYS_SECRET_ARN="${2:?}"; shift 2 ;;
    --mdm-silver-duckdb) MDM_SILVER_DUCKDB="${2:?}"; shift 2 ;;
    --mdm-run-limit) MDM_RUN_LIMIT="${2:?}"; shift 2 ;;
    --mdm-graph-limit) MDM_GRAPH_LIMIT="${2:?}"; shift 2 ;;
    --output-file) OUTPUT_FILE="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$ENVIRONMENT" == "dev" || "$ENVIRONMENT" == "prod" ]] || { usage >&2; exit 2; }
[[ "$WAREHOUSE_RUNTIME_MODE" == "bronze_capture" || "$WAREHOUSE_RUNTIME_MODE" == "infrastructure_validation" ]] || fail "--warehouse-runtime-mode must be bronze_capture or infrastructure_validation"
[[ "$PUSH_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || fail "--push-attempts must be a positive integer"
[[ "$BOOTSTRAP_BATCH_CONCURRENCY" =~ ^[1-9][0-9]*$ ]] || fail "--bootstrap-batch-concurrency must be a positive integer"
[[ "$MDM_RUN_LIMIT" =~ ^[0-9]+$ ]] || fail "--mdm-run-limit must be a non-negative integer"
[[ "$MDM_GRAPH_LIMIT" =~ ^[0-9]+$ ]] || fail "--mdm-graph-limit must be a non-negative integer"
if ! is_empty "$WAREHOUSE_BRONZE_CIK_LIMIT"; then
  [[ "$WAREHOUSE_BRONZE_CIK_LIMIT" =~ ^[0-9]+$ ]] || fail "--warehouse-bronze-cik-limit must be a non-negative integer"
fi

case "$PUBLISH_MODE" in
  auto|linux|crane) ;;
  *) fail "--publish-mode must be one of auto, linux, crane" ;;
esac

require_command aws
require_command python3

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_DIR="${REPO_ROOT}/infra/scripts"
TF_ROOT="${TF_ROOT:-${REPO_ROOT}/infra/terraform/accounts/${ENVIRONMENT}}"
ACCESS_TF_ROOT="${ACCESS_TF_ROOT:-${REPO_ROOT}/infra/terraform/access/aws/accounts/${ENVIRONMENT}}"
NAME_PREFIX="${NAME_PREFIX:-edgartools-${ENVIRONMENT}}"
RUNNER_EXECUTION_ROLE_NAME="sec_platform_runner_execution"
RUNNER_TASK_ROLE_NAME="sec_platform_runner_task"
RUNNER_STEP_FUNCTIONS_ROLE_NAME="sec_platform_runner_step_functions"
BUILD_CONTEXT="${BUILD_CONTEXT:-${REPO_ROOT}}"
DOCKERFILE_PATH="${DOCKERFILE_PATH:-${REPO_ROOT}/Dockerfile}"
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD 2>/dev/null || printf '%s' "$ENVIRONMENT")}"

if is_empty "$BUILD_IMAGE"; then
  if is_empty "$IMAGE_REF"; then
    BUILD_IMAGE=true
  else
    BUILD_IMAGE=false
  fi
fi

aws_cli() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" "$@"
  else
    aws --region "$AWS_REGION_NAME" "$@"
  fi
}

tf_raw() {
  if [[ "$USE_TERRAFORM_DISCOVERY" != "true" || ! -d "$TF_ROOT" ]]; then
    return 0
  fi
  terraform -chdir="$TF_ROOT" output -raw "$1" 2>/dev/null || true
}

tf_json() {
  if [[ "$USE_TERRAFORM_DISCOVERY" != "true" || ! -d "$TF_ROOT" ]]; then
    return 0
  fi
  terraform -chdir="$TF_ROOT" output -json "$1" 2>/dev/null || true
}

tf_access_raw() {
  if [[ "$USE_TERRAFORM_DISCOVERY" != "true" || ! -d "$ACCESS_TF_ROOT" ]]; then
    return 0
  fi
  terraform -chdir="$ACCESS_TF_ROOT" output -raw "$1" 2>/dev/null || true
}

require_runner_role_name() {
  local arn="$1" expected_name="$2" option_name="$3" actual_name
  actual_name="${arn##*/}"
  if [[ "$actual_name" != "$expected_name" ]]; then
    fail "${option_name} must reference IAM role ${expected_name}; got ${arn}"
  fi
}

csv_to_json_array() {
  python3 - "$1" <<'PY'
import json
import sys

values = [part.strip() for part in sys.argv[1].split(",") if part.strip()]
print(json.dumps(values))
PY
}

json_array_is_empty() {
  python3 - "$1" <<'PY'
import json
import sys

try:
    value = json.loads(sys.argv[1] or "[]")
except json.JSONDecodeError:
    value = []
raise SystemExit(0 if not value else 1)
PY
}

if [[ "$USE_TERRAFORM_DISCOVERY" == "true" ]]; then
  require_command terraform
fi

ECR_REPOSITORY_URL="$(first_nonempty "$ECR_REPOSITORY_URL" "$(tf_raw ecr_repository_url)")"
CLUSTER_NAME="$(first_nonempty "$CLUSTER_NAME" "$(tf_raw cluster_name)")"
CLUSTER_ARN="$(first_nonempty "$CLUSTER_ARN" "$(tf_raw cluster_arn)")"
BRONZE_BUCKET_NAME="$(first_nonempty "$BRONZE_BUCKET_NAME" "$(tf_raw bronze_bucket_name)")"
WAREHOUSE_BUCKET_NAME="$(first_nonempty "$WAREHOUSE_BUCKET_NAME" "$(tf_raw warehouse_bucket_name)")"
SNOWFLAKE_EXPORT_BUCKET_NAME="$(first_nonempty "$SNOWFLAKE_EXPORT_BUCKET_NAME" "$(tf_raw snowflake_export_bucket_name)")"
EDGAR_IDENTITY_SECRET_ARN="$(first_nonempty "$EDGAR_IDENTITY_SECRET_ARN" "$(tf_raw edgar_identity_secret_arn)")"
EXECUTION_ROLE_ARN="$(first_nonempty "$EXECUTION_ROLE_ARN" "$(tf_access_raw runner_execution_role_arn)" "$(tf_access_raw ecs_task_execution_role_arn)" "$(tf_raw ecs_task_execution_role_arn)")"
TASK_ROLE_ARN="$(first_nonempty "$TASK_ROLE_ARN" "$(tf_access_raw runner_task_role_arn)" "$(tf_access_raw ecs_task_role_arn)" "$(tf_raw ecs_task_role_arn)")"
STEP_FUNCTIONS_ROLE_ARN="$(first_nonempty "$STEP_FUNCTIONS_ROLE_ARN" "$(tf_access_raw runner_step_functions_role_arn)" "$(tf_access_raw step_functions_role_arn)")"
LOG_GROUP_NAME="$(first_nonempty "$LOG_GROUP_NAME" "$(tf_raw log_group_name)" "/aws/ecs/${NAME_PREFIX}-warehouse")"
MDM_POSTGRES_DSN_SECRET_ARN="$(first_nonempty "$MDM_POSTGRES_DSN_SECRET_ARN" "$(tf_raw mdm_postgres_dsn_secret_arn)")"
MDM_NEO4J_SECRET_ARN="$(first_nonempty "$MDM_NEO4J_SECRET_ARN" "$(tf_raw mdm_neo4j_secret_arn)")"
MDM_API_KEYS_SECRET_ARN="$(first_nonempty "$MDM_API_KEYS_SECRET_ARN" "$(tf_raw mdm_api_keys_secret_arn)")"

if is_empty "$PUBLIC_SUBNET_IDS_JSON"; then
  if ! is_empty "$PUBLIC_SUBNET_IDS_CSV"; then
    PUBLIC_SUBNET_IDS_JSON="$(csv_to_json_array "$PUBLIC_SUBNET_IDS_CSV")"
  else
    PUBLIC_SUBNET_IDS_JSON="$(tf_json public_subnet_ids)"
  fi
fi

if is_empty "$SECURITY_GROUP_IDS_JSON"; then
  if ! is_empty "$SECURITY_GROUP_IDS_CSV"; then
    SECURITY_GROUP_IDS_JSON="$(csv_to_json_array "$SECURITY_GROUP_IDS_CSV")"
  else
    public_sg="$(tf_raw public_ecs_security_group_id)"
    if ! is_empty "$public_sg"; then
      SECURITY_GROUP_IDS_JSON="$(csv_to_json_array "$public_sg")"
    fi
  fi
fi

ACCOUNT_ID="$(aws_cli sts get-caller-identity --query Account --output text)"

if is_empty "$CLUSTER_ARN" && ! is_empty "$CLUSTER_NAME"; then
  CLUSTER_ARN="$(aws_cli ecs describe-clusters --clusters "$CLUSTER_NAME" --query 'clusters[0].clusterArn' --output text 2>/dev/null || true)"
fi
if is_empty "$CLUSTER_NAME" && ! is_empty "$CLUSTER_ARN"; then
  CLUSTER_NAME="${CLUSTER_ARN##*/}"
fi
if is_empty "$EXECUTION_ROLE_ARN"; then
  EXECUTION_ROLE_ARN="$(aws_cli iam get-role --role-name "$RUNNER_EXECUTION_ROLE_NAME" --query 'Role.Arn' --output text 2>/dev/null || true)"
fi
if is_empty "$TASK_ROLE_ARN"; then
  TASK_ROLE_ARN="$(aws_cli iam get-role --role-name "$RUNNER_TASK_ROLE_NAME" --query 'Role.Arn' --output text 2>/dev/null || true)"
fi
if is_empty "$STEP_FUNCTIONS_ROLE_ARN"; then
  STEP_FUNCTIONS_ROLE_ARN="$(aws_cli iam get-role --role-name "$RUNNER_STEP_FUNCTIONS_ROLE_NAME" --query 'Role.Arn' --output text 2>/dev/null || true)"
fi
if is_empty "$ECR_REPOSITORY_URL"; then
  ECR_REPOSITORY_URL="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION_NAME}.amazonaws.com/${NAME_PREFIX}-warehouse"
fi
if is_empty "$PUBLIC_SUBNET_IDS_JSON" || json_array_is_empty "$PUBLIC_SUBNET_IDS_JSON"; then
  PUBLIC_SUBNET_IDS_JSON="$(
    aws_cli ec2 describe-subnets \
      --filters Name=tag:Project,Values=edgartools Name=tag:Environment,Values="$ENVIRONMENT" Name=tag:Name,Values="${NAME_PREFIX}-public-*" \
      --query 'sort_by(Subnets,&AvailabilityZone)[].SubnetId' \
      --output json 2>/dev/null || true
  )"
fi
if is_empty "$SECURITY_GROUP_IDS_JSON" || json_array_is_empty "$SECURITY_GROUP_IDS_JSON"; then
  SECURITY_GROUP_IDS_JSON="$(
    aws_cli ec2 describe-security-groups \
      --filters Name=group-name,Values="${NAME_PREFIX}-ecs-public" Name=tag:Project,Values=edgartools Name=tag:Environment,Values="$ENVIRONMENT" \
      --query 'SecurityGroups[].GroupId' \
      --output json 2>/dev/null || true
  )"
fi

is_empty "$CLUSTER_ARN" && fail "could not resolve ECS cluster ARN; pass --cluster-arn or run Terraform apply with updated outputs"
is_empty "$CLUSTER_NAME" && fail "could not resolve ECS cluster name; pass --cluster-name"
is_empty "$ECR_REPOSITORY_URL" && fail "could not resolve ECR repository URL; pass --ecr-repository-url"
is_empty "$BRONZE_BUCKET_NAME" && fail "could not resolve bronze bucket name; pass --bronze-bucket-name"
is_empty "$WAREHOUSE_BUCKET_NAME" && fail "could not resolve warehouse bucket name; pass --warehouse-bucket-name"
is_empty "$SNOWFLAKE_EXPORT_BUCKET_NAME" && fail "could not resolve Snowflake export bucket name; pass --snowflake-export-bucket-name"
is_empty "$EDGAR_IDENTITY_SECRET_ARN" && fail "could not resolve EDGAR identity secret ARN; pass --edgar-identity-secret-arn"
is_empty "$EXECUTION_ROLE_ARN" && fail "could not resolve ECS task execution role ARN; pass --execution-role-arn"
is_empty "$TASK_ROLE_ARN" && fail "could not resolve ECS task role ARN; pass --task-role-arn"
is_empty "$STEP_FUNCTIONS_ROLE_ARN" && fail "could not resolve Step Functions role ARN; apply the AWS access root or pass --step-functions-role-arn"
require_runner_role_name "$EXECUTION_ROLE_ARN" "$RUNNER_EXECUTION_ROLE_NAME" "--execution-role-arn"
require_runner_role_name "$TASK_ROLE_ARN" "$RUNNER_TASK_ROLE_NAME" "--task-role-arn"
require_runner_role_name "$STEP_FUNCTIONS_ROLE_ARN" "$RUNNER_STEP_FUNCTIONS_ROLE_NAME" "--step-functions-role-arn"
is_empty "$PUBLIC_SUBNET_IDS_JSON" && fail "could not resolve public subnet IDs; pass --public-subnet-ids"
is_empty "$SECURITY_GROUP_IDS_JSON" && fail "could not resolve ECS security group IDs; pass --security-group-ids"
if json_array_is_empty "$PUBLIC_SUBNET_IDS_JSON"; then
  fail "public subnet IDs resolved to an empty list"
fi
if json_array_is_empty "$SECURITY_GROUP_IDS_JSON"; then
  fail "security group IDs resolved to an empty list"
fi
if [[ "$BUILD_IMAGE" != "true" ]] && is_empty "$IMAGE_REF"; then
  fail "--skip-build requires --image-ref"
fi

MDM_SILVER_DUCKDB="$(first_nonempty "$MDM_SILVER_DUCKDB" "s3://${WAREHOUSE_BUCKET_NAME}/warehouse/silver/sec/silver.duckdb")"
DEPLOY_MDM=false
missing_mdm_values=()
is_empty "$MDM_POSTGRES_DSN_SECRET_ARN" && missing_mdm_values+=("mdm_postgres_dsn_secret_arn")
is_empty "$MDM_NEO4J_SECRET_ARN" && missing_mdm_values+=("mdm_neo4j_secret_arn")
is_empty "$MDM_API_KEYS_SECRET_ARN" && missing_mdm_values+=("mdm_api_keys_secret_arn")
case "$MDM_DEPLOYMENT_MODE" in
  enabled)
    if [[ ${#missing_mdm_values[@]} -gt 0 ]]; then
      fail "--enable-mdm requires MDM secret ARNs; missing: ${missing_mdm_values[*]}"
    fi
    DEPLOY_MDM=true
    ;;
  disabled)
    DEPLOY_MDM=false
    ;;
  auto)
    if [[ ${#missing_mdm_values[@]} -eq 0 ]]; then
      DEPLOY_MDM=true
    else
      log "Skipping MDM task definitions/state machines; missing Terraform outputs or flags: ${missing_mdm_values[*]}"
    fi
    ;;
  *)
    fail "invalid internal MDM deployment mode: ${MDM_DEPLOYMENT_MODE}"
    ;;
esac

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/edgartools-aws-application-XXXXXX")"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

json_file() {
  mktemp "${TMP_DIR}/$1-XXXXXX.json"
}

ECR_REPOSITORY_NAME="${ECR_REPOSITORY_URL##*/}"

if [[ "$BUILD_IMAGE" == "true" ]]; then
  image_output_file="$(json_file image-ref)"
  publish_args=(
    --aws-region "$AWS_REGION_NAME"
    --ecr-repository "$ECR_REPOSITORY_NAME"
    --image-tag "$IMAGE_TAG"
    --mode "$PUBLISH_MODE"
    --push-attempts "$PUSH_ATTEMPTS"
    --platform "$PLATFORM"
    --context "$BUILD_CONTEXT"
    --dockerfile "$DOCKERFILE_PATH"
    --output-file "$image_output_file"
  )
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    publish_args+=(--aws-profile "$AWS_PROFILE_NAME")
  fi
  log "Building and publishing warehouse image ${ECR_REPOSITORY_NAME}:${IMAGE_TAG}"
  bash "${SCRIPT_DIR}/publish-warehouse-image.sh" "${publish_args[@]}"
  IMAGE_REF="$(tr -d '\r\n' < "$image_output_file")"
fi

log "Deploying image reference ${IMAGE_REF}"

write_container_definitions() {
  local output_file="$1" profile="$2"
  python3 - "$output_file" "$profile" "$IMAGE_REF" "$AWS_REGION_NAME" "$ENVIRONMENT" \
    "$WAREHOUSE_RUNTIME_MODE" "$BRONZE_BUCKET_NAME" "$WAREHOUSE_BUCKET_NAME" \
    "$SNOWFLAKE_EXPORT_BUCKET_NAME" "$EDGAR_IDENTITY_SECRET_ARN" "$LOG_GROUP_NAME" \
    "$WAREHOUSE_BRONZE_CIK_LIMIT" <<'PY'
import json
import pathlib
import sys

(
    output_file,
    profile,
    image_ref,
    aws_region,
    environment,
    runtime_mode,
    bronze_bucket,
    warehouse_bucket,
    snowflake_export_bucket,
    edgar_secret_arn,
    log_group_name,
    bronze_cik_limit,
) = sys.argv[1:]

snowflake_export_root = f"s3://{snowflake_export_bucket}/warehouse/artifacts/snowflake_exports"
environment_values = [
    {"name": "AWS_REGION", "value": aws_region},
    {"name": "WAREHOUSE_ENVIRONMENT", "value": environment},
    {"name": "WAREHOUSE_RUNTIME_MODE", "value": runtime_mode},
    {"name": "WAREHOUSE_BRONZE_ROOT", "value": f"s3://{bronze_bucket}/warehouse/bronze"},
    {"name": "WAREHOUSE_STORAGE_ROOT", "value": f"s3://{warehouse_bucket}/warehouse"},
    {"name": "WAREHOUSE_SILVER_ROOT", "value": "/tmp/edgar-warehouse-silver"},
    {"name": "SNOWFLAKE_EXPORT_ROOT", "value": snowflake_export_root},
    {"name": "SERVING_EXPORT_ROOT", "value": snowflake_export_root},
]
if bronze_cik_limit:
    environment_values.append({"name": "WAREHOUSE_BRONZE_CIK_LIMIT", "value": bronze_cik_limit})

container_definitions = [{
    "name": "edgar-warehouse",
    "image": image_ref,
    "essential": True,
    "command": ["--help"],
    "environment": environment_values,
    "secrets": [{"name": "EDGAR_IDENTITY", "valueFrom": edgar_secret_arn}],
    "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
            "awslogs-group": log_group_name,
            "awslogs-region": aws_region,
            "awslogs-stream-prefix": f"warehouse-{profile}",
        },
    },
}]

pathlib.Path(output_file).write_text(json.dumps(container_definitions, indent=2) + "\n", encoding="utf-8")
PY
}

register_task_definition() {
  local profile="$1" cpu="$2" memory="$3" container_file task_def_arn
  container_file="$(json_file "container-${profile}")"
  write_container_definitions "$container_file" "$profile"
  log "Registering ECS task definition ${NAME_PREFIX}-${profile}"
  task_def_arn="$(
    aws_cli ecs register-task-definition \
      --family "${NAME_PREFIX}-${profile}" \
      --requires-compatibilities FARGATE \
      --network-mode awsvpc \
      --cpu "$cpu" \
      --memory "$memory" \
      --execution-role-arn "$EXECUTION_ROLE_ARN" \
      --task-role-arn "$TASK_ROLE_ARN" \
      --container-definitions "file://${container_file}" \
      --tags key=Environment,value="$ENVIRONMENT" key=ManagedBy,value=operator-script key=Project,value=edgartools key=TaskProfile,value="$profile" key=Runtime,value=warehouse \
      --query 'taskDefinition.taskDefinitionArn' \
      --output text
  )"
  printf '%s\n' "$task_def_arn"
}

write_mdm_container_definitions() {
  local output_file="$1" profile="$2"
  python3 - "$output_file" "$profile" "$IMAGE_REF" "$AWS_REGION_NAME" "$ENVIRONMENT" \
    "$WAREHOUSE_BUCKET_NAME" "$MDM_SILVER_DUCKDB" "$MDM_POSTGRES_DSN_SECRET_ARN" \
    "$MDM_NEO4J_SECRET_ARN" "$MDM_API_KEYS_SECRET_ARN" "$LOG_GROUP_NAME" <<'PY'
import json
import pathlib
import sys

(
    output_file,
    profile,
    image_ref,
    aws_region,
    environment,
    warehouse_bucket,
    mdm_silver_duckdb,
    mdm_database_secret_arn,
    neo4j_secret_arn,
    api_keys_secret_arn,
    log_group_name,
) = sys.argv[1:]

environment_values = [
    {"name": "AWS_REGION", "value": aws_region},
    {"name": "WAREHOUSE_ENVIRONMENT", "value": environment},
    {"name": "WAREHOUSE_STORAGE_ROOT", "value": f"s3://{warehouse_bucket}/warehouse"},
    {"name": "MDM_SILVER_DUCKDB", "value": mdm_silver_duckdb},
]

container_definitions = [{
    "name": "edgar-warehouse",
    "image": image_ref,
    "essential": True,
    "command": ["mdm", "--help"],
    "environment": environment_values,
    "secrets": [
        {"name": "MDM_DATABASE_URL", "valueFrom": mdm_database_secret_arn},
        {"name": "NEO4J_SECRET_JSON", "valueFrom": neo4j_secret_arn},
        {"name": "MDM_API_KEYS", "valueFrom": api_keys_secret_arn},
    ],
    "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
            "awslogs-group": log_group_name,
            "awslogs-region": aws_region,
            "awslogs-stream-prefix": f"mdm-{profile}",
        },
    },
}]

pathlib.Path(output_file).write_text(json.dumps(container_definitions, indent=2) + "\n", encoding="utf-8")
PY
}

register_mdm_task_definition() {
  local profile="$1" cpu="$2" memory="$3" container_file task_def_arn
  container_file="$(json_file "container-${profile}")"
  write_mdm_container_definitions "$container_file" "$profile"
  log "Registering ECS task definition ${NAME_PREFIX}-${profile}"
  task_def_arn="$(
    aws_cli ecs register-task-definition \
      --family "${NAME_PREFIX}-${profile}" \
      --requires-compatibilities FARGATE \
      --network-mode awsvpc \
      --cpu "$cpu" \
      --memory "$memory" \
      --execution-role-arn "$EXECUTION_ROLE_ARN" \
      --task-role-arn "$TASK_ROLE_ARN" \
      --container-definitions "file://${container_file}" \
      --tags key=Environment,value="$ENVIRONMENT" key=ManagedBy,value=operator-script key=Project,value=edgartools key=TaskProfile,value="$profile" key=Runtime,value=mdm \
      --query 'taskDefinition.taskDefinitionArn' \
      --output text
  )"
  printf '%s\n' "$task_def_arn"
}

TASK_DEF_SMALL_ARN="$(register_task_definition small 512 1024)"
TASK_DEF_MEDIUM_ARN="$(register_task_definition medium 1024 2048)"
TASK_DEF_LARGE_ARN="$(register_task_definition large 2048 4096)"
TASK_DEF_MDM_SMALL_ARN=""
TASK_DEF_MDM_MEDIUM_ARN=""
if [[ "$DEPLOY_MDM" == "true" ]]; then
  TASK_DEF_MDM_SMALL_ARN="$(register_mdm_task_definition mdm-small 512 1024)"
  TASK_DEF_MDM_MEDIUM_ARN="$(register_mdm_task_definition mdm-medium 1024 2048)"
fi

task_definition_for_profile() {
  case "$1" in
    small) printf '%s\n' "$TASK_DEF_SMALL_ARN" ;;
    medium) printf '%s\n' "$TASK_DEF_MEDIUM_ARN" ;;
    large) printf '%s\n' "$TASK_DEF_LARGE_ARN" ;;
    *) fail "unknown task profile: $1" ;;
  esac
}

task_definition_for_mdm_workflow() {
  case "$1" in
    mdm_migrate|mdm_check_connectivity|mdm_verify_graph|mdm_counts) printf '%s\n' "$TASK_DEF_MDM_SMALL_ARN" ;;
    mdm_run|mdm_backfill_relationships|mdm_sync_graph) printf '%s\n' "$TASK_DEF_MDM_MEDIUM_ARN" ;;
    *) fail "unknown MDM workflow: $1" ;;
  esac
}

workflow_profile() {
  case "$1" in
    daily_incremental) printf '%s\n' "medium" ;;
    bootstrap_recent_10) printf '%s\n' "medium" ;;
    bootstrap_full) printf '%s\n' "large" ;;
    targeted_resync) printf '%s\n' "small" ;;
    full_reconcile) printf '%s\n' "medium" ;;
    load_daily_form_index_for_date) printf '%s\n' "small" ;;
    catch_up_daily_form_index) printf '%s\n' "small" ;;
    *) fail "unknown workflow: $1" ;;
  esac
}

workflow_command_expression() {
  case "$1" in
    daily_incremental) printf '%s\n' "States.Array('daily-incremental', '--run-id', \$\$.Execution.Name)" ;;
    bootstrap_recent_10) printf '%s\n' "States.Array('bootstrap-recent-10', '--run-id', \$\$.Execution.Name)" ;;
    bootstrap_full) printf '%s\n' "States.Array('bootstrap-full', '--run-id', \$\$.Execution.Name)" ;;
    targeted_resync) printf '%s\n' "States.Array('targeted-resync', '--scope-type', \$.scope_type, '--scope-key', \$.scope_key, '--run-id', \$\$.Execution.Name)" ;;
    full_reconcile) printf '%s\n' "States.Array('full-reconcile', '--run-id', \$\$.Execution.Name)" ;;
    load_daily_form_index_for_date) printf '%s\n' "States.Array('load-daily-form-index-for-date', \$.target_date, '--run-id', \$\$.Execution.Name)" ;;
    catch_up_daily_form_index) printf '%s\n' "States.Array('catch-up-daily-form-index', '--run-id', \$\$.Execution.Name)" ;;
    *) fail "unknown workflow: $1" ;;
  esac
}

workflow_cik_command_expression() {
  case "$1" in
    daily_incremental) printf '%s\n' "States.Array('daily-incremental', '--run-id', \$\$.Execution.Name, '--cik-list', \$.cik_list)" ;;
    bootstrap_recent_10) printf '%s\n' "States.Array('bootstrap-recent-10', '--run-id', \$\$.Execution.Name, '--cik-list', \$.cik_list)" ;;
    bootstrap_full) printf '%s\n' "States.Array('bootstrap-full', '--run-id', \$\$.Execution.Name, '--cik-list', \$.cik_list)" ;;
    *) return 0 ;;
  esac
}

mdm_workflow_command_expression() {
  case "$1" in
    mdm_migrate) printf '%s\n' "States.Array('mdm', 'migrate')" ;;
    mdm_check_connectivity) printf '%s\n' "States.Array('mdm', 'check-connectivity', '--neo4j')" ;;
    mdm_run)
      if [[ "$MDM_RUN_LIMIT" -gt 0 ]]; then
        printf '%s\n' "States.Array('mdm', 'run', '--entity-type', 'all', '--limit', '${MDM_RUN_LIMIT}')"
      else
        printf '%s\n' "States.Array('mdm', 'run', '--entity-type', 'all')"
      fi
      ;;
    mdm_backfill_relationships)
      if [[ "$MDM_GRAPH_LIMIT" -gt 0 ]]; then
        printf '%s\n' "States.Array('mdm', 'backfill-relationships', '--limit', '${MDM_GRAPH_LIMIT}')"
      else
        printf '%s\n' "States.Array('mdm', 'backfill-relationships')"
      fi
      ;;
    mdm_sync_graph)
      if [[ "$MDM_GRAPH_LIMIT" -gt 0 ]]; then
        printf '%s\n' "States.Array('mdm', 'sync-graph', '--limit', '${MDM_GRAPH_LIMIT}')"
      else
        printf '%s\n' "States.Array('mdm', 'sync-graph')"
      fi
      ;;
    mdm_verify_graph) printf '%s\n' "States.Array('mdm', 'verify-graph')" ;;
    mdm_counts) printf '%s\n' "States.Array('mdm', 'counts')" ;;
    *) fail "unknown MDM workflow: $1" ;;
  esac
}

mdm_workflow_limit_command_expression() {
  case "$1" in
    mdm_run) printf '%s\n' "States.Array('mdm', 'run', '--entity-type', 'all', '--limit', States.Format('{}', $.limit))" ;;
    mdm_backfill_relationships) printf '%s\n' "States.Array('mdm', 'backfill-relationships', '--limit', States.Format('{}', $.limit))" ;;
    mdm_sync_graph) printf '%s\n' "States.Array('mdm', 'sync-graph', '--limit', States.Format('{}', $.limit))" ;;
    *) return 0 ;;
  esac
}

ensure_log_group() {
  local log_group_name="$1" log_group_arn
  if aws_cli logs describe-log-groups --log-group-name-prefix "$log_group_name" --query "logGroups[?logGroupName=='${log_group_name}'].logGroupName | [0]" --output text 2>/dev/null | grep -qx "$log_group_name"; then
    log "Step Functions log group exists: ${log_group_name}"
  else
    log "Creating Step Functions log group ${log_group_name}"
    aws_cli logs create-log-group \
      --log-group-name "$log_group_name" \
      --tags Environment="$ENVIRONMENT",ManagedBy=operator-script,Project=edgartools >/dev/null
  fi
  aws_cli logs put-retention-policy --log-group-name "$log_group_name" --retention-in-days 30 >/dev/null
  log_group_arn="$(aws_cli logs describe-log-groups --log-group-name-prefix "$log_group_name" --query "logGroups[?logGroupName=='${log_group_name}'].arn | [0]" --output text)"
  if [[ "$log_group_arn" != *":*" ]]; then
    log_group_arn="${log_group_arn}:*"
  fi
  printf '%s\n' "$log_group_arn"
}

write_logging_configuration() {
  local output_file="$1" log_group_arn="$2"
  python3 - "$output_file" "$log_group_arn" <<'PY'
import json
import pathlib
import sys

logging = {
    "level": "ALL",
    "includeExecutionData": True,
    "destinations": [{
        "cloudWatchLogsLogGroup": {"logGroupArn": sys.argv[2]},
    }],
}
pathlib.Path(sys.argv[1]).write_text(json.dumps(logging, indent=2) + "\n", encoding="utf-8")
PY
}

write_single_workflow_definition() {
  local output_file="$1" task_definition_arn="$2" default_command="$3" cik_command="$4"
  python3 - "$output_file" "$CLUSTER_ARN" "$task_definition_arn" "edgar-warehouse" \
    "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" "$default_command" "$cik_command" <<'PY'
import json
import pathlib
import sys

(
    output_file,
    cluster_arn,
    task_definition_arn,
    container_name,
    subnet_json,
    security_group_json,
    default_command,
    cik_command,
) = sys.argv[1:]

subnets = json.loads(subnet_json)
security_groups = json.loads(security_group_json)

def run_task_state(command_expression):
    return {
        "Type": "Task",
        "Resource": "arn:aws:states:::ecs:runTask.sync",
        "Parameters": {
            "LaunchType": "FARGATE",
            "Cluster": cluster_arn,
            "TaskDefinition": task_definition_arn,
            "PropagateTags": "TASK_DEFINITION",
            "NetworkConfiguration": {
                "AwsvpcConfiguration": {
                    "AssignPublicIp": "ENABLED",
                    "SecurityGroups": security_groups,
                    "Subnets": subnets,
                },
            },
            "Overrides": {
                "ContainerOverrides": [{
                    "Name": container_name,
                    "Command.$": command_expression,
                }],
            },
        },
        "Retry": [{
            "ErrorEquals": ["States.TaskFailed"],
            "IntervalSeconds": 60,
            "BackoffRate": 2.0,
            "MaxAttempts": 2,
        }],
        "End": True,
    }

if cik_command:
    definition = {
        "Comment": "Run an EdgarTools warehouse workflow on ECS Fargate with an optional cik_list override.",
        "StartAt": "HasCikListOverride",
        "States": {
            "HasCikListOverride": {
                "Type": "Choice",
                "Choices": [{
                    "And": [
                        {"Variable": "$.cik_list", "IsPresent": True},
                        {"Variable": "$.cik_list", "IsString": True},
                    ],
                    "Next": "RunWarehouseTaskWithCikList",
                }],
                "Default": "RunWarehouseTaskDefault",
            },
            "RunWarehouseTaskDefault": run_task_state(default_command),
            "RunWarehouseTaskWithCikList": run_task_state(cik_command),
        },
    }
else:
    definition = {
        "Comment": "Run an EdgarTools warehouse workflow on ECS Fargate.",
        "StartAt": "RunWarehouseTask",
        "States": {"RunWarehouseTask": run_task_state(default_command)},
    }

pathlib.Path(output_file).write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
PY
}

write_mdm_workflow_definition() {
  local output_file="$1" task_definition_arn="$2" default_command="$3" limit_command="$4"
  python3 - "$output_file" "$CLUSTER_ARN" "$task_definition_arn" "edgar-warehouse" \
    "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" "$default_command" "$limit_command" <<'PY'
import json
import pathlib
import sys

(
    output_file,
    cluster_arn,
    task_definition_arn,
    container_name,
    subnet_json,
    security_group_json,
    default_command,
    limit_command,
) = sys.argv[1:]

subnets = json.loads(subnet_json)
security_groups = json.loads(security_group_json)

def run_task_state(command_expression):
    return {
        "Type": "Task",
        "Resource": "arn:aws:states:::ecs:runTask.sync",
        "Parameters": {
            "LaunchType": "FARGATE",
            "Cluster": cluster_arn,
            "TaskDefinition": task_definition_arn,
            "PropagateTags": "TASK_DEFINITION",
            "NetworkConfiguration": {
                "AwsvpcConfiguration": {
                    "AssignPublicIp": "ENABLED",
                    "SecurityGroups": security_groups,
                    "Subnets": subnets,
                },
            },
            "Overrides": {
                "ContainerOverrides": [{
                    "Name": container_name,
                    "Command.$": command_expression,
                }],
            },
        },
        "Retry": [{
            "ErrorEquals": ["States.TaskFailed"],
            "IntervalSeconds": 60,
            "BackoffRate": 2.0,
            "MaxAttempts": 2,
        }],
        "End": True,
    }

if limit_command:
    definition = {
        "Comment": "Run an EdgarTools MDM workflow on ECS Fargate with an optional numeric limit override.",
        "StartAt": "HasLimitOverride",
        "States": {
            "HasLimitOverride": {
                "Type": "Choice",
                "Choices": [{
                    "And": [
                        {"Variable": "$.limit", "IsPresent": True},
                        {"Variable": "$.limit", "IsNumeric": True},
                    ],
                    "Next": "RunMdmTaskWithLimit",
                }],
                "Default": "RunMdmTaskDefault",
            },
            "RunMdmTaskDefault": run_task_state(default_command),
            "RunMdmTaskWithLimit": run_task_state(limit_command),
        },
    }
else:
    definition = {
        "Comment": "Run an EdgarTools MDM workflow on ECS Fargate.",
        "StartAt": "RunMdmTask",
        "States": {"RunMdmTask": run_task_state(default_command)},
    }

pathlib.Path(output_file).write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
PY
}

write_bootstrap_batched_definition() {
  local output_file="$1" seed_task_definition_arn="$2" batch_task_definition_arn="$3"
  python3 - "$output_file" "$CLUSTER_ARN" "$seed_task_definition_arn" "$batch_task_definition_arn" \
    "edgar-warehouse" "$BRONZE_BUCKET_NAME" "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" \
    "$BOOTSTRAP_BATCH_CONCURRENCY" <<'PY'
import json
import pathlib
import sys

(
    output_file,
    cluster_arn,
    seed_task_definition_arn,
    batch_task_definition_arn,
    container_name,
    bronze_bucket_name,
    subnet_json,
    security_group_json,
    batch_concurrency,
) = sys.argv[1:]

subnets = json.loads(subnet_json)
security_groups = json.loads(security_group_json)

def run_task_state(task_definition_arn, command_expression, interval_seconds):
    return {
        "Type": "Task",
        "Resource": "arn:aws:states:::ecs:runTask.sync",
        "Parameters": {
            "LaunchType": "FARGATE",
            "Cluster": cluster_arn,
            "TaskDefinition": task_definition_arn,
            "PropagateTags": "TASK_DEFINITION",
            "NetworkConfiguration": {
                "AwsvpcConfiguration": {
                    "AssignPublicIp": "ENABLED",
                    "SecurityGroups": security_groups,
                    "Subnets": subnets,
                },
            },
            "Overrides": {
                "ContainerOverrides": [{
                    "Name": container_name,
                    "Command.$": command_expression,
                }],
            },
        },
        "Retry": [{
            "ErrorEquals": ["States.TaskFailed"],
            "IntervalSeconds": interval_seconds,
            "BackoffRate": 2.0,
            "MaxAttempts": 2,
        }],
    }

seed = run_task_state(
    seed_task_definition_arn,
    "States.Array('seed-universe', '--run-id', $$.Execution.Name)",
    60,
)
seed["Next"] = "BatchBootstrap"

batch = run_task_state(
    batch_task_definition_arn,
    "States.Array('bootstrap-batch', '--cik-list', $.cik_list, '--run-id', $$.Execution.Name)",
    120,
)
batch["End"] = True

definition = {
    "Comment": "Seed CIK universe then bootstrap companies in parallel batches of 100.",
    "StartAt": "SeedUniverse",
    "States": {
        "SeedUniverse": seed,
        "BatchBootstrap": {
            "Type": "Map",
            "MaxConcurrency": int(batch_concurrency),
            "ItemReader": {
                "Resource": "arn:aws:states:::s3:getObject",
                "ReaderConfig": {
                    "InputType": "JSONL",
                    "MaxItems": 100000,
                },
                "Parameters": {
                    "Bucket": bronze_bucket_name,
                    "Key.$": "States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_batches.jsonl', $$.Execution.Name)",
                },
            },
            "ItemProcessor": {
                "ProcessorConfig": {
                    "Mode": "DISTRIBUTED",
                    "ExecutionType": "STANDARD",
                },
                "StartAt": "RunBatch",
                "States": {"RunBatch": batch},
            },
            "End": True,
        },
    },
}

pathlib.Path(output_file).write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
PY
}

upsert_state_machine() {
  local workflow="$1" definition_file="$2" role_arn="$3" logging_file="$4" name arn existing_arn
  name="${NAME_PREFIX}-${workflow//_/-}"
  arn="arn:aws:states:${AWS_REGION_NAME}:${ACCOUNT_ID}:stateMachine:${name}"
  existing_arn="$(aws_cli stepfunctions describe-state-machine --state-machine-arn "$arn" --query 'stateMachineArn' --output text 2>/dev/null || true)"
  if is_empty "$existing_arn"; then
    log "Creating Step Functions state machine ${name}"
    aws_cli stepfunctions create-state-machine \
      --name "$name" \
      --role-arn "$role_arn" \
      --definition "file://${definition_file}" \
      --type STANDARD \
      --logging-configuration "file://${logging_file}" \
      --tags key=Environment,value="$ENVIRONMENT" key=ManagedBy,value=operator-script key=Project,value=edgartools key=Workflow,value="$workflow" \
      --query 'stateMachineArn' \
      --output text
  else
    log "Updating Step Functions state machine ${name}"
    aws_cli stepfunctions update-state-machine \
      --state-machine-arn "$arn" \
      --role-arn "$role_arn" \
      --definition "file://${definition_file}" \
      --logging-configuration "file://${logging_file}" >/dev/null
    aws_cli stepfunctions tag-resource \
      --resource-arn "$arn" \
      --tags key=Environment,value="$ENVIRONMENT" key=ManagedBy,value=operator-script key=Project,value=edgartools key=Workflow,value="$workflow" >/dev/null
    printf '%s\n' "$arn"
  fi
}

require_runner_role_name "$STEP_FUNCTIONS_ROLE_ARN" "$RUNNER_STEP_FUNCTIONS_ROLE_NAME" "--step-functions-role-arn"
STEP_FUNCTIONS_LOG_GROUP_NAME="/aws/states/${NAME_PREFIX}-warehouse"
STEP_FUNCTIONS_LOG_GROUP_ARN="$(ensure_log_group "$STEP_FUNCTIONS_LOG_GROUP_NAME")"
LOGGING_CONFIGURATION_FILE="$(json_file step-functions-logging)"
write_logging_configuration "$LOGGING_CONFIGURATION_FILE" "$STEP_FUNCTIONS_LOG_GROUP_ARN"

WORKFLOW_ARNS_FILE="$(json_file workflow-arns)"
printf '{\n' > "$WORKFLOW_ARNS_FILE"
first_workflow=true

for workflow in daily_incremental bootstrap_recent_10 bootstrap_full targeted_resync full_reconcile load_daily_form_index_for_date catch_up_daily_form_index; do
  profile="$(workflow_profile "$workflow")"
  task_definition_arn="$(task_definition_for_profile "$profile")"
  command_expression="$(workflow_command_expression "$workflow")"
  cik_command_expression="$(workflow_cik_command_expression "$workflow")"
  definition_file="$(json_file "sfn-${workflow}")"
  write_single_workflow_definition "$definition_file" "$task_definition_arn" "$command_expression" "$cik_command_expression"
  state_machine_arn="$(upsert_state_machine "$workflow" "$definition_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
  if [[ "$first_workflow" == "true" ]]; then
    first_workflow=false
  else
    printf ',\n' >> "$WORKFLOW_ARNS_FILE"
  fi
  python3 - "$workflow" "$state_machine_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
import json
import sys

print(f"  {json.dumps(sys.argv[1])}: {json.dumps(sys.argv[2])}", end="")
PY
done

bootstrap_definition_file="$(json_file sfn-bootstrap-batched)"
write_bootstrap_batched_definition "$bootstrap_definition_file" "$TASK_DEF_SMALL_ARN" "$TASK_DEF_MEDIUM_ARN"
bootstrap_state_machine_arn="$(upsert_state_machine bootstrap_batched "$bootstrap_definition_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
if [[ "$first_workflow" != "true" ]]; then
  printf ',\n' >> "$WORKFLOW_ARNS_FILE"
fi
python3 - "bootstrap_batched" "$bootstrap_state_machine_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
import json
import sys

print(f"  {json.dumps(sys.argv[1])}: {json.dumps(sys.argv[2])}", end="")
PY

if [[ "$DEPLOY_MDM" == "true" ]]; then
  for workflow in mdm_migrate mdm_check_connectivity mdm_run mdm_backfill_relationships mdm_sync_graph mdm_verify_graph mdm_counts; do
    task_definition_arn="$(task_definition_for_mdm_workflow "$workflow")"
    command_expression="$(mdm_workflow_command_expression "$workflow")"
    limit_command_expression="$(mdm_workflow_limit_command_expression "$workflow")"
    definition_file="$(json_file "sfn-${workflow}")"
    write_mdm_workflow_definition "$definition_file" "$task_definition_arn" "$command_expression" "$limit_command_expression"
    state_machine_arn="$(upsert_state_machine "$workflow" "$definition_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
    printf ',\n' >> "$WORKFLOW_ARNS_FILE"
    python3 - "$workflow" "$state_machine_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
import json
import sys

print(f"  {json.dumps(sys.argv[1])}: {json.dumps(sys.argv[2])}", end="")
PY
  done
fi
printf '\n}\n' >> "$WORKFLOW_ARNS_FILE"

SUMMARY_FILE="$(json_file deployment-summary)"
python3 - "$SUMMARY_FILE" "$ENVIRONMENT" "$AWS_REGION_NAME" "$NAME_PREFIX" "$IMAGE_REF" \
  "$CLUSTER_NAME" "$CLUSTER_ARN" "$ECR_REPOSITORY_URL" "$LOG_GROUP_NAME" \
  "$STEP_FUNCTIONS_ROLE_ARN" "$STEP_FUNCTIONS_LOG_GROUP_NAME" \
  "$TASK_DEF_SMALL_ARN" "$TASK_DEF_MEDIUM_ARN" "$TASK_DEF_LARGE_ARN" \
  "$DEPLOY_MDM" "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_MDM_MEDIUM_ARN" "$MDM_SILVER_DUCKDB" \
  "$MDM_POSTGRES_DSN_SECRET_ARN" "$MDM_NEO4J_SECRET_ARN" "$MDM_API_KEYS_SECRET_ARN" \
  "$WORKFLOW_ARNS_FILE" <<'PY'
import json
import pathlib
import sys

(
    output_file,
    environment,
    region,
    name_prefix,
    image_ref,
    cluster_name,
    cluster_arn,
    ecr_repository_url,
    ecs_log_group_name,
    step_functions_role_arn,
    step_functions_log_group_name,
    small_task_definition,
    medium_task_definition,
    large_task_definition,
    deploy_mdm,
    mdm_small_task_definition,
    mdm_medium_task_definition,
    mdm_silver_duckdb,
    mdm_database_secret_arn,
    neo4j_secret_arn,
    api_keys_secret_arn,
    workflow_arns_file,
) = sys.argv[1:]

task_definitions = {
    "small": small_task_definition,
    "medium": medium_task_definition,
    "large": large_task_definition,
}
if deploy_mdm == "true":
    task_definitions["mdm_small"] = mdm_small_task_definition
    task_definitions["mdm_medium"] = mdm_medium_task_definition

summary = {
    "environment": environment,
    "region": region,
    "name_prefix": name_prefix,
    "image_ref": image_ref,
    "cluster": {
        "name": cluster_name,
        "arn": cluster_arn,
    },
    "ecr_repository_url": ecr_repository_url,
    "log_groups": {
        "ecs": ecs_log_group_name,
        "step_functions": step_functions_log_group_name,
    },
    "step_functions_role_arn": step_functions_role_arn,
    "task_definitions": task_definitions,
    "state_machines": json.loads(pathlib.Path(workflow_arns_file).read_text(encoding="utf-8")),
}
if deploy_mdm == "true":
    summary["mdm"] = {
        "silver_duckdb": mdm_silver_duckdb,
        "secrets": {
            "postgres_dsn": mdm_database_secret_arn,
            "neo4j": neo4j_secret_arn,
            "api_keys": api_keys_secret_arn,
        },
    }

pathlib.Path(output_file).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
PY

if ! is_empty "$OUTPUT_FILE"; then
  cp "$SUMMARY_FILE" "$OUTPUT_FILE"
fi

cat "$SUMMARY_FILE"
