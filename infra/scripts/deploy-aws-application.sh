#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  deploy-aws-application.sh --env <dev|prod> [options]

Deploys active AWS application components — no Terraform required:
  - optional warehouse Docker image build and ECR push
  - ECS Fargate task definitions for warehouse task profiles
  - Step Functions log group and state machines

Infrastructure parameters (bucket names, role ARNs, secret ARNs) are resolved in order:
  1. CLI flag (explicit override)
  2. Deployment manifest (infra/aws-<env>-application.json — written by every successful deploy)
  3. AWS API discovery / deterministic naming convention
Terraform is only needed for initial provisioning (infra/terraform/); never for normal operations.

Options:
  --env <dev|prod>                  Environment name. Required.
  --aws-profile <profile>           AWS CLI profile.
  --aws-account-id <12-digit-id>    Expected AWS account. Required. Deployment stops if STS
                                    resolves the selected profile to a different account.
  --aws-region <region>             AWS region. Default: AWS_REGION, AWS_DEFAULT_REGION, or us-east-1.
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
  --execution-role-arn <arn>        ECS task execution role ARN. Must be named
                                    <runner-role-name-prefix>_runner_execution.
  --task-role-arn <arn>             ECS task role ARN. Must be named
                                    <runner-role-name-prefix>_runner_task.
  --step-functions-role-arn <arn>   Step Functions role ARN. Must be named
                                    <runner-role-name-prefix>_runner_step_functions.
  --runner-role-name-prefix <prefix>
                                    Expected prefix for the three runner role names above.
                                    Default: sec_platform. Override when a second environment
                                    shares this AWS account and Terraform was applied with a
                                    matching runner_role_name_prefix (see
                                    infra/terraform/access/aws/modules/runtime_access).
  --log-group-name <name>           ECS task log group name.
  --image-tag <tag>                 Image tag for build/push. Default: git short SHA.
  --image-ref <ref>                 Existing image ref to deploy. Skips build unless --build-image is set.
  --build-image                     Build and push the warehouse image before deployment.
  --skip-build                      Do not build; requires --image-ref.
  --publish-mode <auto|docker|buildx>
                                    Image publish mode. Default: auto.
  --image-cache-from-tag <tag>      Plain Docker cache source tag, usually dev.
  --image-cache-tag <tag>           Buildx registry cache tag, usually buildcache.
  --also-tag <tag>                  Additional tag to push for built images. Repeatable.
  --push-attempts <count>           Image push retry count. Default: 1.
  --platform <platform>             Docker target platform. Default: linux/amd64.
  --context <path>                  Docker build context. Default: repo root.
  --dockerfile <path>               Dockerfile path. Default: repo root Dockerfile.
  --warehouse-runtime-mode <mode>   bronze_capture or infrastructure_validation. Default: bronze_capture.
  --warehouse-bronze-cik-limit <n>  Optional WAREHOUSE_BRONZE_CIK_LIMIT.
  --bootstrap-batch-concurrency <n> Distributed Map bootstrap concurrency. Default: 10.
  --enable-mdm                      Deploy MDM ECS task definitions and state machines; fail if MDM secret ARNs are missing.
  --skip-mdm                        Do not deploy MDM ECS task definitions or state machines.
  --mdm-image-ref <ref>             Existing MDM image ref. Defaults to warehouse image ref when not building MDM separately.
  --mdm-ecr-repository-url <url>    ECR repository URL for built MDM image. Default: <account>.dkr.ecr.<region>.amazonaws.com/<prefix>-mdm.
  --build-mdm-image                 Build and push a separate MDM image when MDM is deployed.
  --mdm-database-source <rds|snowflake-postgres>
                                    Source of the MDM_DATABASE_URL secret. Default: rds.
                                    Use snowflake-postgres after the secret contains the Snowflake Postgres application DSN.
  --mdm-postgres-dsn-secret-arn <arn>
                                    Secrets Manager ARN injected as MDM_DATABASE_URL.
  --mdm-snowflake-secret-arn <arn>  Secrets Manager ARN injected as MDM_SNOWFLAKE_SECRET_JSON.
  --mdm-silver-duckdb <uri>         MDM_SILVER_DUCKDB. Default: s3://<warehouse-bucket>/warehouse/silver/sec/silver.duckdb.
  --mdm-run-limit <n>               Default limit for mdm run state machine. Default: 100; 0 means no default limit.
  --mdm-graph-limit <n>             Default limit for mdm graph backfill/sync. Default: 200; 0 means no default limit.
  --mdm-seed-universe-tracking-status <status>
                                    tracking_status baked into mdm_seed_universe state machine. Default: bootstrap_pending.
  --mdm-seed-from-silver-tracking-status <status>
                                    tracking_status filter for mdm_seed_from_silver (migrate silver→MDM). Default: bootstrap_pending.
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
EXPECTED_AWS_ACCOUNT_ID=""
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
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
MDM_IMAGE_REF=""
BUILD_IMAGE=""
BUILD_MDM_IMAGE=""
PUBLISH_MODE="auto"
IMAGE_CACHE_FROM_TAG=""
IMAGE_CACHE_TAG=""
IMAGE_ALSO_TAGS=()
PUSH_ATTEMPTS=1
PLATFORM="linux/amd64"
BUILD_CONTEXT=""
DOCKERFILE_PATH=""
WAREHOUSE_RUNTIME_MODE="bronze_capture"
WAREHOUSE_BRONZE_CIK_LIMIT=""
BOOTSTRAP_BATCH_CONCURRENCY=3
MDM_DEPLOYMENT_MODE="auto"
MDM_DATABASE_SOURCE=""
MDM_ECR_REPOSITORY_URL=""
MDM_POSTGRES_DSN_SECRET_ARN=""
MDM_SNOWFLAKE_SECRET_ARN=""
MDM_SILVER_DUCKDB=""
MDM_RUN_LIMIT=100
MDM_GRAPH_LIMIT=200
MDM_SEED_UNIVERSE_TRACKING_STATUS="bootstrap_pending"
MDM_SEED_FROM_SILVER_TRACKING_STATUS="bootstrap_pending"
RUNNER_ROLE_NAME_PREFIX="sec_platform"
OUTPUT_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-account-id) EXPECTED_AWS_ACCOUNT_ID="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
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
    --mdm-image-ref) MDM_IMAGE_REF="${2:?}"; shift 2 ;;
    --build-image) BUILD_IMAGE=true; shift ;;
    --build-mdm-image) BUILD_MDM_IMAGE=true; shift ;;
    --skip-build) BUILD_IMAGE=false; shift ;;
    --publish-mode) PUBLISH_MODE="${2:?}"; shift 2 ;;
    --image-cache-from-tag) IMAGE_CACHE_FROM_TAG="${2:?}"; shift 2 ;;
    --image-cache-tag) IMAGE_CACHE_TAG="${2:?}"; shift 2 ;;
    --also-tag) IMAGE_ALSO_TAGS+=("${2:?}"); shift 2 ;;
    --push-attempts) PUSH_ATTEMPTS="${2:?}"; shift 2 ;;
    --platform) PLATFORM="${2:?}"; shift 2 ;;
    --context) BUILD_CONTEXT="${2:?}"; shift 2 ;;
    --dockerfile) DOCKERFILE_PATH="${2:?}"; shift 2 ;;
    --warehouse-runtime-mode) WAREHOUSE_RUNTIME_MODE="${2:?}"; shift 2 ;;
    --warehouse-bronze-cik-limit) WAREHOUSE_BRONZE_CIK_LIMIT="${2:?}"; shift 2 ;;
    --bootstrap-batch-concurrency) BOOTSTRAP_BATCH_CONCURRENCY="${2:?}"; shift 2 ;;
    --enable-mdm) MDM_DEPLOYMENT_MODE="enabled"; shift ;;
    --skip-mdm) MDM_DEPLOYMENT_MODE="disabled"; shift ;;
    --mdm-database-source) MDM_DATABASE_SOURCE="${2:?}"; shift 2 ;;
    --mdm-ecr-repository-url) MDM_ECR_REPOSITORY_URL="${2:?}"; shift 2 ;;
    --mdm-postgres-dsn-secret-arn) MDM_POSTGRES_DSN_SECRET_ARN="${2:?}"; shift 2 ;;
    --mdm-snowflake-secret-arn) MDM_SNOWFLAKE_SECRET_ARN="${2:?}"; shift 2 ;;
    --mdm-silver-duckdb) MDM_SILVER_DUCKDB="${2:?}"; shift 2 ;;
    --mdm-run-limit) MDM_RUN_LIMIT="${2:?}"; shift 2 ;;
    --mdm-graph-limit) MDM_GRAPH_LIMIT="${2:?}"; shift 2 ;;
    --mdm-seed-universe-tracking-status) MDM_SEED_UNIVERSE_TRACKING_STATUS="${2:?}"; shift 2 ;;
    --mdm-seed-from-silver-tracking-status) MDM_SEED_FROM_SILVER_TRACKING_STATUS="${2:?}"; shift 2 ;;
    --runner-role-name-prefix) RUNNER_ROLE_NAME_PREFIX="${2:?}"; shift 2 ;;
    --output-file) OUTPUT_FILE="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$ENVIRONMENT" == "dev" || "$ENVIRONMENT" == "prod" ]] || { usage >&2; exit 2; }
[[ -n "$EXPECTED_AWS_ACCOUNT_ID" ]] || fail "--aws-account-id is required"
if [[ ! "$EXPECTED_AWS_ACCOUNT_ID" =~ ^[0-9]{12}$ ]]; then
  fail "--aws-account-id must be a 12-digit AWS account ID"
fi
[[ "$WAREHOUSE_RUNTIME_MODE" == "bronze_capture" || "$WAREHOUSE_RUNTIME_MODE" == "infrastructure_validation" ]] || fail "--warehouse-runtime-mode must be bronze_capture or infrastructure_validation"
[[ "$PUSH_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || fail "--push-attempts must be a positive integer"
[[ "$BOOTSTRAP_BATCH_CONCURRENCY" =~ ^[1-9][0-9]*$ ]] || fail "--bootstrap-batch-concurrency must be a positive integer"
[[ "$MDM_RUN_LIMIT" =~ ^[0-9]+$ ]] || fail "--mdm-run-limit must be a non-negative integer"
[[ "$MDM_GRAPH_LIMIT" =~ ^[0-9]+$ ]] || fail "--mdm-graph-limit must be a non-negative integer"
if ! is_empty "$MDM_DATABASE_SOURCE"; then
  case "$MDM_DATABASE_SOURCE" in
    rds|snowflake-postgres) ;;
    *) fail "--mdm-database-source must be rds or snowflake-postgres" ;;
  esac
fi
if ! is_empty "$WAREHOUSE_BRONZE_CIK_LIMIT"; then
  [[ "$WAREHOUSE_BRONZE_CIK_LIMIT" =~ ^[0-9]+$ ]] || fail "--warehouse-bronze-cik-limit must be a non-negative integer"
fi

case "$PUBLISH_MODE" in
  auto|docker|macos-docker|buildx|linux|linux-buildx|windows-buildx|crane) ;;
  *) fail "--publish-mode must be one of auto, docker, buildx, macos-docker, linux-buildx, windows-buildx, crane" ;;
esac
case "$BUILD_MDM_IMAGE" in
  ""|auto|true|false) ;;
  *) fail "--build-mdm-image is a flag and cannot take a value" ;;
esac

require_command aws
require_command python3

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_DIR="${REPO_ROOT}/infra/scripts"
MANIFEST_FILE="${REPO_ROOT}/infra/aws-${ENVIRONMENT}-application.json"
NAME_PREFIX="${NAME_PREFIX:-edgartools-${ENVIRONMENT}}"
RUNNER_EXECUTION_ROLE_NAME="${RUNNER_ROLE_NAME_PREFIX}_runner_execution"
RUNNER_TASK_ROLE_NAME="${RUNNER_ROLE_NAME_PREFIX}_runner_task"
RUNNER_STEP_FUNCTIONS_ROLE_NAME="${RUNNER_ROLE_NAME_PREFIX}_runner_step_functions"
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

if is_empty "$BUILD_MDM_IMAGE"; then
  BUILD_MDM_IMAGE=auto
fi

aws_cli() {
  # MSYS_NO_PATHCONV=1 prevents Git Bash from translating /aws/states/... style
  # CloudWatch log group names into Windows filesystem paths (e.g. C:/Program Files/Git/aws/...).
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    MSYS_NO_PATHCONV=1 aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" "$@"
  else
    MSYS_NO_PATHCONV=1 aws --region "$AWS_REGION_NAME" "$@"
  fi
}

# Read a top-level or dotted-path value from the deployment manifest.
# Usage: manifest_value "key"  OR  manifest_value "mdm.secrets.postgres_dsn"
manifest_value() {
  [[ -f "$MANIFEST_FILE" ]] || return 0
  # On Windows Git Bash, REPO_ROOT/MANIFEST_FILE are MSYS-style paths
  # (e.g. /c/work/...) from `pwd`. bash resolves these fine, but the
  # native Windows python3 invoked below cannot -- open('/c/work/...')
  # fails with "No such file or directory" (it looks for a literal
  # directory named "c", not drive C:), so this silently returned empty
  # on Windows and every dependent value fell through to "could not
  # resolve". cygpath -m gives the drive-letter form with forward
  # slashes (C:/work/...), which both bash and native python understand,
  # and avoids embedding backslashes in the python string literal below
  # (a literal "C:\work\...\aws-..." would corrupt via \a being read as
  # a bell-character escape). No-op on Linux/macOS: no cygpath there,
  # and REPO_ROOT is already a plain POSIX path python3 handles natively.
  local manifest_path="$MANIFEST_FILE"
  if command -v cygpath >/dev/null 2>&1; then
    manifest_path="$(cygpath -m "$MANIFEST_FILE")"
  fi
  python3 -c "
import json, sys
try:
    d = json.load(open('${manifest_path}'))
    for k in '${1}'.split('.'): d = d[k]
    print(d or '', end='')
except Exception: pass
" 2>/dev/null || true
}

# Look up a Secrets Manager ARN by secret name (partial match on name prefix).
secret_arn_by_name() {
  aws_cli secretsmanager describe-secret --secret-id "$1" \
    --query 'ARN' --output text 2>/dev/null || true
}

# Resolve an S3 bucket name without assuming a naming convention. Terraform's
# account-suffix convention differs across environments (dev appends
# ${ACCOUNT_ID}, prod does not — see infra/terraform/accounts/prod/main.tf),
# so guessing one fixed pattern silently points task defs at a bucket that
# doesn't exist. Instead, check which candidate name actually exists in S3
# and use that; only fall back to construction (with a loud warning) if
# neither candidate exists yet (e.g. infra not provisioned yet, dry-run).
resolve_bucket_name() {
  local purpose="$1" suffixed="${NAME_PREFIX}-${1}-${ACCOUNT_ID}" unsuffixed="${NAME_PREFIX}-${1}"
  if aws_cli s3api head-bucket --bucket "$unsuffixed" >/dev/null 2>&1; then
    echo "$unsuffixed"
  elif aws_cli s3api head-bucket --bucket "$suffixed" >/dev/null 2>&1; then
    echo "$suffixed"
  else
    echo "WARNING: neither s3://${unsuffixed} nor s3://${suffixed} exists; defaulting to s3://${suffixed} (verify Terraform has been applied)" >&2
    echo "$suffixed"
  fi
}

MDM_DATABASE_SOURCE="$(first_nonempty "$MDM_DATABASE_SOURCE" "$(manifest_value mdm.database_source)" "rds")"
case "$MDM_DATABASE_SOURCE" in
  rds|snowflake-postgres) ;;
  *) fail "--mdm-database-source must be rds or snowflake-postgres" ;;
esac

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

# Resolve account ID first — bucket naming convention depends on it.
ACCOUNT_ID="$(aws_cli sts get-caller-identity --query Account --output text)"
if [[ "$ACCOUNT_ID" != "$EXPECTED_AWS_ACCOUNT_ID" ]]; then
  fail "AWS account mismatch: --aws-account-id requested ${EXPECTED_AWS_ACCOUNT_ID}, but profile ${AWS_PROFILE_NAME:-<default>} resolved to ${ACCOUNT_ID}."
fi

# Parameter resolution order (no Terraform):
#   1. CLI flag (already set above)
#   2. Deployment manifest (infra/aws-<env>-application.json — written by every successful deploy)
#   3. AWS API discovery / deterministic naming convention

# Cluster
CLUSTER_ARN="$(first_nonempty "$CLUSTER_ARN" "$(manifest_value cluster.arn)")"
CLUSTER_NAME="$(first_nonempty "$CLUSTER_NAME" "$(manifest_value cluster.name)")"

# ECR — naming convention: <account>.dkr.ecr.<region>.amazonaws.com/<prefix>-warehouse
ECR_REPOSITORY_URL="$(first_nonempty "$ECR_REPOSITORY_URL" "$(manifest_value ecr_repository_url)" \
  "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION_NAME}.amazonaws.com/${NAME_PREFIX}-warehouse")"

# S3 buckets — naming convention is environment-dependent (dev appends
# ${ACCOUNT_ID}, prod does not), so resolve_bucket_name checks which name
# actually exists in S3 rather than assuming a fixed pattern. CLI flag and
# manifest value (a name a prior run confirmed/was told to use) still win.
BRONZE_BUCKET_NAME="$(first_nonempty "$BRONZE_BUCKET_NAME" \
  "$(manifest_value bronze_bucket_name)" \
  "$(resolve_bucket_name bronze)")"
WAREHOUSE_BUCKET_NAME="$(first_nonempty "$WAREHOUSE_BUCKET_NAME" \
  "$(manifest_value warehouse_bucket_name)" \
  "$(resolve_bucket_name warehouse)")"
SNOWFLAKE_EXPORT_BUCKET_NAME="$(first_nonempty "$SNOWFLAKE_EXPORT_BUCKET_NAME" \
  "$(manifest_value snowflake_export_bucket_name)" \
  "$(resolve_bucket_name snowflake-export)")"

# IAM roles — fixed names provisioned by Terraform access layer; look up via IAM API
EXECUTION_ROLE_ARN="$(first_nonempty "$EXECUTION_ROLE_ARN" \
  "$(manifest_value execution_role_arn)" \
  "$(aws_cli iam get-role --role-name "$RUNNER_EXECUTION_ROLE_NAME" --query 'Role.Arn' --output text 2>/dev/null || true)")"
TASK_ROLE_ARN="$(first_nonempty "$TASK_ROLE_ARN" \
  "$(manifest_value task_role_arn)" \
  "$(aws_cli iam get-role --role-name "$RUNNER_TASK_ROLE_NAME" --query 'Role.Arn' --output text 2>/dev/null || true)")"
STEP_FUNCTIONS_ROLE_ARN="$(first_nonempty "$STEP_FUNCTIONS_ROLE_ARN" \
  "$(manifest_value step_functions_role_arn)" \
  "$(aws_cli iam get-role --role-name "$RUNNER_STEP_FUNCTIONS_ROLE_NAME" --query 'Role.Arn' --output text 2>/dev/null || true)")"

# CloudWatch log group
LOG_GROUP_NAME="$(first_nonempty "$LOG_GROUP_NAME" \
  "$(manifest_value log_groups.ecs)" \
  "/aws/ecs/${NAME_PREFIX}-warehouse")"

# Secrets Manager ARNs — look up by name; names are fixed conventions
EDGAR_IDENTITY_SECRET_ARN="$(first_nonempty "$EDGAR_IDENTITY_SECRET_ARN" \
  "$(manifest_value edgar_identity_secret_arn)" \
  "$(secret_arn_by_name "${NAME_PREFIX}-edgar-identity")")"
MDM_POSTGRES_DSN_SECRET_ARN="$(first_nonempty "$MDM_POSTGRES_DSN_SECRET_ARN" \
  "$(manifest_value mdm.secrets.postgres_dsn)" \
  "$(secret_arn_by_name "${NAME_PREFIX}/mdm/postgres_dsn")")"
MDM_SNOWFLAKE_SECRET_ARN="$(first_nonempty "$MDM_SNOWFLAKE_SECRET_ARN" \
  "$(manifest_value mdm.secrets.snowflake)" \
  "$(secret_arn_by_name "${NAME_PREFIX}/mdm/snowflake")")"

# Subnets and security groups — discovered via EC2 tags (no Terraform needed)
if is_empty "$PUBLIC_SUBNET_IDS_JSON"; then
  if ! is_empty "$PUBLIC_SUBNET_IDS_CSV"; then
    PUBLIC_SUBNET_IDS_JSON="$(csv_to_json_array "$PUBLIC_SUBNET_IDS_CSV")"
  fi
fi

if is_empty "$SECURITY_GROUP_IDS_JSON" && ! is_empty "$SECURITY_GROUP_IDS_CSV"; then
  SECURITY_GROUP_IDS_JSON="$(csv_to_json_array "$SECURITY_GROUP_IDS_CSV")"
fi

# Cluster name ↔ ARN cross-derivation
if is_empty "$CLUSTER_ARN" && ! is_empty "$CLUSTER_NAME"; then
  CLUSTER_ARN="$(aws_cli ecs describe-clusters --clusters "$CLUSTER_NAME" --query 'clusters[0].clusterArn' --output text 2>/dev/null || true)"
fi
if is_empty "$CLUSTER_NAME" && ! is_empty "$CLUSTER_ARN"; then
  CLUSTER_NAME="${CLUSTER_ARN##*/}"
fi

# MDM ECR — naming convention
if is_empty "$MDM_ECR_REPOSITORY_URL"; then
  MDM_ECR_REPOSITORY_URL="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION_NAME}.amazonaws.com/${NAME_PREFIX}-mdm"
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

is_empty "$CLUSTER_ARN" && fail "could not resolve ECS cluster ARN; pass --cluster-arn or ensure the manifest file ${MANIFEST_FILE} exists"
is_empty "$CLUSTER_NAME" && fail "could not resolve ECS cluster name; pass --cluster-name"
is_empty "$ECR_REPOSITORY_URL" && fail "could not resolve ECR repository URL; pass --ecr-repository-url"
is_empty "$BRONZE_BUCKET_NAME" && fail "could not resolve bronze bucket name; pass --bronze-bucket-name"
is_empty "$WAREHOUSE_BUCKET_NAME" && fail "could not resolve warehouse bucket name; pass --warehouse-bucket-name"
is_empty "$SNOWFLAKE_EXPORT_BUCKET_NAME" && fail "could not resolve Snowflake export bucket name; pass --snowflake-export-bucket-name"
is_empty "$EDGAR_IDENTITY_SECRET_ARN" && fail "could not resolve EDGAR identity secret ARN; pass --edgar-identity-secret-arn"
is_empty "$EXECUTION_ROLE_ARN" && fail "could not resolve ECS task execution role ARN; pass --execution-role-arn"
is_empty "$TASK_ROLE_ARN" && fail "could not resolve ECS task role ARN; pass --task-role-arn"
is_empty "$STEP_FUNCTIONS_ROLE_ARN" && fail "could not resolve Step Functions role ARN; check IAM role ${RUNNER_STEP_FUNCTIONS_ROLE_NAME} exists or pass --step-functions-role-arn"
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
is_empty "$MDM_SNOWFLAKE_SECRET_ARN" && missing_mdm_values+=("mdm_snowflake_secret_arn")
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
      log "Skipping MDM task definitions/state machines; missing values: ${missing_mdm_values[*]}"
    fi
    ;;
  *)
    fail "invalid internal MDM deployment mode: ${MDM_DEPLOYMENT_MODE}"
    ;;
esac

# Pre-cutover compatibility: sync the MDM Postgres DSN secret from the
# AWS-managed RDS credential when --mdm-database-source rds is selected.
# Snowflake Postgres deployments must pass --mdm-database-source
# snowflake-postgres so this block does not overwrite the application DSN.
sync_mdm_postgres_dsn() {
  local dsn_secret_arn="$1"
  local rds_instance_id="$2"

  log "Syncing MDM Postgres DSN from live RDS credential (instance: ${rds_instance_id})"

  local rds_json master_secret_arn host port dbname cred_json username password dsn
  rds_json="$(aws_cli rds describe-db-instances \
    --db-instance-identifier "$rds_instance_id" \
    --query 'DBInstances[0].{Host:Endpoint.Address,Port:Endpoint.Port,DB:DBName,SecretArn:MasterUserSecret.SecretArn}' \
    --output json 2>/dev/null)" || { log "WARN: could not describe RDS instance ${rds_instance_id}; skipping DSN sync"; return 0; }

  host="$(python3 -c "import json,sys; print(json.loads(sys.stdin.read())['Host'])" <<< "$rds_json")"
  port="$(python3 -c "import json,sys; print(json.loads(sys.stdin.read())['Port'])" <<< "$rds_json")"
  dbname="$(python3 -c "import json,sys; print(json.loads(sys.stdin.read())['DB'])" <<< "$rds_json")"
  master_secret_arn="$(python3 -c "import json,sys; print(json.loads(sys.stdin.read())['SecretArn'])" <<< "$rds_json")"

  if is_empty "$master_secret_arn"; then
    log "WARN: RDS instance ${rds_instance_id} has no AWS-managed master secret; skipping DSN sync"
    return 0
  fi

  cred_json="$(aws_cli secretsmanager get-secret-value \
    --secret-id "$master_secret_arn" \
    --query SecretString --output text 2>/dev/null)" || { log "WARN: could not read RDS master secret; skipping DSN sync"; return 0; }

  dsn="$(CRED_JSON="$cred_json" python3 - "$host" "$port" "$dbname" <<'PY'
import json, os, sys
from urllib.parse import quote_plus
cred = json.loads(os.environ["CRED_JSON"])
host, port, db = sys.argv[1], sys.argv[2], sys.argv[3]
u = quote_plus(cred["username"])
p = quote_plus(cred["password"])
print(f"postgresql+psycopg2://{u}:{p}@{host}:{port}/{db}?sslmode=require")
PY
)"

  aws_cli secretsmanager put-secret-value \
    --secret-id "$dsn_secret_arn" \
    --secret-string "$dsn" >/dev/null
  log "MDM Postgres DSN secret updated (host=${host} db=${dbname} sslmode=require)"
}

if [[ "$DEPLOY_MDM" == "true" ]] && ! is_empty "$MDM_POSTGRES_DSN_SECRET_ARN"; then
  MDM_RDS_INSTANCE_ID="${NAME_PREFIX}-mdm"
  if [[ "$MDM_DATABASE_SOURCE" == "rds" ]]; then
    sync_mdm_postgres_dsn "$MDM_POSTGRES_DSN_SECRET_ARN" "$MDM_RDS_INSTANCE_ID"
  else
    log "Skipping RDS DSN sync; using operator-managed Snowflake Postgres DSN secret (${MDM_POSTGRES_DSN_SECRET_ARN})"
  fi
fi

# Wire S3 → SNS bucket notification so Snowpipe receives ObjectCreated events for manifests.
# 5-why root cause: Snowflake had stale data because this notification was never configured,
# meaning Snowpipe never fired and SNOWFLAKE_RUN_MANIFEST_INBOX stayed empty.
SNOWFLAKE_MANIFEST_SNS_ARN="arn:aws:sns:${AWS_REGION_NAME}:${ACCOUNT_ID}:${NAME_PREFIX}-snowflake-manifest-events"
MANIFEST_PREFIX="warehouse/artifacts/snowflake_exports/manifests/"

if aws_cli sns get-topic-attributes \
    --topic-arn "$SNOWFLAKE_MANIFEST_SNS_ARN" \
    --query 'Attributes.TopicArn' --output text 2>/dev/null | grep -q "arn:"; then

  # Ensure the SNS topic policy allows S3 to publish.
  # Use heredoc + sys.argv to avoid nested-double-quote quoting issues.
  SNS_POLICY=$(python3 - "$SNOWFLAKE_MANIFEST_SNS_ARN" "$SNOWFLAKE_EXPORT_BUCKET_NAME" <<'PY'
import json, sys
sns_arn, bucket_name = sys.argv[1], sys.argv[2]
print(json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Sid": "AllowS3BucketNotification",
        "Effect": "Allow",
        "Principal": {"Service": "s3.amazonaws.com"},
        "Action": "SNS:Publish",
        "Resource": sns_arn,
        "Condition": {"ArnLike": {"aws:SourceArn": f"arn:aws:s3:::{bucket_name}"}}
    }]
}))
PY
)
  aws_cli sns set-topic-attributes \
    --topic-arn "$SNOWFLAKE_MANIFEST_SNS_ARN" \
    --attribute-name Policy \
    --attribute-value "$SNS_POLICY" 2>/dev/null || true

  # Set the bucket notification (idempotent — PUT replaces in full)
  NOTIFICATION_JSON=$(python3 - "$SNOWFLAKE_MANIFEST_SNS_ARN" "$MANIFEST_PREFIX" <<'PY'
import json, sys
sns_arn, prefix = sys.argv[1], sys.argv[2]
print(json.dumps({"TopicConfigurations": [{
    "Id": "snowflake-manifest-events",
    "TopicArn": sns_arn,
    "Events": ["s3:ObjectCreated:*"],
    "Filter": {"Key": {"FilterRules": [
        {"Name": "prefix", "Value": prefix},
        {"Name": "suffix", "Value": "run_manifest.json"}
    ]}}
}]}))
PY
)
  aws_cli s3api put-bucket-notification-configuration \
    --bucket "$SNOWFLAKE_EXPORT_BUCKET_NAME" \
    --notification-configuration "$NOTIFICATION_JSON" 2>/dev/null \
    && log "S3 → SNS notification configured on ${SNOWFLAKE_EXPORT_BUCKET_NAME} for manifest prefix" \
    || log "WARN: could not set S3 bucket notification (may need s3:PutBucketNotification permission)"
else
  log "WARN: SNS topic ${SNOWFLAKE_MANIFEST_SNS_ARN} not found — skipping S3 notification wiring"
fi

if [[ "$BUILD_MDM_IMAGE" == "auto" ]]; then
  if [[ "$DEPLOY_MDM" == "true" && "$BUILD_IMAGE" == "true" ]] && is_empty "$MDM_IMAGE_REF"; then
    BUILD_MDM_IMAGE=true
  else
    BUILD_MDM_IMAGE=false
  fi
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/edgartools-aws-application-XXXXXX")"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

json_file() {
  mktemp "${TMP_DIR}/$1-XXXXXX.json"
}

# On Windows Git Bash, /tmp is remapped by the shell but AWS CLI (native exe) reads
# file:// paths as literal Windows paths (C:\tmp\...), not the remapped location.
# cygpath -m converts /tmp/foo → C:/Users/.../AppData/Local/Temp/foo, which AWS CLI
# can resolve correctly on both Windows and Unix.
file_url() {
  if command -v cygpath &>/dev/null 2>&1; then
    printf 'file://%s' "$(cygpath -m "$1")"
  else
    printf 'file://%s' "$1"
  fi
}

# Returns a native-OS path suitable for passing to Python on Windows.
# On Windows Git Bash, cygpath -w converts /tmp/foo → C:\Users\...\AppData\Local\Temp\foo
# so Python (which maps /tmp → C:\tmp\) can find the file.
# On Linux/Mac this is a no-op.
win_path() {
  if command -v cygpath &>/dev/null 2>&1; then
    cygpath -w "$1"
  else
    printf '%s' "$1"
  fi
}

ECR_REPOSITORY_NAME="${ECR_REPOSITORY_URL##*/}"
MDM_ECR_REPOSITORY_NAME="${MDM_ECR_REPOSITORY_URL##*/}"

# ── Clean up stale ECR images before every deploy ────────────────────────────
log "Cleaning up stale ECR images (keeps :dev + 2 newest :sha-* per repo)"
bash "${SCRIPT_DIR}/cleanup-ecr-images.sh" \
  --env "$ENVIRONMENT" \
  --region "$AWS_REGION_NAME" \
  ${AWS_PROFILE_NAME:+--profile "$AWS_PROFILE_NAME"} \
  --apply || log "ECR cleanup encountered errors (non-fatal, continuing deploy)"

if [[ "$BUILD_IMAGE" == "true" ]]; then
  image_output_file="$(json_file image-ref)"
  publish_args=(
    --aws-region "$AWS_REGION_NAME"
    --ecr-repository "$ECR_REPOSITORY_NAME"
    --role warehouse
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
  if [[ -n "$IMAGE_CACHE_FROM_TAG" ]]; then
    publish_args+=(--cache-from-tag "$IMAGE_CACHE_FROM_TAG")
  fi
  if [[ -n "$IMAGE_CACHE_TAG" ]]; then
    publish_args+=(--cache-tag "$IMAGE_CACHE_TAG")
  fi
  for tag in ${IMAGE_ALSO_TAGS[@]+"${IMAGE_ALSO_TAGS[@]}"}; do
    publish_args+=(--also-tag "$tag")
  done
  log "Building and publishing warehouse image ${ECR_REPOSITORY_NAME}:${IMAGE_TAG}"
  bash "${SCRIPT_DIR}/publish-warehouse-image.sh" "${publish_args[@]}"
  IMAGE_REF="$(tr -d '\r\n' < "$image_output_file")"
fi

if [[ "$BUILD_MDM_IMAGE" == "true" ]]; then
  mdm_image_output_file="$(json_file mdm-image-ref)"
  mdm_publish_args=(
    --aws-region "$AWS_REGION_NAME"
    --ecr-repository "$MDM_ECR_REPOSITORY_NAME"
    --role mdm
    --image-tag "$IMAGE_TAG"
    --mode "$PUBLISH_MODE"
    --push-attempts "$PUSH_ATTEMPTS"
    --platform "$PLATFORM"
    --context "$BUILD_CONTEXT"
    --output-file "$mdm_image_output_file"
  )
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    mdm_publish_args+=(--aws-profile "$AWS_PROFILE_NAME")
  fi
  if [[ -n "$IMAGE_CACHE_FROM_TAG" ]]; then
    mdm_publish_args+=(--cache-from-tag "$IMAGE_CACHE_FROM_TAG")
  fi
  if [[ -n "$IMAGE_CACHE_TAG" ]]; then
    mdm_publish_args+=(--cache-tag "$IMAGE_CACHE_TAG")
  fi
  for tag in ${IMAGE_ALSO_TAGS[@]+"${IMAGE_ALSO_TAGS[@]}"}; do
    mdm_publish_args+=(--also-tag "$tag")
  done
  log "Building and publishing MDM image ${MDM_ECR_REPOSITORY_NAME}:${IMAGE_TAG}"
  bash "${SCRIPT_DIR}/publish-warehouse-image.sh" "${mdm_publish_args[@]}"
  MDM_IMAGE_REF="$(tr -d '\r\n' < "$mdm_image_output_file")"
fi

if [[ "$DEPLOY_MDM" == "true" ]] && is_empty "$MDM_IMAGE_REF"; then
  MDM_IMAGE_REF="$IMAGE_REF"
fi

log "Deploying warehouse image reference ${IMAGE_REF}"
if [[ "$DEPLOY_MDM" == "true" ]]; then
  log "Deploying MDM image reference ${MDM_IMAGE_REF}"
fi

write_container_definitions() {
  local output_file="$1" profile="$2"
  # MSYS_NO_PATHCONV=1 prevents Git Bash from translating /aws/ecs/... log group names
  # into Windows filesystem paths. win_path() converts output_file to native Windows
  # form so Python can locate it regardless of /tmp remapping differences.
  # MDM_POSTGRES_DSN_SECRET_ARN is passed (may be empty when MDM is not deployed).
  MSYS_NO_PATHCONV=1 python3 - "$(win_path "$output_file")" "$profile" "$IMAGE_REF" "$AWS_REGION_NAME" "$ENVIRONMENT" \
    "$WAREHOUSE_RUNTIME_MODE" "$BRONZE_BUCKET_NAME" "$WAREHOUSE_BUCKET_NAME" \
    "$SNOWFLAKE_EXPORT_BUCKET_NAME" "$EDGAR_IDENTITY_SECRET_ARN" "$LOG_GROUP_NAME" \
    "$WAREHOUSE_BRONZE_CIK_LIMIT" "${MDM_POSTGRES_DSN_SECRET_ARN:-}" <<'PY'
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
    mdm_postgres_dsn_secret_arn,
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

secrets = [{"name": "EDGAR_IDENTITY", "valueFrom": edgar_secret_arn}]
# MDM_DATABASE_URL is required for gold-affecting commands (seed-universe, bootstrap-*, gold-refresh).
# Inject it from Secrets Manager when MDM is deployed alongside the warehouse.
if mdm_postgres_dsn_secret_arn:
    secrets.append({"name": "MDM_DATABASE_URL", "valueFrom": mdm_postgres_dsn_secret_arn})

container_definitions = [{
    "name": "edgar-warehouse",
    "image": image_ref,
    "essential": True,
    "command": ["--help"],
    "environment": environment_values,
    "secrets": secrets,
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
      --container-definitions "$(file_url "$container_file")" \
      --tags key=Environment,value="$ENVIRONMENT" key=ManagedBy,value=operator-script key=Project,value=edgartools key=TaskProfile,value="$profile" key=Runtime,value=warehouse \
      --query 'taskDefinition.taskDefinitionArn' \
      --output text
  )"
  printf '%s\n' "$task_def_arn"
}

write_mdm_container_definitions() {
  local output_file="$1" profile="$2"
  MSYS_NO_PATHCONV=1 python3 - "$(win_path "$output_file")" "$profile" "$MDM_IMAGE_REF" "$AWS_REGION_NAME" "$ENVIRONMENT" \
    "$BRONZE_BUCKET_NAME" "$WAREHOUSE_BUCKET_NAME" "$MDM_SILVER_DUCKDB" "$MDM_POSTGRES_DSN_SECRET_ARN" \
    "$MDM_SNOWFLAKE_SECRET_ARN" \
    "$EDGAR_IDENTITY_SECRET_ARN" "$LOG_GROUP_NAME" <<'PY'
import json
import pathlib
import sys

(
    output_file,
    profile,
    image_ref,
    aws_region,
    environment,
    bronze_bucket,
    warehouse_bucket,
    mdm_silver_duckdb,
    mdm_database_secret_arn,
    snowflake_secret_arn,
    edgar_secret_arn,
    log_group_name,
) = sys.argv[1:]

environment_values = [
    {"name": "AWS_REGION", "value": aws_region},
    {"name": "WAREHOUSE_ENVIRONMENT", "value": environment},
    {"name": "WAREHOUSE_RUNTIME_MODE", "value": "bronze_capture"},
    {"name": "WAREHOUSE_BRONZE_ROOT", "value": f"s3://{bronze_bucket}/warehouse/bronze"},
    {"name": "WAREHOUSE_STORAGE_ROOT", "value": f"s3://{warehouse_bucket}/warehouse"},
    {"name": "WAREHOUSE_SILVER_ROOT", "value": "/tmp/edgar-warehouse-silver"},
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
        {"name": "MDM_SNOWFLAKE_SECRET_JSON", "valueFrom": snowflake_secret_arn},
        {"name": "EDGAR_IDENTITY", "valueFrom": edgar_secret_arn},
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
      --container-definitions "$(file_url "$container_file")" \
      --tags key=Environment,value="$ENVIRONMENT" key=ManagedBy,value=operator-script key=Project,value=edgartools key=TaskProfile,value="$profile" key=Runtime,value=mdm \
      --query 'taskDefinition.taskDefinitionArn' \
      --output text
  )"
  printf '%s\n' "$task_def_arn"
}

TASK_DEF_SMALL_ARN="$(register_task_definition small 512 1024)"
# medium memory raised 2048 -> 4096 (2026-07-12, fix-pipelines 06-03): the WindowedBootstrap
# per-window `bootstrap-next` runs on `medium` and builds gold from the canonical silver.duckdb
# (full accumulated universe, multi-GB — e.g. 2.7M sec_financial_fact rows), not just its window.
# At 2048 MB it OOM-killed (exit 137) building the sec_financial_fact gold table, failing
# load_history exec #3. 4096 matches the memory the dedicated gold-refresh (`large`) already uses
# for the same full-universe gold build. cpu 1024 supports 4096 on Fargate.
# DEEPER FOLLOW-UP: per-window bootstrap-next rebuilding the FULL gold every window is redundant
# with the Stage-3 gold-refresh — consider making WindowedBootstrap skip the inline gold build
# (phased-pipeline invariant: no gold per batch) rather than only widening memory.
TASK_DEF_MEDIUM_ARN="$(register_task_definition medium 1024 4096)"
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
    mdm_migrate|mdm_check_connectivity|mdm_verify_graph|mdm_counts|mdm_seed_universe|mdm_seed_from_silver) printf '%s\n' "$TASK_DEF_MDM_SMALL_ARN" ;;
    mdm_run|mdm_backfill_relationships|mdm_sync_graph) printf '%s\n' "$TASK_DEF_MDM_MEDIUM_ARN" ;;
    *) fail "unknown MDM workflow: $1" ;;
  esac
}

workflow_profile() {
  case "$1" in
    daily_incremental) printf '%s\n' "medium" ;;
    bootstrap) printf '%s\n' "medium" ;;
    bootstrap_full) printf '%s\n' "large" ;;
    targeted_resync) printf '%s\n' "large" ;;
    full_reconcile) printf '%s\n' "medium" ;;
    load_daily_form_index_for_date) printf '%s\n' "small" ;;
    catch_up_daily_form_index) printf '%s\n' "small" ;;
    gold_refresh) printf '%s\n' "medium" ;;
    seed_universe) printf '%s\n' "medium" ;;
    *) fail "unknown workflow: $1" ;;
  esac
}

workflow_command_expression() {
  case "$1" in
    daily_incremental) printf '%s\n' "States.Array('daily-incremental', '--run-id', \$\$.Execution.Name)" ;;
    bootstrap) printf '%s\n' "States.Array('bootstrap', '--run-id', \$\$.Execution.Name)" ;;
    bootstrap_full) printf '%s\n' "States.Array('bootstrap-full', '--run-id', \$\$.Execution.Name)" ;;
    targeted_resync) printf '%s\n' "States.Array('targeted-resync', '--scope-type', \$.scope_type, '--scope-key', \$.scope_key, '--run-id', \$\$.Execution.Name)" ;;
    full_reconcile) printf '%s\n' "States.Array('full-reconcile', '--run-id', \$\$.Execution.Name)" ;;
    load_daily_form_index_for_date) printf '%s\n' "States.Array('load-daily-form-index-for-date', \$.target_date, '--run-id', \$\$.Execution.Name)" ;;
    catch_up_daily_form_index) printf '%s\n' "States.Array('catch-up-daily-form-index', '--run-id', \$\$.Execution.Name)" ;;
    gold_refresh) printf '%s\n' "States.Array('gold-refresh', '--run-id', \$\$.Execution.Name)" ;;
    seed_universe) printf '%s\n' "States.Array('seed-universe', '--run-id', \$\$.Execution.Name)" ;;
    *) fail "unknown workflow: $1" ;;
  esac
}

workflow_cik_command_expression() {
  case "$1" in
    daily_incremental) printf '%s\n' "States.Array('daily-incremental', '--run-id', \$\$.Execution.Name, '--cik-list', \$.cik_list)" ;;
    bootstrap) printf '%s\n' "States.Array('bootstrap', '--run-id', \$\$.Execution.Name, '--cik-list', \$.cik_list)" ;;
    bootstrap_full) printf '%s\n' "States.Array('bootstrap-full', '--run-id', \$\$.Execution.Name, '--cik-list', \$.cik_list)" ;;
    *) return 0 ;;
  esac
}

mdm_workflow_command_expression() {
  case "$1" in
    mdm_migrate) printf '%s\n' "States.Array('mdm', 'migrate')" ;;
    mdm_check_connectivity) printf '%s\n' "States.Array('mdm', 'check-connectivity')" ;;
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
    mdm_seed_universe) printf '%s\n' "States.Array('mdm', 'seed-universe', '--tracking-status', '${MDM_SEED_UNIVERSE_TRACKING_STATUS}')" ;;
    mdm_seed_from_silver) printf '%s\n' "States.Array('mdm', 'seed-from-silver', '--tracking-status', '${MDM_SEED_FROM_SILVER_TRACKING_STATUS}')" ;;
    *) fail "unknown MDM workflow: $1" ;;
  esac
}

mdm_workflow_limit_command_expression() {
  case "$1" in
    mdm_run) printf '%s\n' "States.Array('mdm', 'run', '--entity-type', 'all', '--limit', States.Format('{}', $.limit))" ;;
    mdm_backfill_relationships) printf '%s\n' "States.Array('mdm', 'backfill-relationships', '--limit', States.Format('{}', $.limit))" ;;
    mdm_sync_graph) printf '%s\n' "States.Array('mdm', 'sync-graph', '--limit', States.Format('{}', $.limit))" ;;
    mdm_seed_universe) printf '%s\n' "States.Array('mdm', 'seed-universe', '--tracking-status', '${MDM_SEED_UNIVERSE_TRACKING_STATUS}', '--limit', States.Format('{}', $.limit))" ;;
    *) return 0 ;;
  esac
}

mdm_workflow_relationship_command_expression() {
  case "$1" in
    mdm_backfill_relationships) printf '%s\n' "States.Array('mdm', 'derive-relationships', '--relationship-type', $.relationship_type)" ;;
    mdm_sync_graph) printf '%s\n' "States.Array('mdm', 'sync-graph', '--relationship-type', $.relationship_type)" ;;
    *) return 0 ;;
  esac
}

mdm_workflow_relationship_limit_command_expression() {
  case "$1" in
    mdm_backfill_relationships) printf '%s\n' "States.Array('mdm', 'derive-relationships', '--relationship-type', $.relationship_type, '--target-per-type', States.Format('{}', $.limit))" ;;
    mdm_sync_graph) printf '%s\n' "States.Array('mdm', 'sync-graph', '--relationship-type', $.relationship_type, '--limit', States.Format('{}', $.limit))" ;;
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
  local output_file="$1" task_definition_arn="$2" default_command="$3" limit_command="$4" relationship_command="${5:-}" relationship_limit_command="${6:-}"
  python3 - "$output_file" "$CLUSTER_ARN" "$task_definition_arn" "edgar-warehouse" \
    "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" "$default_command" "$limit_command" "$relationship_command" "$relationship_limit_command" <<'PY'
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
    relationship_command,
    relationship_limit_command,
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

if relationship_command and relationship_limit_command:
    definition = {
        "Comment": "Run an EdgarTools MDM workflow on ECS Fargate with optional relationship_type and numeric limit overrides.",
        "StartAt": "HasRelationshipTypeAndLimitOverride",
        "States": {
            "HasRelationshipTypeAndLimitOverride": {
                "Type": "Choice",
                "Choices": [{
                    "And": [
                        {"Variable": "$.relationship_type", "IsPresent": True},
                        {"Variable": "$.relationship_type", "IsString": True},
                        {"Variable": "$.limit", "IsPresent": True},
                        {"Variable": "$.limit", "IsNumeric": True},
                    ],
                    "Next": "RunMdmTaskWithRelationshipTypeAndLimit",
                }],
                "Default": "HasRelationshipTypeOverride",
            },
            "HasRelationshipTypeOverride": {
                "Type": "Choice",
                "Choices": [{
                    "And": [
                        {"Variable": "$.relationship_type", "IsPresent": True},
                        {"Variable": "$.relationship_type", "IsString": True},
                    ],
                    "Next": "RunMdmTaskWithRelationshipType",
                }],
                "Default": "HasLimitOverride",
            },
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
            "RunMdmTaskWithRelationshipType": run_task_state(relationship_command),
            "RunMdmTaskWithRelationshipTypeAndLimit": run_task_state(relationship_limit_command),
        },
    }
elif limit_command:
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
            "ToleratedFailurePercentage": 10,
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

# Phased pipeline: seed → compute windows → sequential windowed bootstrap → MDM chain → gold → run summary.
# Replaces the original DISTRIBUTED Map over cik_batches.jsonl with an INLINE Map (MaxConcurrency=1)
# over cik_windows.jsonl written by compute-windows.  Sequential windows ensure silver.duckdb is
# consistent at each step; MDM + gold run once after all windows complete.
# Implements CHUNK-02 (sequential windowed SM) and CHUNK-04 SM-side (per-window bootstrap-next command).
# Uses direct ECS task states throughout (no nested Step Function executions) so the
# existing sec_platform_runner_step_functions role needs no extra EventBridge permissions.
write_load_history_definition() {
  local output_file="$1"
  local wh_task_small_arn="$2"    # warehouse small  (compute-windows, write-run-summary)
  local wh_task_medium_arn="$3"   # warehouse medium (seed-universe, per-window bootstrap-next/-fundamentals)
  local mdm_task_small_arn="$4"   # mdm small        (mdm verify-graph — lightweight check)
  local mdm_task_medium_arn="$5"  # mdm medium       (mdm seed-universe, run, backfill-relationships, export, sync-graph)
  local wh_task_large_arn="$6"    # warehouse large  (gold-refresh — full-universe DuckDB is multi-GB)

  python3 - "$output_file" "$CLUSTER_ARN" \
    "$wh_task_small_arn" "$wh_task_medium_arn" "$mdm_task_small_arn" "$mdm_task_medium_arn" "$wh_task_large_arn" \
    "edgar-warehouse" "$BRONZE_BUCKET_NAME" "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" \
    "$MDM_RUN_LIMIT" "$MDM_GRAPH_LIMIT" "$MDM_SEED_UNIVERSE_TRACKING_STATUS" <<'PY'
import json, pathlib, sys

(output_file, cluster_arn,
 wh_small_arn, wh_medium_arn, mdm_small_arn, mdm_medium_arn, wh_large_arn,
 container_name, bronze_bucket_name, subnet_json, security_group_json,
 mdm_run_limit, mdm_graph_limit, mdm_seed_universe_tracking_status) = sys.argv[1:]

subnets = json.loads(subnet_json)
security_groups = json.loads(security_group_json)

def ecs_state(task_def_arn, cmd_expr, next_state=None, is_end=False, retry_secs=120):
    s = {
        "Type": "Task",
        "Resource": "arn:aws:states:::ecs:runTask.sync",
        "Parameters": {
            "LaunchType": "FARGATE",
            "Cluster": cluster_arn,
            "TaskDefinition": task_def_arn,
            "PropagateTags": "TASK_DEFINITION",
            "NetworkConfiguration": {"AwsvpcConfiguration": {
                "AssignPublicIp": "ENABLED",
                "SecurityGroups": security_groups,
                "Subnets": subnets,
            }},
            "Overrides": {"ContainerOverrides": [{"Name": container_name, "Command.$": cmd_expr}]},
        },
        "Retry": [{"ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": retry_secs,
                   "BackoffRate": 2.0, "MaxAttempts": 3}],
    }
    if is_end:
        s["End"] = True
    else:
        s["Next"] = next_state
    return s

mdm_limit = str(mdm_run_limit)
graph_limit = str(mdm_graph_limit)

# (1) SeedUniverse: warehouse reference/window seed ONLY — direct-SEC company_tickers.json
# capture + CIK batch/window bookkeeping (sec_company_ticker, cik_batches.jsonl). Does NOT
# touch MDM (data-architecture Issue 2: this state's old comment claimed it "enrols CIKs
# into MDM", which was never true — it calls warehouse `seed-universe`, not
# `mdm seed-universe`). MDM enrollment is the next state, MdmSeedUniverse.
seed = ecs_state(wh_medium_arn,
    "States.Array('seed-universe', '--run-id', $$.Execution.Name)",
    next_state="MdmSeedUniverse", retry_secs=60)
# ResultPath: null passes the original SM input (e.g. {"window_size": 25}) unchanged to the
# next state.  Without this, the ECS runTask.sync result object would replace the entire input,
# destroying $.window_size before WindowSizeCheck can read it (D-15 bug).
seed["ResultPath"] = None

# (1b) MdmSeedUniverse: MDM tracked-universe seed — upserts mdm_entity/mdm_company from
# edgartools ticker data (data-architecture Issue 2). Without this step a fresh environment
# has no deterministic path from empty MDM tables to a runnable load_history: ComputeWindows
# queries MDM directly and would silently compute zero windows. Idempotent (upsert), so safe
# to run on every execution, not just the first. tracking_status matches the value the
# standalone mdm_seed_universe utility workflow uses (MDM_SEED_UNIVERSE_TRACKING_STATUS) —
# ComputeWindows/bootstrap-next/bootstrap-fundamentals below all query
# tracking_status IN ('active','bootstrap_pending') so it doesn't matter which of the two a
# newly-seeded company lands in for THIS pipeline to pick it up.
mdm_seed_universe = ecs_state(mdm_medium_arn,
    f"States.Array('mdm', 'seed-universe', '--tracking-status', '{mdm_seed_universe_tracking_status}')",
    next_state="WindowSizeCheck", retry_secs=60)
mdm_seed_universe["ResultPath"] = None

# (2) WindowSizeCheck → WindowSizeDefault → TotalCikLimitCheck → TotalCikLimitDefault → ComputeWindows
# D-15 backward-compat: SM input {} is valid because WindowSizeDefault injects window_size=500
# when the caller omits it.  The Choice state routes:
#   - $.window_size IS_PRESENT (caller supplied a value) → skip default, go to TotalCikLimitCheck
#   - $.window_size absent (e.g. input was {}) → WindowSizeDefault injects the integer 500
#     at $.window_size via ResultPath, then falls through to TotalCikLimitCheck
window_size_check = {
    "Type": "Choice",
    "Comment": "Route to TotalCikLimitCheck directly when caller supplied window_size; otherwise inject the default.",
    "Choices": [
        {
            "Variable": "$.window_size",
            "IsPresent": True,
            "Next": "TotalCikLimitCheck",
        }
    ],
    "Default": "WindowSizeDefault",
}

# Pass state: writes integer 500 directly to $.window_size (Result is a scalar, not a dict,
# so ResultPath merges it in-place — downstream sees $.window_size = 500, not $.window_size = {}).
window_size_default = {
    "Type": "Pass",
    "Comment": "Inject default window_size=500 when caller passed {} or omitted the key. "
               "Result is a bare integer; ResultPath $.window_size writes it directly so "
               "$.window_size = 500 (not {\"window_size\": 500}) for ComputeWindows.",
    "Result": 500,
    "ResultPath": "$.window_size",
    "Next": "TotalCikLimitCheck",
}

# (2b) TotalCikLimitCheck → TotalCikLimitDefault → ComputeWindows
# Same backward-compat pattern as WindowSizeCheck/Default above (D-15), for an optional
# $.total_cik_limit SM input field. Added to give load_history a real CIK-scoping bound at
# trigger time (fix-pipelines 06-03 Rule 4 finding: previously the ONLY exposed bound was
# window_size, which chunks the full tracking_status IN ('active','bootstrap_pending')
# universe rather than capping it — every run processed the entire tracked universe
# regardless of window_size). $.total_cik_limit IS_PRESENT (caller supplied a value, e.g.
# {"total_cik_limit": 150} for a bounded investigative sample) routes straight to
# ComputeWindows; absent → TotalCikLimitDefault injects the sentinel 0, which
# compute-windows' CLI/orchestrator treat as "no limit" (unbounded, full-universe — the
# pre-existing default behavior every caller of `--input '{}'` already relies on).
total_cik_limit_check = {
    "Type": "Choice",
    "Comment": "Route to ComputeWindows directly when caller supplied total_cik_limit; otherwise inject the no-limit default.",
    "Choices": [
        {
            "Variable": "$.total_cik_limit",
            "IsPresent": True,
            "Next": "ComputeWindows",
        }
    ],
    "Default": "TotalCikLimitDefault",
}

# Pass state: writes integer 0 (the "no limit" sentinel — compute-windows treats
# total_cik_limit in (None, "", 0, "0") as unbounded) directly to $.total_cik_limit.
total_cik_limit_default = {
    "Type": "Pass",
    "Comment": "Inject the no-limit sentinel 0 when caller passed {} or omitted total_cik_limit, "
               "preserving pre-existing full-universe behavior for every caller that doesn't "
               "opt into CIK-scoping.",
    "Result": 0,
    "ResultPath": "$.total_cik_limit",
    "Next": "ComputeWindows",
}

# (3) ComputeWindows: queries MDM for CIKs eligible for this run and writes
# cik_windows.jsonl + cik_snapshot.jsonl. tracking_status IN ('active','bootstrap_pending') —
# NOT 'active' alone (data-architecture Issue 2). A CIK is 'bootstrap_pending' until its first
# full submissions bootstrap completes, then bootstrap-next promotes it to 'active'
# (warehouse_orchestrator._sync_mdm_tracking_status). Filtering ComputeWindows to 'active' only
# would compute zero windows for every freshly-seeded environment, since nothing is 'active' yet.
# --window-size uses States.Format to coerce the integer $.window_size to a string for argv.
# --total-cik-limit (optional CIK-scoping bound, see TotalCikLimitCheck/Default above) is always
# passed explicitly (0 = no limit) since WindowSizeCheck/TotalCikLimitCheck guarantee both
# $.window_size and $.total_cik_limit are present by the time this state runs.
compute_windows = ecs_state(wh_medium_arn,
    "States.Array('compute-windows', '--window-size', States.Format('{}', $.window_size), '--total-cik-limit', States.Format('{}', $.total_cik_limit), '--run-id', $$.Execution.Name)",
    next_state="Stage1Parallel")

# (4) Stage1Parallel: Branch A ownership bootstrap. Branch B fundamentals is
# intentionally sequenced after this state because all Branch B modes now write
# the same canonical SEC silver DuckDB database as Branch A. Running two ECS
# tasks against the same S3-backed DuckDB artifact would race the hydrate/publish
# round trip and could drop whichever task published second.
#
# (4a) Branch A — WindowedBootstrap DISTRIBUTED Map.
# Per-window command: bootstrap-next --cik-limit M --cik-offset N --run-id <execution-name>.
# --tracking-status-filter is explicit here (bootstrap-next's own CLI default is
# 'bootstrap_pending' alone, for its OTHER standalone/ad-hoc use — process the pending backlog).
# Within load_history it must match ComputeWindows' filter exactly, or window offsets computed
# against one CIK list get applied to a different list bootstrap-next resolves independently.
# Terminal within Branch A's sub-state-machine (End=True), strict failure policy (ToleratedFailurePercentage=0).
#
# Mode is DISTRIBUTED, not INLINE (fix-pipelines 06-03): AWS Step Functions rejects
# ItemReader on an INLINE Map ("The ItemReader, ItemBatcher and ResultWriter fields are
# not supported for INLINE maps", States.Runtime) — ItemReader (reading cik_windows.jsonl
# from S3) requires Mode=DISTRIBUTED. This was undiscovered until 06-03's first-ever dev
# load_history execution (06-02: "zero prior dev executions") failed with exactly that
# error at WindowedBootstrap. MaxConcurrency=1 still enforces one window at a time under
# DISTRIBUTED mode (each item runs as its own STANDARD child execution, at most 1
# concurrently). Matches the already-working DISTRIBUTED pattern used by
# write_ownership_mdm_gold_definition's batch_map (Mode: DISTRIBUTED, ExecutionType:
# STANDARD) elsewhere in this script.
per_window = ecs_state(wh_medium_arn,
    "States.Array('bootstrap-next', '--cik-limit', States.Format('{}', $.window_limit), '--cik-offset', States.Format('{}', $.window_offset), '--tracking-status-filter', 'active,bootstrap_pending', '--run-id', $$.Execution.Name)",
    is_end=True)

windowed_bootstrap = {
    "Type": "Map",
    "Comment": "Branch A ownership bootstrap (MaxConcurrency=1): one window at a time so silver/ownership/ is consistent.",
    "MaxConcurrency": 1,
    "ToleratedFailurePercentage": 0,
    "ItemReader": {
        "Resource": "arn:aws:states:::s3:getObject",
        "ReaderConfig": {"InputType": "JSONL", "MaxItems": 100000},
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_windows.jsonl', $$.Execution.Name)",
        },
    },
    "ItemProcessor": {
        "ProcessorConfig": {
            "Mode": "DISTRIBUTED",
            "ExecutionType": "STANDARD",
        },
        "StartAt": "RunWindow",
        "States": {"RunWindow": per_window},
    },
    "ResultPath": None,
    "End": True,
}

# (4b) Branch B entity-facts. No --cik-list is passed: the Map
# item carries only offset/limit, and bootstrap-fundamentals resolves the actual CIK slice from
# the same MDM universe/order/status-filter Branch A uses (see ISSUE-2 status-filter note above),
# so Branch A and Branch B process identical CIK windows for the same {window_offset,
# window_limit} item.
#
# AD-13: partial Branch B failure is accepted. A failure is caught and routed to
# Stage1BPerFiling so the pipeline proceeds. Gaps self-heal via idempotent
# backfill; a hard abort would defeat that. Branch A remains strict.
stage1b_entity_facts_catch = [{
    "ErrorEquals": ["States.ALL"],
    "ResultPath": None,
    "Next": "Stage1BPerFiling",
}]

per_window_fundamentals_entity_facts = ecs_state(wh_medium_arn,
    "States.Array('bootstrap-fundamentals', '--mode', 'entity-facts', '--cik-offset', States.Format('{}', $.window_offset), '--cik-limit', States.Format('{}', $.window_limit), '--run-id', $$.Execution.Name)",
    is_end=True)

fundamentals_entity_facts = {
    "Type": "Map",
    "Comment": "Branch B entity-facts: SEC companyfacts XBRL -> sec_financial_fact, sec_financial_derived, sec_accounting_flag in unified SEC silver. Runs after Branch A to avoid concurrent writes to the same DuckDB artifact.",
    "MaxConcurrency": 1,
    "ToleratedFailurePercentage": 0,
    "ItemReader": {
        "Resource": "arn:aws:states:::s3:getObject",
        "ReaderConfig": {"InputType": "JSONL", "MaxItems": 100000},
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_windows.jsonl', $$.Execution.Name)",
        },
    },
    "ItemProcessor": {
        # DISTRIBUTED, not INLINE — see the WindowedBootstrap comment above (fix-pipelines
        # 06-03): ItemReader requires Mode=DISTRIBUTED, not INLINE.
        "ProcessorConfig": {"Mode": "DISTRIBUTED", "ExecutionType": "STANDARD"},
        "StartAt": "RunFundamentalsEntityFacts",
        "States": {"RunFundamentalsEntityFacts": per_window_fundamentals_entity_facts},
    },
    "ResultPath": None,
    "Catch": stage1b_entity_facts_catch,
    "Next": "Stage1BPerFiling",
}

stage1_parallel = {
    "Type": "Parallel",
    "Comment": (
        "Stage 1 ownership bootstrap. Branch B fundamentals writes the same unified SEC silver "
        "database, so all bootstrap-fundamentals modes run sequentially after Branch A. Branch A "
        "is strict; Branch B stages catch failures so the pipeline can still advance (AD-13)."
    ),
    "Branches": [
        {
            "StartAt": "WindowedBootstrap",
            "States": {"WindowedBootstrap": windowed_bootstrap},
        },
    ],
    "ResultPath": None,
    "Next": "Stage1BEntityFacts",
}

# (4c) Stage1BPerFiling / Stage1BThirteenF: Branch B modes that read Branch A's filing/attachment/
# raw-object metadata (data-architecture Issues 1 and 4). Run sequentially after Branch A and
# entity-facts because all Branch B modes write the same unified SEC silver DuckDB file.
#
# AD-13 applies here too: a Catch on either stage skips to the next step (not a hard abort) so a
# transient Branch B failure never blocks MDM/gold for the (strict, already-complete) Branch A data.
stage1b_per_filing_catch = [{
    "ErrorEquals": ["States.ALL"],
    "ResultPath": None,
    "Next": "Stage1BThirteenF",
}]
stage1b_thirteenf_catch = [{
    "ErrorEquals": ["States.ALL"],
    "ResultPath": None,
    "Next": "MdmRun",
}]

per_window_fundamentals_per_filing = ecs_state(wh_medium_arn,
    "States.Array('bootstrap-fundamentals', '--mode', 'per-filing', '--cik-offset', States.Format('{}', $.window_offset), '--cik-limit', States.Format('{}', $.window_limit), '--run-id', $$.Execution.Name)",
    is_end=True)

fundamentals_per_filing = {
    "Type": "Map",
    "Comment": "Branch B per-filing (post-Branch-A): 8-K earnings + DEF 14A proxy -> sec_earnings_release, sec_executive_record in unified SEC silver. Reads filing/attachment/raw-object metadata Branch A just finished writing.",
    "MaxConcurrency": 1,
    "ToleratedFailurePercentage": 0,
    "ItemReader": {
        "Resource": "arn:aws:states:::s3:getObject",
        "ReaderConfig": {"InputType": "JSONL", "MaxItems": 100000},
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_windows.jsonl', $$.Execution.Name)",
        },
    },
    "ItemProcessor": {
        # DISTRIBUTED, not INLINE — see the WindowedBootstrap comment above (fix-pipelines
        # 06-03): ItemReader requires Mode=DISTRIBUTED, not INLINE.
        "ProcessorConfig": {"Mode": "DISTRIBUTED", "ExecutionType": "STANDARD"},
        "StartAt": "RunFundamentalsPerFiling",
        "States": {"RunFundamentalsPerFiling": per_window_fundamentals_per_filing},
    },
    "ResultPath": None,
    "Catch": stage1b_per_filing_catch,
    "Next": "Stage1BThirteenF",
}

per_window_fundamentals_thirteenf = ecs_state(wh_medium_arn,
    "States.Array('bootstrap-fundamentals', '--mode', 'thirteenf', '--cik-offset', States.Format('{}', $.window_offset), '--cik-limit', States.Format('{}', $.window_limit), '--run-id', $$.Execution.Name)",
    is_end=True)

fundamentals_thirteenf = {
    "Type": "Map",
    "Comment": "Branch B 13F (post-Branch-A, data-architecture Issue 4): INFORMATION TABLE XML -> sec_thirteenf_holding in unified SEC silver. Same Branch A dependency as per-filing; runs after it in this same sequential stage.",
    "MaxConcurrency": 1,
    "ToleratedFailurePercentage": 0,
    "ItemReader": {
        "Resource": "arn:aws:states:::s3:getObject",
        "ReaderConfig": {"InputType": "JSONL", "MaxItems": 100000},
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_windows.jsonl', $$.Execution.Name)",
        },
    },
    "ItemProcessor": {
        # DISTRIBUTED, not INLINE — see the WindowedBootstrap comment above (fix-pipelines
        # 06-03): ItemReader requires Mode=DISTRIBUTED, not INLINE.
        "ProcessorConfig": {"Mode": "DISTRIBUTED", "ExecutionType": "STANDARD"},
        "StartAt": "RunFundamentalsThirteenF",
        "States": {"RunFundamentalsThirteenF": per_window_fundamentals_thirteenf},
    },
    "ResultPath": None,
    "Catch": stage1b_thirteenf_catch,
    "Next": "MdmRun",
}

# (5)–(9) MDM chain + GoldRefresh — run once after ALL windows complete (same invariant as before).
# MdmExport is new (data-architecture Issue 3): mdm sync-graph materializes Snowflake graph
# tables from the Snowflake MDM mirror, not from the runtime MDM database directly. Without an
# export between backfill-relationships and sync-graph, sync-graph can read a stale or missing
# mirror — graph output wouldn't reflect the MDM run this same execution just did.
mdm_run = ecs_state(mdm_medium_arn,
    f"States.Array('mdm', 'run', '--entity-type', 'all', '--limit', '{mdm_limit}')",
    next_state="MdmBackfill")
mdm_backfill = ecs_state(mdm_medium_arn,
    f"States.Array('mdm', 'backfill-relationships', '--limit', '{graph_limit}')",
    next_state="MdmExport")
mdm_export = ecs_state(mdm_medium_arn,
    "States.Array('mdm', 'export')",
    next_state="MdmSync")
mdm_sync = ecs_state(mdm_medium_arn,
    f"States.Array('mdm', 'sync-graph', '--limit', '{graph_limit}')",
    next_state="MdmVerify")
mdm_verify = ecs_state(mdm_small_arn,
    "States.Array('mdm', 'verify-graph')",
    next_state="GoldRefresh")
mdm_verify["Catch"] = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "GoldRefresh"}]
# verify-graph is validation-only per docs/data-architecture.md: it reports
# parity but must never block gold-refresh, so a verify failure falls through.
gold = ecs_state(wh_large_arn,
    "States.Array('gold-refresh', '--run-id', $$.Execution.Name)",
    next_state="WriteRunSummary", retry_secs=60)

# (9) WriteRunSummary: terminal task that reads cik_windows.jsonl + cik_snapshot.jsonl from S3
# to derive window_count and cik_count, then writes run-summary.json.
# Uses --from-windows-key so the command resolves counts from S3 manifests; the SM does NOT
# carry $.WindowCount / $.CikCount through state (those values live only in the S3 manifests).
write_run_summary = ecs_state(wh_medium_arn,
    "States.Array('write-run-summary', '--run-id', $$.Execution.Name, '--from-windows-key', States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_windows.jsonl', $$.Execution.Name))",
    is_end=True)

definition = {
    "Comment": (
        "Phased bootstrap: (1) seed warehouse reference data, (1b) seed MDM tracked universe "
        "(mdm seed-universe — data-architecture Issue 2), (2) inject window_size default if "
        "absent, (3) compute CIK windows for tracking_status active-or-bootstrap_pending + write "
        "manifests to S3, "
        "(4) Stage1Parallel — Branch A ownership (bootstrap-next) writes unified SEC silver, "
        "(4b) Stage1BEntityFacts then (4c) Stage1BPerFiling then Stage1BThirteenF — Branch B "
        "fundamentals modes run sequentially after Branch A because they share the same silver "
        "DuckDB artifact; Branch B failures are caught so the pipeline still advances (AD-13), "
        "(5) MDM entity resolution + export to Snowflake mirror + Neo4j sync in bulk "
        "(data-architecture Issue 3: export precedes sync-graph so graph reflects this run), "
        "(6) single gold build + Snowflake export manifest, "
        "(7) write run-summary.json with window_count and cik_count from S3 manifests. "
        "Implements CHUNK-02 (sequential windowed SM) and CHUNK-04 SM-side."
    ),
    "StartAt": "SeedUniverse",
    "States": {
        "SeedUniverse":      seed,
        "MdmSeedUniverse":   mdm_seed_universe,
        "WindowSizeCheck":   window_size_check,
        "WindowSizeDefault": window_size_default,
        "TotalCikLimitCheck":   total_cik_limit_check,
        "TotalCikLimitDefault": total_cik_limit_default,
        "ComputeWindows":    compute_windows,
        "Stage1Parallel":    stage1_parallel,
        "Stage1BEntityFacts": fundamentals_entity_facts,
        "Stage1BPerFiling":  fundamentals_per_filing,
        "Stage1BThirteenF":  fundamentals_thirteenf,
        "MdmRun":            mdm_run,
        "MdmBackfill":       mdm_backfill,
        "MdmExport":         mdm_export,
        "MdmSync":           mdm_sync,
        "MdmVerify":         mdm_verify,
        "GoldRefresh":       gold,
        "WriteRunSummary":   write_run_summary,
    },
}
pathlib.Path(output_file).write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
PY
}

# Full pipeline for a single warehouse command followed by the MDM chain and gold refresh.
# Shape: RunWarehouseTask → MdmRun → MdmBackfill → MdmSync → MdmVerify → GoldRefresh
# Used by bootstrap and daily_incremental.
write_warehouse_mdm_gold_definition() {
  local output_file="$1"
  local wh_task_medium_arn="$2"   # warehouse medium (the bronze/silver command)
  local mdm_task_small_arn="$3"   # mdm small  (verify-graph)
  local mdm_task_medium_arn="$4"  # mdm medium (run, backfill, sync)
  local wh_task_large_arn="$5"    # warehouse large (gold-refresh)
  local workflow_name="$6"        # e.g. bootstrap or daily_incremental

  python3 - "$output_file" "$CLUSTER_ARN" \
    "$wh_task_medium_arn" "$mdm_task_small_arn" "$mdm_task_medium_arn" "$wh_task_large_arn" \
    "edgar-warehouse" "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" \
    "$MDM_RUN_LIMIT" "$MDM_GRAPH_LIMIT" "$workflow_name" <<'PY'
import json, pathlib, sys

(output_file, cluster_arn,
 wh_medium_arn, mdm_small_arn, mdm_medium_arn, wh_large_arn,
 container_name, subnet_json, security_group_json,
 mdm_run_limit, mdm_graph_limit, workflow_name) = sys.argv[1:]

subnets = json.loads(subnet_json)
security_groups = json.loads(security_group_json)
mdm_limit   = str(mdm_run_limit)
graph_limit = str(mdm_graph_limit)

WAREHOUSE_COMMANDS = {
    "bootstrap": "bootstrap",
    "daily_incremental":   "daily-incremental",
}
wh_cmd = WAREHOUSE_COMMANDS[workflow_name]

def ecs_state(task_def_arn, cmd_expr, next_state=None, is_end=False, retry_secs=120):
    s = {
        "Type": "Task",
        "Resource": "arn:aws:states:::ecs:runTask.sync",
        "Parameters": {
            "LaunchType": "FARGATE",
            "Cluster": cluster_arn,
            "TaskDefinition": task_def_arn,
            "PropagateTags": "TASK_DEFINITION",
            "NetworkConfiguration": {"AwsvpcConfiguration": {
                "AssignPublicIp": "ENABLED",
                "SecurityGroups": security_groups,
                "Subnets": subnets,
            }},
            "Overrides": {"ContainerOverrides": [{"Name": container_name, "Command.$": cmd_expr}]},
        },
        "Retry": [{"ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": retry_secs,
                   "BackoffRate": 2.0, "MaxAttempts": 3}],
    }
    if is_end:
        s["End"] = True
    else:
        s["Next"] = next_state
    return s

run_wh = ecs_state(wh_medium_arn,
    f"States.Array('{wh_cmd}', '--run-id', $$.Execution.Name)",
    next_state="MdmRun")
mdm_run = ecs_state(mdm_medium_arn,
    f"States.Array('mdm', 'run', '--entity-type', 'all', '--limit', '{mdm_limit}')",
    next_state="MdmBackfill")
mdm_backfill = ecs_state(mdm_medium_arn,
    f"States.Array('mdm', 'backfill-relationships', '--limit', '{graph_limit}')",
    next_state="MdmExport")
# MdmExport precedes MdmSync (data-architecture Issue 3): sync-graph materializes Snowflake
# graph tables from the Snowflake MDM mirror, not the runtime MDM database directly — without
# an export here the mirror can be stale relative to the run/backfill that just completed.
mdm_export = ecs_state(mdm_medium_arn,
    "States.Array('mdm', 'export')",
    next_state="MdmSync")
mdm_sync = ecs_state(mdm_medium_arn,
    f"States.Array('mdm', 'sync-graph', '--limit', '{graph_limit}')",
    next_state="MdmVerify")
mdm_verify = ecs_state(mdm_small_arn,
    "States.Array('mdm', 'verify-graph')",
    next_state="GoldRefresh")
mdm_verify["Catch"] = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "GoldRefresh"}]
# verify-graph is validation-only per docs/data-architecture.md: it reports
# parity but must never block gold-refresh, so a verify failure falls through.
gold = ecs_state(wh_large_arn,
    "States.Array('gold-refresh', '--run-id', $$.Execution.Name)",
    is_end=True, retry_secs=60)

display = workflow_name.replace("_", " ").title()

# All workflows except daily_incremental seed the universe first so any
# bootstrap_pending CIKs are enrolled before the main pipeline step runs.
if workflow_name != "daily_incremental":
    seed_universe = ecs_state(wh_medium_arn,
        "States.Array('seed-universe', '--run-id', $$.Execution.Name)",
        next_state="RunWarehouseTask", retry_secs=60)
    definition = {
        "Comment": (
            f"{display}: (0) seed universe, (1) bronze+silver capture, "
            "(2) MDM entity resolution + Neo4j sync, (3) gold build + Snowflake export manifest."
        ),
        "StartAt": "SeedUniverse",
        "States": {
            "SeedUniverse":     seed_universe,
            "RunWarehouseTask": run_wh,
            "MdmRun":           mdm_run,
            "MdmBackfill":      mdm_backfill,
            "MdmExport":        mdm_export,
            "MdmSync":          mdm_sync,
            "MdmVerify":        mdm_verify,
            "GoldRefresh":      gold,
        },
    }
else:
    definition = {
        "Comment": (
            f"{display}: (1) bronze+silver capture, (2) MDM entity resolution + Neo4j sync, "
            "(3) gold build + Snowflake export manifest."
        ),
        "StartAt": "RunWarehouseTask",
        "States": {
            "RunWarehouseTask": run_wh,
            "MdmRun":           mdm_run,
            "MdmBackfill":      mdm_backfill,
            "MdmExport":        mdm_export,
            "MdmSync":          mdm_sync,
            "MdmVerify":        mdm_verify,
            "GoldRefresh":      gold,
        },
    }
pathlib.Path(output_file).write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
PY
}

# Re-process pipeline for already-loaded bronze:
#   seed-silver-batches → parallel bootstrap-batch (uses cached bronze) → MDM chain → gold-refresh.
# Use when bronze is already in S3 but silver/MDM/Neo4j/Snowflake need refreshing.
# Accepts optional input: {"tracking_status_filter": "all|active|bootstrap_pending"}
write_silver_mdm_gold_definition() {
  local output_file="$1"
  local wh_task_medium_arn="$2"  # warehouse medium (seed-silver-batches, bootstrap-batch)
  local mdm_task_small_arn="$3"  # mdm small   (mdm verify-graph)
  local mdm_task_medium_arn="$4" # mdm medium  (mdm run, backfill, sync)
  local wh_task_large_arn="$5"   # warehouse large (gold-refresh)

  python3 - "$output_file" "$CLUSTER_ARN" \
    "$wh_task_medium_arn" "$mdm_task_small_arn" "$mdm_task_medium_arn" "$wh_task_large_arn" \
    "edgar-warehouse" "$BRONZE_BUCKET_NAME" "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" \
    "$BOOTSTRAP_BATCH_CONCURRENCY" "$MDM_RUN_LIMIT" "$MDM_GRAPH_LIMIT" <<'PY'
import json, pathlib, sys

(output_file, cluster_arn,
 wh_medium_arn, mdm_small_arn, mdm_medium_arn, wh_large_arn,
 container_name, bronze_bucket_name, subnet_json, security_group_json,
 batch_concurrency, mdm_run_limit, mdm_graph_limit) = sys.argv[1:]

subnets = json.loads(subnet_json)
security_groups = json.loads(security_group_json)

def ecs_state(task_def_arn, cmd_expr, next_state=None, is_end=False, retry_secs=120):
    s = {
        "Type": "Task",
        "Resource": "arn:aws:states:::ecs:runTask.sync",
        "Parameters": {
            "LaunchType": "FARGATE",
            "Cluster": cluster_arn,
            "TaskDefinition": task_def_arn,
            "PropagateTags": "TASK_DEFINITION",
            "NetworkConfiguration": {"AwsvpcConfiguration": {
                "AssignPublicIp": "ENABLED",
                "SecurityGroups": security_groups,
                "Subnets": subnets,
            }},
            "Overrides": {"ContainerOverrides": [{"Name": container_name, "Command.$": cmd_expr}]},
        },
        "Retry": [{"ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": retry_secs,
                   "BackoffRate": 2.0, "MaxAttempts": 3}],
    }
    if is_end:
        s["End"] = True
    else:
        s["Next"] = next_state
    return s

mdm_limit   = str(mdm_run_limit)
graph_limit = str(mdm_graph_limit)

# seed-silver-batches reads CIKs from silver DuckDB (no SEC API calls) and writes the same
# cik_batches.jsonl format that bootstrap-batch expects. tracking_status_filter is passed
# from the SM execution input (default "all" when not provided in trigger input).
seed = ecs_state(wh_medium_arn,
    "States.Array('seed-silver-batches', '--run-id', $$.Execution.Name, '--tracking-status-filter', $.tracking_status_filter)",
    next_state="BatchSilver", retry_secs=60)

# INVARIANT: silver_mdm_gold must make ZERO SEC API calls and must not fan out
# parser work inside each BatchSilver chunk. --artifact-policy skip prevents
# ownership XML fetches; --parser-policy skip prevents each chunk from
# re-parsing the full configured-form corpus. Run artifact fetch/parse as a
# separate targeted pipeline after silver_mdm_gold completes when ownership
# artifacts are needed.
batch = ecs_state(wh_medium_arn,
    "States.Array('bootstrap-batch', '--cik-list', $.cik_list, '--artifact-policy', 'skip', '--parser-policy', 'skip', '--run-id', $$.Execution.Name)",
    is_end=True)

batch_map = {
    "Type": "Map",
    "MaxConcurrency": int(batch_concurrency),
    "Comment": "Re-process silver + artifacts from cached bronze. Submissions not re-downloaded.",
    "ToleratedFailurePercentage": 0,
    "ItemReader": {
        "Resource": "arn:aws:states:::s3:getObject",
        "ReaderConfig": {"InputType": "JSONL", "MaxItems": 100000},
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_batches.jsonl', $$.Execution.Name)",
        },
    },
    "ItemProcessor": {
        "ProcessorConfig": {"Mode": "DISTRIBUTED", "ExecutionType": "STANDARD"},
        "StartAt": "RunBatch",
        "States": {"RunBatch": batch},
    },
    "ResultPath": None,
    "Next": "MdmRun",
}

# INVARIANT: No --limit on MDM commands here. silver_mdm_gold is always a full bulk
# re-run (all companies in silver), not an incremental daily update. A hard limit would
# silently leave the majority of companies unprocessed in MDM and Neo4j.
# MDM_RUN_LIMIT (incremental default 100) is intentionally NOT used here.
mdm_run      = ecs_state(mdm_medium_arn, "States.Array('mdm', 'run', '--entity-type', 'all')", next_state="MdmBackfill")
mdm_backfill = ecs_state(mdm_medium_arn, "States.Array('mdm', 'backfill-relationships')", next_state="MdmExport")
# MdmExport precedes MdmSync (data-architecture Issue 3) — see write_load_history_definition.
mdm_export   = ecs_state(mdm_medium_arn, "States.Array('mdm', 'export')", next_state="MdmSync")
mdm_sync     = ecs_state(mdm_medium_arn, "States.Array('mdm', 'sync-graph')", next_state="MdmVerify")
mdm_verify   = ecs_state(mdm_small_arn,  "States.Array('mdm', 'verify-graph')", next_state="GoldRefresh")
mdm_verify["Catch"] = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "GoldRefresh"}]
# verify-graph is validation-only per docs/data-architecture.md: it reports
# parity but must never block gold-refresh, so a verify failure falls through.
gold         = ecs_state(wh_large_arn,   "States.Array('gold-refresh', '--run-id', $$.Execution.Name)", is_end=True, retry_secs=60)

seed_universe = ecs_state(wh_medium_arn,
    "States.Array('seed-universe', '--run-id', $$.Execution.Name)",
    next_state="SeedSilverBatches", retry_secs=60)

definition = {
    "Comment": (
        "Re-process pipeline for already-loaded bronze: "
        "(0) seed universe (enrol any bootstrap_pending CIKs), "
        "(1) seed batch file from silver DuckDB (no SEC downloads), "
        "(2) parallel bootstrap-batch uses bronze SHA256 cache for submissions + runs artifact pipeline, "
        "(3) MDM entity resolution + Neo4j sync, "
        "(4) gold build + Snowflake export manifest. "
        "Trigger with: {} or {\"tracking_status_filter\": \"active|bootstrap_pending\"}"
    ),
    "StartAt": "SeedUniverse",
    "States": {
        "SeedUniverse":     seed_universe,
        "SeedSilverBatches": seed,
        "BatchSilver":  batch_map,
        "MdmRun":       mdm_run,
        "MdmBackfill":  mdm_backfill,
        "MdmExport":    mdm_export,
        "MdmSync":      mdm_sync,
        "MdmVerify":    mdm_verify,
        "GoldRefresh":  gold,
    },
}
pathlib.Path(output_file).write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
PY
}

# One-click cold-start/recovery pipeline for an existing bronze snapshot:
#   seed-bronze-batches (lists CIKs from S3 bronze directly) → sequential bootstrap-batch
#   (uses cached bronze, zero SEC calls) → MDM chain → gold-refresh.
# Use when an environment's bronze was copied in from elsewhere (e.g. dev → prod via
# `aws s3 sync`) and silver/MDM/Neo4j/Snowflake have never been built from it — unlike
# silver_mdm_gold, this does NOT depend on silver DuckDB's own bookkeeping tables
# (sec_company_sync_state), which are empty in that scenario. No execution input required.
write_bronze_seed_silver_gold_definition() {
  local output_file="$1"
  local wh_task_medium_arn="$2"  # warehouse medium (seed-bronze-batches, bootstrap-batch)
  local mdm_task_small_arn="$3"  # mdm small   (mdm verify-graph)
  local mdm_task_medium_arn="$4" # mdm medium  (mdm run, backfill, sync)
  local wh_task_large_arn="$5"   # warehouse large (gold-refresh)

  python3 - "$output_file" "$CLUSTER_ARN" \
    "$wh_task_medium_arn" "$mdm_task_small_arn" "$mdm_task_medium_arn" "$wh_task_large_arn" \
    "edgar-warehouse" "$BRONZE_BUCKET_NAME" "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" \
    "$BOOTSTRAP_BATCH_CONCURRENCY" "$MDM_RUN_LIMIT" "$MDM_GRAPH_LIMIT" <<'PY'
import json, pathlib, sys

(output_file, cluster_arn,
 wh_medium_arn, mdm_small_arn, mdm_medium_arn, wh_large_arn,
 container_name, bronze_bucket_name, subnet_json, security_group_json,
 batch_concurrency, mdm_run_limit, mdm_graph_limit) = sys.argv[1:]

subnets = json.loads(subnet_json)
security_groups = json.loads(security_group_json)

def ecs_state(task_def_arn, cmd_expr, next_state=None, is_end=False, retry_secs=120):
    s = {
        "Type": "Task",
        "Resource": "arn:aws:states:::ecs:runTask.sync",
        "Parameters": {
            "LaunchType": "FARGATE",
            "Cluster": cluster_arn,
            "TaskDefinition": task_def_arn,
            "PropagateTags": "TASK_DEFINITION",
            "NetworkConfiguration": {"AwsvpcConfiguration": {
                "AssignPublicIp": "ENABLED",
                "SecurityGroups": security_groups,
                "Subnets": subnets,
            }},
            "Overrides": {"ContainerOverrides": [{"Name": container_name, "Command.$": cmd_expr}]},
        },
        "Retry": [{"ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": retry_secs,
                   "BackoffRate": 2.0, "MaxAttempts": 3}],
    }
    if is_end:
        s["End"] = True
    else:
        s["Next"] = next_state
    return s

mdm_limit   = str(mdm_run_limit)
graph_limit = str(mdm_graph_limit)

# seed-bronze-batches lists CIKs straight from S3 bronze (submissions/sec/cik={cik}/...) —
# no SEC API calls, no dependency on silver's own bookkeeping tables. Writes the same
# cik_batches.jsonl format bootstrap-batch expects, so BatchSilver below is unchanged
# from silver_mdm_gold's.
batch_size_check = {
    "Type": "Choice",
    "Comment": "Route to SeedFromBronze directly when caller supplied batch_size; otherwise inject the default.",
    "Choices": [{
        "Variable": "$.batch_size",
        "IsPresent": True,
        "Next": "SeedFromBronze",
    }],
    "Default": "BatchSizeDefault",
}

batch_size_default = {
    "Type": "Pass",
    "Comment": "Inject default batch_size=100 when caller passed {} or omitted the key.",
    "Result": 100,
    "ResultPath": "$.batch_size",
    "Next": "SeedFromBronze",
}

seed_from_bronze = ecs_state(wh_medium_arn,
    "States.Array('seed-bronze-batches', '--run-id', $$.Execution.Name, '--batch-size', States.Format('{}', $.batch_size))",
    next_state="BatchSilver", retry_secs=60)

# INVARIANT: bronze_seed_silver_gold must make ZERO SEC API calls and must not
# fan out parser work inside each BatchSilver chunk. --artifact-policy skip
# prevents ownership XML fetches; --parser-policy skip prevents each chunk from
# re-parsing the full configured-form corpus. Parse cached artifacts later
# through a targeted operator run if ownership tables need refresh.
batch = ecs_state(wh_medium_arn,
    "States.Array('bootstrap-batch', '--cik-list', $.cik_list, '--artifact-policy', 'skip', '--parser-policy', 'skip', '--run-id', $$.Execution.Name)",
    is_end=True)

batch_map = {
    "Type": "Map",
    "MaxConcurrency": 4,
    "Comment": "First-load recovery from cached bronze. Runs four batches at a time to use the PR95 bulk merge optimization. Validated end-to-end in prod at MaxConcurrency=4 (run bronze-seed-silver-gold-1782384165, 2026-06-25: 81/81 BatchSilver batches succeeded, zero sec_pull_started, full chain through GoldRefresh SUCCEEDED), confirming the earlier MaxConcurrency=2 PASS (run bronze-seed-silver-gold-1782351277, 2026-06-24/25).",
    "ToleratedFailurePercentage": 0,
    "ItemReader": {
        "Resource": "arn:aws:states:::s3:getObject",
        "ReaderConfig": {"InputType": "JSONL", "MaxItems": 100000},
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_batches.jsonl', $$.Execution.Name)",
        },
    },
    "ItemProcessor": {
        "ProcessorConfig": {"Mode": "DISTRIBUTED", "ExecutionType": "STANDARD"},
        "StartAt": "RunBatch",
        "States": {"RunBatch": batch},
    },
    "ResultPath": None,
    "Next": "MdmRun",
}

# INVARIANT: No --limit on MDM commands here. bronze_seed_silver_gold is always a full
# bulk run (all CIKs found in bronze), not an incremental daily update.
mdm_run      = ecs_state(mdm_medium_arn, "States.Array('mdm', 'run', '--entity-type', 'all')", next_state="MdmBackfill")
mdm_backfill = ecs_state(mdm_medium_arn, "States.Array('mdm', 'backfill-relationships')", next_state="MdmExport")
# MdmExport precedes MdmSync (data-architecture Issue 3) — see write_load_history_definition.
mdm_export   = ecs_state(mdm_medium_arn, "States.Array('mdm', 'export')", next_state="MdmSync")
mdm_sync     = ecs_state(mdm_medium_arn, "States.Array('mdm', 'sync-graph')", next_state="MdmVerify")
mdm_verify   = ecs_state(mdm_small_arn,  "States.Array('mdm', 'verify-graph')", next_state="GoldRefresh")
mdm_verify["Catch"] = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "GoldRefresh"}]
# verify-graph is validation-only per docs/data-architecture.md: it reports
# parity but must never block gold-refresh, so a verify failure falls through.
gold         = ecs_state(wh_large_arn,   "States.Array('gold-refresh', '--run-id', $$.Execution.Name)", is_end=True, retry_secs=60)

definition = {
    "Comment": (
        "One-click cold-start/recovery from an existing bronze snapshot: "
        "(1) seed batch file by listing CIKs directly from S3 bronze (zero SEC calls, "
        "works even when silver has never been built), "
        "(2) sequential bootstrap-batch uses bronze SHA256 cache for submissions + runs artifact pipeline, "
        "(3) MDM entity resolution + Neo4j sync, "
        "(4) gold build + Snowflake export manifest. "
        "Trigger with: {} or {\"batch_size\": 100}"
    ),
    "StartAt": "BatchSizeCheck",
    "States": {
        "BatchSizeCheck": batch_size_check,
        "BatchSizeDefault": batch_size_default,
        "SeedFromBronze": seed_from_bronze,
        "BatchSilver":  batch_map,
        "MdmRun":       mdm_run,
        "MdmBackfill":  mdm_backfill,
        "MdmExport":    mdm_export,
        "MdmSync":      mdm_sync,
        "MdmVerify":    mdm_verify,
        "GoldRefresh":  gold,
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
      --definition "$(file_url "$definition_file")" \
      --type STANDARD \
      --logging-configuration "$(file_url "$logging_file")" \
      --tags key=Environment,value="$ENVIRONMENT" key=ManagedBy,value=operator-script key=Project,value=edgartools key=Workflow,value="$workflow" \
      --query 'stateMachineArn' \
      --output text
  else
    log "Updating Step Functions state machine ${name}"
    aws_cli stepfunctions update-state-machine \
      --state-machine-arn "$arn" \
      --role-arn "$role_arn" \
      --definition "$(file_url "$definition_file")" \
      --logging-configuration "$(file_url "$logging_file")" >/dev/null
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

# seed_universe: the standalone edgartools-dev-seed-universe state machine
# predates this script's workflow loop and was orphaned (its frozen task-def
# revision pointed at an ECR digest that had been garbage-collected, so every
# execution failed with CannotPullContainerError). Managing it here adopts the
# legacy machine in dev and creates it in newer environments.
for workflow in bootstrap_full targeted_resync full_reconcile load_daily_form_index_for_date catch_up_daily_form_index gold_refresh seed_universe; do
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
write_bootstrap_batched_definition "$bootstrap_definition_file" "$TASK_DEF_MEDIUM_ARN" "$TASK_DEF_MEDIUM_ARN"
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
  # load_history: the recommended way to load 100+ companies.
  # Chains seed → parallel bronze+silver batches → MDM → gold-refresh once.
  phased_definition_file="$(json_file sfn-load-history)"
  write_load_history_definition "$phased_definition_file" \
    "$TASK_DEF_SMALL_ARN" "$TASK_DEF_MEDIUM_ARN" "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_MDM_MEDIUM_ARN" "$TASK_DEF_LARGE_ARN"
  phased_state_machine_arn="$(upsert_state_machine load_history "$phased_definition_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
  printf ',\n' >> "$WORKFLOW_ARNS_FILE"
  python3 - "load_history" "$phased_state_machine_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
import json, sys
print(f"  {json.dumps(sys.argv[1])}: {json.dumps(sys.argv[2])}", end="")
PY

  # bootstrap: recent filings → MDM chain → gold. Same shape as load_history
  # but scoped to the 10 most recent filings per active company instead of a full batch sweep.
  recent10_definition_file="$(json_file sfn-bootstrap)"
  write_warehouse_mdm_gold_definition "$recent10_definition_file" \
    "$TASK_DEF_MEDIUM_ARN" "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_MDM_MEDIUM_ARN" "$TASK_DEF_LARGE_ARN" \
    "bootstrap"
  recent10_state_machine_arn="$(upsert_state_machine bootstrap "$recent10_definition_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
  printf ',\n' >> "$WORKFLOW_ARNS_FILE"
  python3 - "bootstrap" "$recent10_state_machine_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
import json, sys
print(f"  {json.dumps(sys.argv[1])}: {json.dumps(sys.argv[2])}", end="")
PY

  # daily_incremental: daily new filings → MDM chain → gold. Same pipeline shape.
  daily_definition_file="$(json_file sfn-daily-incremental)"
  write_warehouse_mdm_gold_definition "$daily_definition_file" \
    "$TASK_DEF_MEDIUM_ARN" "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_MDM_MEDIUM_ARN" "$TASK_DEF_LARGE_ARN" \
    "daily_incremental"
  daily_state_machine_arn="$(upsert_state_machine daily_incremental "$daily_definition_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
  printf ',\n' >> "$WORKFLOW_ARNS_FILE"
  python3 - "daily_incremental" "$daily_state_machine_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
import json, sys
print(f"  {json.dumps(sys.argv[1])}: {json.dumps(sys.argv[2])}", end="")
PY

  # mdm_gold: MDM entity resolution + Neo4j sync + gold-refresh, no silver batch step.
  # Use after BatchBootstrap already completed — skips all submission downloading.
  mdm_gold_file="$(json_file sfn-mdm-gold)"
  python3 - "$mdm_gold_file" "$CLUSTER_ARN" \
    "$TASK_DEF_MDM_MEDIUM_ARN" "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_LARGE_ARN" \
    "edgar-warehouse" "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" \
    "$MDM_RUN_LIMIT" "$MDM_GRAPH_LIMIT" <<'PY'
import json, pathlib, sys
(output_file, cluster_arn,
 mdm_medium_arn, mdm_small_arn, wh_large_arn,
 container_name, subnet_json, security_group_json,
 mdm_run_limit, mdm_graph_limit) = sys.argv[1:]
subnets = json.loads(subnet_json)
security_groups = json.loads(security_group_json)
mdm_limit   = str(mdm_run_limit)
graph_limit = str(mdm_graph_limit)

def ecs_state(task_def_arn, cmd_expr, next_state=None, is_end=False, retry_secs=120):
    s = {"Type": "Task", "Resource": "arn:aws:states:::ecs:runTask.sync",
         "Parameters": {"LaunchType": "FARGATE", "Cluster": cluster_arn,
                        "TaskDefinition": task_def_arn, "PropagateTags": "TASK_DEFINITION",
                        "NetworkConfiguration": {"AwsvpcConfiguration": {
                            "AssignPublicIp": "ENABLED", "SecurityGroups": security_groups, "Subnets": subnets}},
                        "Overrides": {"ContainerOverrides": [{"Name": container_name, "Command.$": cmd_expr}]}},
         "Retry": [{"ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": retry_secs, "BackoffRate": 2.0, "MaxAttempts": 2}]}
    if is_end: s["End"] = True
    else: s["Next"] = next_state
    return s

definition = {
    "Comment": "MDM entity resolution + Neo4j sync + gold-refresh. No silver batch step — run after bronze+silver are complete.",
    "StartAt": "MdmRun",
    "States": {
        "MdmRun":      ecs_state(mdm_medium_arn, f"States.Array('mdm', 'run', '--entity-type', 'all', '--limit', '{mdm_limit}')", next_state="MdmBackfill"),
        "MdmBackfill": ecs_state(mdm_medium_arn, f"States.Array('mdm', 'backfill-relationships', '--limit', '{graph_limit}')", next_state="MdmExport"),
        # MdmExport precedes MdmSync (data-architecture Issue 3) — see write_load_history_definition.
        "MdmExport":   ecs_state(mdm_medium_arn, "States.Array('mdm', 'export')", next_state="MdmSync"),
        "MdmSync":     ecs_state(mdm_medium_arn, f"States.Array('mdm', 'sync-graph', '--limit', '{graph_limit}')", next_state="MdmVerify"),
        "MdmVerify":   ecs_state(mdm_small_arn,  "States.Array('mdm', 'verify-graph')", next_state="GoldRefresh"),
        "GoldRefresh": ecs_state(wh_large_arn,   "States.Array('gold-refresh', '--run-id', $$.Execution.Name)", is_end=True, retry_secs=60),
    },
}
pathlib.Path(output_file).write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
PY
  mdm_gold_arn="$(upsert_state_machine mdm_gold "$mdm_gold_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
  printf ',\n' >> "$WORKFLOW_ARNS_FILE"
  python3 - "mdm_gold" "$mdm_gold_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
import json, sys
print(f"  {json.dumps(sys.argv[1])}: {json.dumps(sys.argv[2])}", end="")
PY

  # ownership_mdm_gold: parse Form 3/4/5 XMLs already in S3 bronze → persons + IS_INSIDER in MDM → Neo4j → gold.
  # No SEC calls. Uses edgartools to parse XMLs directly from bronze.
  ownership_mdm_gold_file="$(json_file sfn-ownership-mdm-gold)"
  python3 - "$ownership_mdm_gold_file" "$CLUSTER_ARN" \
    "$TASK_DEF_MEDIUM_ARN" "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_MDM_MEDIUM_ARN" "$TASK_DEF_LARGE_ARN" \
    "edgar-warehouse" "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" <<'PY'
import json, pathlib, sys

(output_file, cluster_arn,
 wh_medium_arn, mdm_small_arn, mdm_medium_arn, wh_large_arn,
 container_name, subnet_json, security_group_json) = sys.argv[1:]

subnets = json.loads(subnet_json)
security_groups = json.loads(security_group_json)

def ecs_state(task_def_arn, cmd_expr, next_state=None, is_end=False, retry_secs=120):
    s = {
        "Type": "Task",
        "Resource": "arn:aws:states:::ecs:runTask.sync",
        "Parameters": {
            "LaunchType": "FARGATE",
            "Cluster": cluster_arn,
            "TaskDefinition": task_def_arn,
            "PropagateTags": "TASK_DEFINITION",
            "NetworkConfiguration": {"AwsvpcConfiguration": {
                "AssignPublicIp": "ENABLED",
                "SecurityGroups": security_groups,
                "Subnets": subnets,
            }},
            "Overrides": {"ContainerOverrides": [{"Name": container_name, "Command.$": cmd_expr}]},
        },
        "Retry": [{"ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": retry_secs,
                   "BackoffRate": 2.0, "MaxAttempts": 2}],
    }
    if is_end:
        s["End"] = True
    else:
        s["Next"] = next_state
    return s

definition = {
    "Comment": (
        "Parse Form 3/4/5 ownership XMLs already in S3 bronze (no SEC calls), "
        "then run MDM to derive persons + IS_INSIDER relationships, sync to Neo4j, refresh gold."
    ),
    "StartAt": "ParseOwnershipBronze",
    "States": {
        "ParseOwnershipBronze": ecs_state(wh_medium_arn,
            "States.Array('parse-ownership-bronze', '--run-id', $$.Execution.Name)",
            next_state="MdmRun", retry_secs=60),
        "MdmRun":      ecs_state(mdm_medium_arn, "States.Array('mdm', 'run', '--entity-type', 'all')", next_state="MdmBackfill"),
        "MdmBackfill": ecs_state(mdm_medium_arn, "States.Array('mdm', 'backfill-relationships')", next_state="MdmExport"),
        # MdmExport precedes MdmSync (data-architecture Issue 3) — see write_load_history_definition.
        "MdmExport":   ecs_state(mdm_medium_arn, "States.Array('mdm', 'export')", next_state="MdmSync"),
        "MdmSync":     ecs_state(mdm_medium_arn, "States.Array('mdm', 'sync-graph')", next_state="MdmVerify"),
        "MdmVerify":   ecs_state(mdm_small_arn,  "States.Array('mdm', 'verify-graph')", next_state="GoldRefresh"),
        "GoldRefresh": ecs_state(wh_large_arn,   "States.Array('gold-refresh', '--run-id', $$.Execution.Name)", is_end=True, retry_secs=60),
    },
}
pathlib.Path(output_file).write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
PY
  ownership_mdm_gold_arn="$(upsert_state_machine ownership_mdm_gold "$ownership_mdm_gold_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
  printf ',\n' >> "$WORKFLOW_ARNS_FILE"
  python3 - "ownership_mdm_gold" "$ownership_mdm_gold_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
import json, sys
print(f"  {json.dumps(sys.argv[1])}: {json.dumps(sys.argv[2])}", end="")
PY

  # silver_mdm_gold: re-process already-loaded bronze through silver → MDM → Neo4j → Snowflake.
  silver_mdm_gold_file="$(json_file sfn-silver-mdm-gold)"
  write_silver_mdm_gold_definition "$silver_mdm_gold_file" \
    "$TASK_DEF_MEDIUM_ARN" "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_MDM_MEDIUM_ARN" "$TASK_DEF_LARGE_ARN"
  silver_mdm_gold_arn="$(upsert_state_machine silver_mdm_gold "$silver_mdm_gold_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
  printf ',\n' >> "$WORKFLOW_ARNS_FILE"
  python3 - "silver_mdm_gold" "$silver_mdm_gold_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
import json, sys
print(f"  {json.dumps(sys.argv[1])}: {json.dumps(sys.argv[2])}", end="")
PY

  # bronze_seed_silver_gold: one-click cold-start/recovery from an existing bronze
  # snapshot (e.g. copied in from another environment) through silver → MDM → Neo4j →
  # Snowflake. Unlike silver_mdm_gold, does not depend on silver already knowing about
  # the CIKs — discovers them directly from S3 bronze.
  bronze_seed_silver_gold_file="$(json_file sfn-bronze-seed-silver-gold)"
  write_bronze_seed_silver_gold_definition "$bronze_seed_silver_gold_file" \
    "$TASK_DEF_MEDIUM_ARN" "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_MDM_MEDIUM_ARN" "$TASK_DEF_LARGE_ARN"
  bronze_seed_silver_gold_arn="$(upsert_state_machine bronze_seed_silver_gold "$bronze_seed_silver_gold_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
  printf ',\n' >> "$WORKFLOW_ARNS_FILE"
  python3 - "bronze_seed_silver_gold" "$bronze_seed_silver_gold_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
import json, sys
print(f"  {json.dumps(sys.argv[1])}: {json.dumps(sys.argv[2])}", end="")
PY

  for workflow in mdm_migrate mdm_check_connectivity mdm_run mdm_backfill_relationships mdm_sync_graph mdm_verify_graph mdm_counts mdm_seed_universe mdm_seed_from_silver; do
    task_definition_arn="$(task_definition_for_mdm_workflow "$workflow")"
    command_expression="$(mdm_workflow_command_expression "$workflow")"
    limit_command_expression="$(mdm_workflow_limit_command_expression "$workflow")"
    relationship_command_expression="$(mdm_workflow_relationship_command_expression "$workflow")"
    relationship_limit_command_expression="$(mdm_workflow_relationship_limit_command_expression "$workflow")"
    definition_file="$(json_file "sfn-${workflow}")"
    write_mdm_workflow_definition "$definition_file" "$task_definition_arn" "$command_expression" "$limit_command_expression" "$relationship_command_expression" "$relationship_limit_command_expression"
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
# MSYS_NO_PATHCONV=1: same fix as the ensure_log_group call above -- without
# it, Git Bash rewrites the /aws/ecs/... and /aws/states/... argv strings
# below into Windows filesystem paths (e.g. C:/Program Files/Git/aws/ecs/...)
# before python3 ever sees them, corrupting log_groups in the written
# deployment-summary manifest even though the actual ECS task definitions
# (registered earlier via the already-guarded call) are unaffected.
# MSYS_NO_PATHCONV=1 also disables the (wanted) translation of the two real
# temp-file paths below, so those are converted explicitly via win_path()
# instead -- same split responsibility as the earlier guarded call.
MSYS_NO_PATHCONV=1 python3 - "$(win_path "$SUMMARY_FILE")" "$ENVIRONMENT" "$AWS_REGION_NAME" "$NAME_PREFIX" "$IMAGE_REF" "$MDM_IMAGE_REF" \
  "$CLUSTER_NAME" "$CLUSTER_ARN" "$ECR_REPOSITORY_URL" "$LOG_GROUP_NAME" \
  "$STEP_FUNCTIONS_ROLE_ARN" "$STEP_FUNCTIONS_LOG_GROUP_NAME" \
  "$TASK_DEF_SMALL_ARN" "$TASK_DEF_MEDIUM_ARN" "$TASK_DEF_LARGE_ARN" \
  "$DEPLOY_MDM" "$MDM_DATABASE_SOURCE" "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_MDM_MEDIUM_ARN" "$MDM_SILVER_DUCKDB" \
  "$MDM_POSTGRES_DSN_SECRET_ARN" "$MDM_SNOWFLAKE_SECRET_ARN" \
  "$(win_path "$WORKFLOW_ARNS_FILE")" \
  "$BRONZE_BUCKET_NAME" "$WAREHOUSE_BUCKET_NAME" "$SNOWFLAKE_EXPORT_BUCKET_NAME" \
  "$EXECUTION_ROLE_ARN" "$TASK_ROLE_ARN" "$EDGAR_IDENTITY_SECRET_ARN" <<'PY'
import json
import pathlib
import sys

(
    output_file,
    environment,
    region,
    name_prefix,
    image_ref,
    mdm_image_ref,
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
    mdm_database_source,
    mdm_small_task_definition,
    mdm_medium_task_definition,
    mdm_silver_duckdb,
    mdm_database_secret_arn,
    snowflake_secret_arn,
    workflow_arns_file,
    bronze_bucket_name,
    warehouse_bucket_name,
    snowflake_export_bucket_name,
    execution_role_arn,
    task_role_arn,
    edgar_identity_secret_arn,
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
    "mdm_image_ref": mdm_image_ref if deploy_mdm == "true" else None,
    "cluster": {
        "name": cluster_name,
        "arn": cluster_arn,
    },
    "ecr_repository_url": ecr_repository_url,
    "log_groups": {
        "ecs": ecs_log_group_name,
        "step_functions": step_functions_log_group_name,
    },
    "bronze_bucket_name": bronze_bucket_name,
    "warehouse_bucket_name": warehouse_bucket_name,
    "snowflake_export_bucket_name": snowflake_export_bucket_name,
    "execution_role_arn": execution_role_arn,
    "task_role_arn": task_role_arn,
    "step_functions_role_arn": step_functions_role_arn,
    "edgar_identity_secret_arn": edgar_identity_secret_arn,
    "task_definitions": task_definitions,
    "state_machines": json.loads(pathlib.Path(workflow_arns_file).read_text(encoding="utf-8")),
}
if deploy_mdm == "true":
    summary["mdm"] = {
        "image_ref": mdm_image_ref,
        "database_source": mdm_database_source,
        "silver_duckdb": mdm_silver_duckdb,
        "secrets": {
            "postgres_dsn": mdm_database_secret_arn,
            "snowflake": snowflake_secret_arn,
        },
    }

pathlib.Path(output_file).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
PY

# Always update the deployment manifest so future deploys resolve params without Terraform.
cp "$SUMMARY_FILE" "$MANIFEST_FILE"
log "Manifest written to ${MANIFEST_FILE}"

if ! is_empty "$OUTPUT_FILE"; then
  cp "$SUMMARY_FILE" "$OUTPUT_FILE"
fi

cat "$SUMMARY_FILE"
