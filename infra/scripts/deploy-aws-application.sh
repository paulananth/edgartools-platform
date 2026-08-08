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
  --ecr-repository-url <url>        ECR repository URL. Default: <account>.dkr.ecr.<region>.amazonaws.com/<prefix>-images
                                    (single shared repo for warehouse/mdm x final/deps; role lives
                                    in the image tag, e.g. warehouse-<tag>/mdm-<tag>).
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
                                    Default: sec_platform for dev and sec_platform_prod for
                                    prod, matching the access Terraform account roots.
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
  --mdm-image-ref <ref>             Existing MDM image ref. Required when MDM is
                                    deployed and --build-mdm-image is not set.
                                    Never silently defaults to the warehouse image.
  --mdm-ecr-repository-url <url>    ECR repository URL for built MDM image. Default: same shared
                                    <prefix>-images repo as --ecr-repository-url (mdm-* tags).
  --build-mdm-image                 Build and push a separate MDM image when MDM is deployed.
  --mdm-database-source <snowflake-postgres>
                                    Source of the MDM_DATABASE_URL secret. Only snowflake-postgres
                                    is supported (MDM Postgres runs on Snowflake's native Postgres
                                    service; there is no AWS RDS instance to source from).
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
  --mdm-graph-rule-version <v>      Default rule_version baked into generation_build state machine. Default: v1.
  --mdm-graph-schema-version <v>    Default schema_version baked into generation_build state machine. Default: v1.
  --mdm-generation-partition-concurrency <n>
                                    MaxConcurrency for generation_build's BuildPartitions Distributed Map. Default: 8.
  --output-file <path>              Write deployment summary JSON.
  --configure-daily-incremental-schedule <enable|disable>
                                    Off-by-default operator control (release-readiness
                                    ticket 45/49) for edgartools-<env>-daily-incremental's
                                    recurring trigger: creates/updates (enable) or removes
                                    (disable) two EventBridge rules -- Daily Identity
                                    Refresh Mon-Sat 12:00 UTC (refresh_mode=daily) and
                                    Identity Backstop Sweep Sun 12:00 UTC
                                    (refresh_mode=backstop). Never runs as a side effect of
                                    an ordinary deploy; run this flag alone, as
                                    sec_platform_deployer, after an explicit operator go.
                                    Exits immediately after configuring -- does not build
                                    images, register task definitions, or touch state
                                    machines.
  --daily-incremental-scheduler-role-arn <arn>
                                    IAM role ARN EventBridge assumes to start
                                    edgartools-<env>-daily-incremental. Required with
                                    --configure-daily-incremental-schedule enable. Source:
                                    infra/terraform/access/aws/accounts/<env> output
                                    daily_incremental_scheduler_role_arn.
  --configure-daily-incremental-alarms <enable|disable>
                                    Explicitly create/update or remove the 18-hour
                                    timeout alarm AND the application-level execution-
                                    failure alarm (AWS/States ExecutionsFailed --
                                    release-readiness ticket 81; covers States.TaskFailed
                                    and similar non-timeout failures the timeout alarm
                                    does not see). Per-deferral SNS delivery is part of
                                    the deployed state machine. This standalone action
                                    never deploys workloads or enables schedules.
  --operator-alert-topic-arn <arn>  Confirmed operator SNS topic used by both alarms.
                                    Required when enabling alarms.
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
MDM_GRAPH_RULE_VERSION="v1"
MDM_GRAPH_SCHEMA_VERSION="v1"
MDM_GENERATION_PARTITION_CONCURRENCY=8
RUNNER_ROLE_NAME_PREFIX=""
OUTPUT_FILE=""
CONFIGURE_DAILY_INCREMENTAL_SCHEDULE=""
DAILY_INCREMENTAL_SCHEDULER_ROLE_ARN=""
CONFIGURE_DAILY_INCREMENTAL_ALARMS=""
OPERATOR_ALERT_TOPIC_ARN=""

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
    --mdm-graph-rule-version) MDM_GRAPH_RULE_VERSION="${2:?}"; shift 2 ;;
    --mdm-graph-schema-version) MDM_GRAPH_SCHEMA_VERSION="${2:?}"; shift 2 ;;
    --mdm-generation-partition-concurrency) MDM_GENERATION_PARTITION_CONCURRENCY="${2:?}"; shift 2 ;;
    --runner-role-name-prefix) RUNNER_ROLE_NAME_PREFIX="${2:?}"; shift 2 ;;
    --output-file) OUTPUT_FILE="${2:?}"; shift 2 ;;
    --configure-daily-incremental-schedule) CONFIGURE_DAILY_INCREMENTAL_SCHEDULE="${2:?}"; shift 2 ;;
    --daily-incremental-scheduler-role-arn) DAILY_INCREMENTAL_SCHEDULER_ROLE_ARN="${2:?}"; shift 2 ;;
    --configure-daily-incremental-alarms) CONFIGURE_DAILY_INCREMENTAL_ALARMS="${2:?}"; shift 2 ;;
    --operator-alert-topic-arn) OPERATOR_ALERT_TOPIC_ARN="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$ENVIRONMENT" == "dev" || "$ENVIRONMENT" == "prod" ]] || { usage >&2; exit 2; }
[[ -n "$EXPECTED_AWS_ACCOUNT_ID" ]] || fail "--aws-account-id is required"
if [[ ! "$EXPECTED_AWS_ACCOUNT_ID" =~ ^[0-9]{12}$ ]]; then
  fail "--aws-account-id must be a 12-digit AWS account ID"
fi
if ! is_empty "$CONFIGURE_DAILY_INCREMENTAL_ALARMS"; then
  case "$CONFIGURE_DAILY_INCREMENTAL_ALARMS" in
    enable|disable) ;;
    *) fail "--configure-daily-incremental-alarms must be enable or disable" ;;
  esac
  if [[ "$CONFIGURE_DAILY_INCREMENTAL_ALARMS" == "enable" ]] && is_empty "$OPERATOR_ALERT_TOPIC_ARN"; then
    fail "--operator-alert-topic-arn is required with --configure-daily-incremental-alarms enable"
  fi
fi
if is_empty "$RUNNER_ROLE_NAME_PREFIX"; then
  if [[ "$ENVIRONMENT" == "prod" ]]; then
    RUNNER_ROLE_NAME_PREFIX="sec_platform_prod"
  else
    RUNNER_ROLE_NAME_PREFIX="sec_platform"
  fi
fi
[[ "$WAREHOUSE_RUNTIME_MODE" == "bronze_capture" || "$WAREHOUSE_RUNTIME_MODE" == "infrastructure_validation" ]] || fail "--warehouse-runtime-mode must be bronze_capture or infrastructure_validation"
[[ "$PUSH_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || fail "--push-attempts must be a positive integer"
[[ "$BOOTSTRAP_BATCH_CONCURRENCY" =~ ^[1-9][0-9]*$ ]] || fail "--bootstrap-batch-concurrency must be a positive integer"
[[ "$MDM_RUN_LIMIT" =~ ^[0-9]+$ ]] || fail "--mdm-run-limit must be a non-negative integer"
[[ "$MDM_GRAPH_LIMIT" =~ ^[0-9]+$ ]] || fail "--mdm-graph-limit must be a non-negative integer"
[[ "$MDM_GENERATION_PARTITION_CONCURRENCY" =~ ^[1-9][0-9]*$ ]] || fail "--mdm-generation-partition-concurrency must be a positive integer"
if ! is_empty "$MDM_DATABASE_SOURCE"; then
  case "$MDM_DATABASE_SOURCE" in
    snowflake-postgres) ;;
    *) fail "--mdm-database-source must be snowflake-postgres" ;;
  esac
fi
if ! is_empty "$WAREHOUSE_BRONZE_CIK_LIMIT"; then
  [[ "$WAREHOUSE_BRONZE_CIK_LIMIT" =~ ^[0-9]+$ ]] || fail "--warehouse-bronze-cik-limit must be a non-negative integer"
fi
if ! is_empty "$CONFIGURE_DAILY_INCREMENTAL_SCHEDULE"; then
  case "$CONFIGURE_DAILY_INCREMENTAL_SCHEDULE" in
    enable|disable) ;;
    *) fail "--configure-daily-incremental-schedule must be enable or disable" ;;
  esac
  if [[ "$CONFIGURE_DAILY_INCREMENTAL_SCHEDULE" == "enable" ]] && is_empty "$DAILY_INCREMENTAL_SCHEDULER_ROLE_ARN"; then
    fail "--daily-incremental-scheduler-role-arn is required with --configure-daily-incremental-schedule enable"
  fi
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

MDM_DATABASE_SOURCE="$(first_nonempty "$MDM_DATABASE_SOURCE" "$(manifest_value mdm.database_source)" "snowflake-postgres")"
case "$MDM_DATABASE_SOURCE" in
  snowflake-postgres) ;;
  *) fail "--mdm-database-source must be snowflake-postgres" ;;
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

# --configure-daily-incremental-schedule is a standalone action (release-readiness
# ticket 45/49): it needs only ACCOUNT_ID/AWS_REGION_NAME/NAME_PREFIX (all resolved
# above) and the deterministic state-machine ARN upsert_state_machine's own naming
# convention produces (${NAME_PREFIX}-daily-incremental) -- no image build, task
# definition, or state-machine deploy is required. Handled here, before any of that
# heavier work below runs, and exits immediately so this flag is never an accidental
# side effect of an ordinary deploy invocation.
build_daily_incremental_targets_json() {
  # $1 = state machine ARN, $2 = scheduler role ARN, $3 = refresh_mode value.
  # EventBridge's target Input is itself a JSON-encoded string (not a nested
  # object), hence json.dumps applied twice below -- once for the target
  # list, once for the Input string it contains.
  python3 - "$1" "$2" "$3" <<'PY'
import json
import sys

arn, role_arn, refresh_mode = sys.argv[1:4]
print(json.dumps([{
    "Id": "daily-incremental-sfn",
    "Arn": arn,
    "RoleArn": role_arn,
    "Input": json.dumps({"refresh_mode": refresh_mode}),
}]))
PY
}

# Creates/updates one EventBridge rule + its daily-incremental target.
# $1 = rule name, $2 = cron schedule expression, $3 = description,
# $4 = refresh_mode value for the target's Input, $5 = state machine ARN,
# $6 = scheduler role ARN. Shared by both the Mon-Sat and Sunday rules
# below so their put-rule/put-targets shape can't drift out of sync.
put_daily_incremental_schedule_rule() {
  local rule_name="$1" cron_expr="$2" description="$3" refresh_mode="$4" state_machine_arn="$5" role_arn="$6"
  aws_cli events put-rule \
    --name "$rule_name" \
    --schedule-expression "$cron_expr" \
    --state ENABLED \
    --description "$description" >/dev/null
  aws_cli events put-targets --rule "$rule_name" \
    --targets "$(build_daily_incremental_targets_json "$state_machine_arn" "$role_arn" "$refresh_mode")" >/dev/null
  log "EventBridge rule ${rule_name} configured (${cron_expr})"
}

configure_daily_incremental_schedule() {
  local action="$1" role_arn="$2"
  local state_machine_arn="arn:aws:states:${AWS_REGION_NAME}:${ACCOUNT_ID}:stateMachine:${NAME_PREFIX}-daily-incremental"
  local daily_rule="${NAME_PREFIX}-daily-incremental-refresh"
  local backstop_rule="${NAME_PREFIX}-daily-incremental-backstop"

  if [[ "$action" == "disable" ]]; then
    log "Disabling daily_incremental schedule (${daily_rule}, ${backstop_rule})"
    local rule
    for rule in "$daily_rule" "$backstop_rule"; do
      if aws_cli events describe-rule --name "$rule" >/dev/null 2>&1; then
        aws_cli events remove-targets --rule "$rule" --ids daily-incremental-sfn >/dev/null
        aws_cli events delete-rule --name "$rule"
        log "Deleted EventBridge rule ${rule}"
      else
        log "EventBridge rule ${rule} does not exist -- nothing to disable"
      fi
    done
    return 0
  fi

  log "Enabling daily_incremental schedule: Daily Identity Refresh Mon-Sat 12:00 UTC, Identity Backstop Sweep Sun 12:00 UTC"

  # 12:00 UTC = 7am EST / 8am EDT -- safely after the daily-index file's
  # expected ~6am ET availability in both standard and daylight time, with
  # margin (same rationale the removed passive-Terraform schedule used).
  # EventBridge cron requires exactly one of day-of-month/day-of-week to be
  # '?' when the other field is explicit -- '?' goes on day-of-month here
  # since both rules pin an explicit day-of-week.
  put_daily_incremental_schedule_rule \
    "$daily_rule" "cron(0 12 ? * MON-SAT *)" \
    "Daily Identity Refresh for ${NAME_PREFIX}-daily-incremental (release-readiness ticket 45/49)" \
    "daily" "$state_machine_arn" "$role_arn"

  put_daily_incremental_schedule_rule \
    "$backstop_rule" "cron(0 12 ? * SUN *)" \
    "Identity Backstop Sweep for ${NAME_PREFIX}-daily-incremental (release-readiness ticket 45/49)" \
    "backstop" "$state_machine_arn" "$role_arn"
}

if ! is_empty "$CONFIGURE_DAILY_INCREMENTAL_SCHEDULE"; then
  configure_daily_incremental_schedule "$CONFIGURE_DAILY_INCREMENTAL_SCHEDULE" "$DAILY_INCREMENTAL_SCHEDULER_ROLE_ARN"
  exit 0
fi

require_confirmed_operator_alert_topic() {
  local topic_arn="$1" confirmed_subscriptions

  [[ "$topic_arn" == "arn:aws:sns:${AWS_REGION_NAME}:${ACCOUNT_ID}:"* ]] ||
    fail "--operator-alert-topic-arn must be an SNS topic in ${AWS_REGION_NAME}, account ${ACCOUNT_ID}"
  confirmed_subscriptions="$(aws_cli sns list-subscriptions-by-topic \
    --topic-arn "$topic_arn" \
    --query "length(Subscriptions[?SubscriptionArn!='PendingConfirmation'])" \
    --output text)"
  [[ "$confirmed_subscriptions" =~ ^[1-9][0-9]*$ ]] ||
    fail "--operator-alert-topic-arn must have at least one confirmed subscription"
}

configure_daily_incremental_alarms() {
  local action="$1" topic_arn="$2"
  local state_machine_arn="arn:aws:states:${AWS_REGION_NAME}:${ACCOUNT_ID}:stateMachine:${NAME_PREFIX}-daily-incremental"
  local timeout_alarm="${NAME_PREFIX}-daily-incremental-timeout"
  local failed_alarm="${NAME_PREFIX}-daily-incremental-failed"

  if [[ "$action" == "disable" ]]; then
    aws_cli cloudwatch delete-alarms --alarm-names "$timeout_alarm" "$failed_alarm"
    log "Deleted daily_incremental timeout and failure alarms"
    return 0
  fi

  require_confirmed_operator_alert_topic "$topic_arn"

  aws_cli cloudwatch put-metric-alarm \
    --alarm-name "$timeout_alarm" \
    --alarm-description "Daily Identity Refresh execution reached the hard 18-hour bound" \
    --namespace "AWS/States" \
    --metric-name "ExecutionsTimedOut" \
    --dimensions "Name=StateMachineArn,Value=${state_machine_arn}" \
    --statistic Sum --period 60 --evaluation-periods 1 \
    --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold \
    --treat-missing-data notBreaching \
    --alarm-actions "$topic_arn"
  log "Configured daily_incremental 18-hour timeout alarm"

  # release-readiness ticket 81: the timeout alarm only sees ExecutionsTimedOut --
  # an application-level failure (States.TaskFailed, e.g. an ECS task exiting
  # non-zero) increments ExecutionsFailed instead and previously reached no one.
  aws_cli cloudwatch put-metric-alarm \
    --alarm-name "$failed_alarm" \
    --alarm-description "Daily Identity Refresh execution failed (application-level, not a timeout)" \
    --namespace "AWS/States" \
    --metric-name "ExecutionsFailed" \
    --dimensions "Name=StateMachineArn,Value=${state_machine_arn}" \
    --statistic Sum --period 60 --evaluation-periods 1 \
    --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold \
    --treat-missing-data notBreaching \
    --alarm-actions "$topic_arn"
  log "Configured daily_incremental execution-failure alarm"
}

if ! is_empty "$CONFIGURE_DAILY_INCREMENTAL_ALARMS"; then
  configure_daily_incremental_alarms "$CONFIGURE_DAILY_INCREMENTAL_ALARMS" "$OPERATOR_ALERT_TOPIC_ARN"
  exit 0
fi

# Parameter resolution order (no Terraform):
#   1. CLI flag (already set above)
#   2. Deployment manifest (infra/aws-<env>-application.json — written by every successful deploy)
#   3. AWS API discovery / deterministic naming convention

# Cluster
CLUSTER_ARN="$(first_nonempty "$CLUSTER_ARN" "$(manifest_value cluster.arn)")"
CLUSTER_NAME="$(first_nonempty "$CLUSTER_NAME" "$(manifest_value cluster.name)")"

# ECR — single shared repo for all roles/stages: <account>.dkr.ecr.<region>.amazonaws.com/<prefix>-images
# Role (warehouse/mdm) and stage (final/deps) are encoded in the image tag
# (warehouse-*, mdm-*, warehouse-deps-*, mdm-deps-*), not the repository name.
ECR_REPOSITORY_URL="$(first_nonempty "$ECR_REPOSITORY_URL" "$(manifest_value ecr_repository_url)" \
  "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION_NAME}.amazonaws.com/${NAME_PREFIX}-images")"

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

# MDM ECR — same shared repo as the warehouse image; role lives in the tag
# (mdm-* vs warehouse-*), not the repository name.
if is_empty "$MDM_ECR_REPOSITORY_URL"; then
  MDM_ECR_REPOSITORY_URL="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION_NAME}.amazonaws.com/${NAME_PREFIX}-images"
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

# MDM Postgres runs on Snowflake's native Postgres service (no AWS RDS
# instance exists to sync a DSN from); MDM_POSTGRES_DSN_SECRET_ARN is
# operator-managed and this script never overwrites it.
if [[ "$DEPLOY_MDM" == "true" ]] && ! is_empty "$MDM_POSTGRES_DSN_SECRET_ARN"; then
  log "Using operator-managed Snowflake Postgres DSN secret (${MDM_POSTGRES_DSN_SECRET_ARN})"
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
log "Cleaning up stale ECR images (keeps every tagged image + active task digests)"
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

image_ref_has_tag_prefix() {
  # Both roles now share one ECR repo, so the repo URL can no longer tell
  # warehouse and mdm images apart -- resolve the digest's own tag list and
  # check for the expected role prefix (warehouse-*/mdm-*) instead.
  local image_ref="$1" prefix="$2" repo_name digest tags_json
  repo_name="${image_ref%%@*}"
  repo_name="${repo_name##*/}"
  digest="${image_ref##*@}"
  [[ "$digest" == "$image_ref" ]] && return 1  # not digest-addressed; can't check tags
  tags_json="$(aws_cli ecr describe-images \
    --repository-name "$repo_name" \
    --image-ids "imageDigest=${digest}" \
    --query 'imageDetails[0].imageTags' --output json 2>/dev/null || echo 'null')"
  [[ "$tags_json" == "null" ]] && return 1
  python3 -c "
import json, sys
tags = json.loads(sys.argv[1]) or []
sys.exit(0 if any(t.startswith(sys.argv[2] + '-') for t in tags) else 1)
" "$tags_json" "$prefix"
}

if [[ "$DEPLOY_MDM" == "true" ]]; then
  if is_empty "$MDM_IMAGE_REF"; then
    fail "MDM deploy requires a distinct MDM image. Pass --mdm-image-ref <mdm-digest> or --build-mdm-image. Refusing to reuse the warehouse image (warehouse and MDM have different dependency sets)."
  fi
  if [[ "$MDM_IMAGE_REF" == "$IMAGE_REF" ]]; then
    fail "MDM image_ref equals warehouse image_ref (${IMAGE_REF}). Pass a distinct --mdm-image-ref. Mixing roles breaks Ticket 20 / MDM runtimes."
  fi
  # Role guard: confirm each digest actually carries the expected role-prefixed
  # tag (warehouse-*/mdm-*) in the shared images repo, catching an accidental
  # image_ref/mdm_image_ref swap. Skipped for non-digest refs (e.g. :dev),
  # where the tag itself already states its role.
  if ! image_ref_has_tag_prefix "$IMAGE_REF" "warehouse"; then
    fail "Warehouse image_ref (${IMAGE_REF}) has no warehouse-* tag in ECR. Looks like an MDM image was passed as --image-ref."
  fi
  if ! image_ref_has_tag_prefix "$MDM_IMAGE_REF" "mdm"; then
    fail "MDM image_ref (${MDM_IMAGE_REF}) has no mdm-* tag in ECR. Looks like a warehouse image was passed as --mdm-image-ref."
  fi
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
    # Bound into immutable Daily Identity Refresh plans and verified again by
    # the reducer. This is the deployed ECR digest, never a mutable tag.
    {"name": "WAREHOUSE_IMAGE_REF", "value": image_ref},
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
# Medium handles Bronze/Silver window work. load_history's per-window
# `bootstrap-next` explicitly uses --silver-only; the workflow's single final
# `gold-refresh` owns the full-universe gold/Snowflake publication on large.
# 4096 MB remains the measured floor for canonical Silver merge/publication.
TASK_DEF_MEDIUM_ARN="$(register_task_definition medium 1024 4096)"
# large memory raised 4096 -> 8192 (2026-07-30, gold-build-memory-reliability ticket 03):
# `large` and `medium` shared the identical 4096MB ceiling (only CPU differed), so
# 37c3171's "move gold-refresh to large" fix was memory-ineffective -- confirmed when
# daily_incremental (medium, 4096MB) OOM-killed 4x building sec_thirteenf_holding.
# 8192 matches mdm-large's floor for the same class of full-universe gold-build memory
# pressure. daily_incremental/bootstrap/full_reconcile/gold_refresh all moved onto this
# profile below (workflow_profile()) since they share the identical build_gold() call
# site -- see .scratch/gold-build-memory-reliability/issues/03-decide-task-memory-fix-to-unblock-daily-incremental.md.
TASK_DEF_LARGE_ARN="$(register_task_definition large 2048 8192)"
TASK_DEF_MDM_SMALL_ARN=""
TASK_DEF_MDM_MEDIUM_ARN=""
TASK_DEF_MDM_LARGE_ARN=""
if [[ "$DEPLOY_MDM" == "true" ]]; then
  TASK_DEF_MDM_SMALL_ARN="$(register_mdm_task_definition mdm-small 512 1024)"
  # mdm-medium memory raised 2048 -> 4096 (2026-07-25, residual-holds OOM):
  # full-universe `mdm run --entity-type security` loads silver.duckdb (holdings/
  # ownership surfaces) and OOM-killed (exit 137) at 2048 MB on prod residual
  # holds pipeline residual-holds-20260725T221723Z / MdmSecurities. Same class of
  # failure as warehouse medium gold-from-silver (fix-pipelines 06-03).
  TASK_DEF_MDM_MEDIUM_ARN="$(register_mdm_task_definition mdm-medium 1024 4096)"
  # mdm-large for residual holds graph (security resolve + INSTITUTIONAL_HOLDS +
  # multi-type sync-graph). 13F / holds tables are the memory-heavy path.
  TASK_DEF_MDM_LARGE_ARN="$(register_mdm_task_definition mdm-large 2048 8192)"
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
    # DEAD CODE as of 2026-07-30 (gold-build-memory-reliability ticket 03 investigation):
    # workflow_profile() is never actually *called* with "daily_incremental" or "bootstrap"
    # anywhere in this script -- their real RunWarehouseTask task-def comes from
    # write_warehouse_mdm_gold_definition's run_wh (see that function's own comment), not
    # from here. These two cases are kept only so a value exists if that ever changes; set
    # to "large" to match the ticket 03 decision (both need large's raised 8192MB ceiling,
    # same as bootstrap_full/full_reconcile/gold_refresh below), not because this line is
    # actually reached in production.
    daily_incremental) printf '%s\n' "large" ;;
    bootstrap) printf '%s\n' "large" ;;
    # bootstrap_full/targeted_resync/full_reconcile/gold_refresh: this IS the operative path
    # (see the workflow_profile()-driven loop below) -- moved medium -> large (2026-07-30,
    # ticket 03): all four call the identical memory-heavy build_gold() path and need
    # large's raised 8192MB ceiling, not medium's unchanged 4096MB. See TASK_DEF_LARGE_ARN's
    # comment above.
    bootstrap_full) printf '%s\n' "large" ;;
    targeted_resync) printf '%s\n' "large" ;;
    full_reconcile) printf '%s\n' "large" ;;
    load_daily_form_index_for_date) printf '%s\n' "small" ;;
    catch_up_daily_form_index) printf '%s\n' "small" ;;
    gold_refresh) printf '%s\n' "large" ;;
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

# release-readiness ticket 94: sync-graph's `--limit-per-type` was CLI-only --
# the state machine's ASL only ever wired `$.limit`, so an execution input of
# {"limit_per_type": N} was silently ignored (fell through to the bare
# default command, which itself resolves to a small ~200-edge cap deep in
# snowflake_graph.py). Only mdm_sync_graph supports this flag; every other
# MDM workflow returns empty, same convention as the relationship_* helpers.
mdm_workflow_limit_per_type_command_expression() {
  case "$1" in
    mdm_sync_graph) printf '%s\n' "States.Array('mdm', 'sync-graph', '--limit-per-type', States.Format('{}', $.limit_per_type))" ;;
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
  local bronze_bucket_name="${5:-}" wrap_with_sec_fetch_lease="${6:-}"
  python3 - "$output_file" "$CLUSTER_ARN" "$task_definition_arn" "edgar-warehouse" \
    "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" "$default_command" "$cik_command" \
    "$bronze_bucket_name" "$wrap_with_sec_fetch_lease" <<'PY'
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
    bronze_bucket_name,
    wrap_with_sec_fetch_lease,
) = sys.argv[1:]

subnets = json.loads(subnet_json)
security_groups = json.loads(security_group_json)

def run_task_state(command_expression, next_state=None, is_end=False):
    s = {
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
    }
    if is_end:
        s["End"] = True
    else:
        s["Next"] = next_state
    return s


def build_sec_fetch_lease_states(acquired_next_state):
    """Cross-command sec_fetch_active lease (release-readiness ticket 84):
    gates this single-task workflow's entire run (the whole thing IS the
    fetch-heavy phase -- no MDM/gold follow-up exists in this state machine
    shape) behind the shared lease, and releases it right before the
    execution ends. No operator-alert notification, unlike daily_incremental's
    identity-refresh lease -- these are operator-triggered ad-hoc runs
    (bootstrap_full, targeted_resync), matching
    write_warehouse_mdm_gold_definition's bootstrap branch: the operator
    running one is already watching it.
    """
    def lease_task_state(command_expression, next_state=None, is_end=False):
        s = run_task_state(command_expression, next_state=next_state, is_end=is_end)
        s["Retry"][0]["IntervalSeconds"] = 30
        s["ResultPath"] = None
        return s

    acquire = lease_task_state(
        "States.Array('acquire-sec-fetch-lease', '--run-id', $$.Execution.Name)",
        next_state="ReadSecFetchLeaseResult",
    )
    release = lease_task_state(
        "States.Array('release-sec-fetch-lease', '--run-id', $$.Execution.Name)",
        is_end=True,
    )
    release["Catch"] = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLeaseFailedNonFatal"}]

    return {
        "AcquireSecFetchLease": acquire,
        "ReadSecFetchLeaseResult": {
            "Type": "Task",
            "Resource": "arn:aws:states:::aws-sdk:s3:getObject",
            "Parameters": {
                "Bucket": bronze_bucket_name,
                "Key.$": "States.Format('warehouse/bronze/reference/sec_fetch_lease/runs/{}/lease_result.json', $$.Execution.Name)",
            },
            "ResultSelector": {"parsed.$": "States.StringToJson($.Body)"},
            "ResultPath": "$.sec_fetch_lease_check",
            "Next": "SecFetchLeaseAcquiredCheck",
        },
        "SecFetchLeaseAcquiredCheck": {
            "Type": "Choice",
            "Comment": "lease_result.json (not a plain ecs:runTask.sync field) is the source of truth for whether this run holds the shared cross-command sec_fetch_active lease.",
            "Choices": [{
                "Variable": "$.sec_fetch_lease_check.parsed.lease_acquired",
                "BooleanEquals": True,
                "Next": acquired_next_state,
            }],
            "Default": "SecFetchDeferred",
        },
        "SecFetchDeferred": {
            "Type": "Pass",
            "Comment": "sec_fetch_active lease already held by another SEC-fetching command -- an explicit disposition, not an invisible skip. No SEC-fetch work started this run (release-readiness ticket 84).",
            "Parameters": {
                "disposition": "sec_fetch_deferred",
                "sec_fetch_lease_check.$": "$.sec_fetch_lease_check.parsed",
            },
            "ResultPath": "$.sec_fetch_deferred_summary",
            "End": True,
        },
        "ReleaseSecFetchLease": release,
        "ReleaseSecFetchLeaseFailedNonFatal": {
            "Type": "Pass",
            "Comment": "Release is best-effort -- a failure here must not mark an otherwise-successful run FAILED. The 16h stale-lease reclaim in acquire_pipeline_run_lease is the actual safety net for a wedged sec_fetch_active lease.",
            "End": True,
        },
        # release-readiness ticket 86: RunWarehouseTask (the whole point of
        # this state machine) had no Catch -- a real failure (e.g. an
        # immutable-object content conflict, found live during ticket 84's
        # own verification) wedged sec_fetch_active for the full 16h
        # stale-reclaim window instead of releasing promptly. Distinct from
        # ReleaseSecFetchLease above (the happy-path release, which ends the
        # execution successfully): this path always ends in Fail, so
        # ExecutionsFailed/alarm visibility for a real work failure is
        # preserved rather than silently reporting success.
        "ReleaseSecFetchLeaseAfterFailure": {
            **lease_task_state(
                "States.Array('release-sec-fetch-lease', '--run-id', $$.Execution.Name)",
                next_state="SecFetchTaskFailed",
            ),
            "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "SecFetchTaskFailed"}],
        },
        "SecFetchTaskFailed": {
            "Type": "Fail",
            "ErrorPath": "$.sec_fetch_task_error.Error",
            "CausePath": "$.sec_fetch_task_error.Cause",
        },
    }


def sec_fetch_task_catch():
    """ticket 86: shared Catch for every RunWarehouseTask variant below --
    releases sec_fetch_active promptly on a real failure instead of leaving
    it held for the 16h stale-reclaim window."""
    return [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.sec_fetch_task_error", "Next": "ReleaseSecFetchLeaseAfterFailure"}]


if wrap_with_sec_fetch_lease:
    if cik_command:
        run_default = run_task_state(default_command, next_state="ReleaseSecFetchLease")
        run_default["Catch"] = sec_fetch_task_catch()
        run_with_cik_list = run_task_state(cik_command, next_state="ReleaseSecFetchLease")
        run_with_cik_list["Catch"] = sec_fetch_task_catch()
        definition = {
            "Comment": "Run an EdgarTools warehouse workflow on ECS Fargate with an optional cik_list override, gated by the cross-command sec_fetch_active lease.",
            "StartAt": "AcquireSecFetchLease",
            "States": {
                **build_sec_fetch_lease_states("HasCikListOverride"),
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
                "RunWarehouseTaskDefault": run_default,
                "RunWarehouseTaskWithCikList": run_with_cik_list,
            },
        }
    else:
        run_wh_task = run_task_state(default_command, next_state="ReleaseSecFetchLease")
        run_wh_task["Catch"] = sec_fetch_task_catch()
        definition = {
            "Comment": "Run an EdgarTools warehouse workflow on ECS Fargate, gated by the cross-command sec_fetch_active lease.",
            "StartAt": "AcquireSecFetchLease",
            "States": {
                **build_sec_fetch_lease_states("RunWarehouseTask"),
                "RunWarehouseTask": run_wh_task,
            },
        }
elif cik_command:
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
            "RunWarehouseTaskDefault": run_task_state(default_command, is_end=True),
            "RunWarehouseTaskWithCikList": run_task_state(cik_command, is_end=True),
        },
    }
else:
    definition = {
        "Comment": "Run an EdgarTools warehouse workflow on ECS Fargate.",
        "StartAt": "RunWarehouseTask",
        "States": {"RunWarehouseTask": run_task_state(default_command, is_end=True)},
    }

pathlib.Path(output_file).write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
PY
}

write_mdm_workflow_definition() {
  local output_file="$1" task_definition_arn="$2" default_command="$3" limit_command="$4" relationship_command="${5:-}" relationship_limit_command="${6:-}" limit_per_type_command="${7:-}"
  python3 - "$output_file" "$CLUSTER_ARN" "$task_definition_arn" "edgar-warehouse" \
    "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" "$default_command" "$limit_command" "$relationship_command" "$relationship_limit_command" "$limit_per_type_command" <<'PY'
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
    limit_per_type_command,
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

if limit_per_type_command:
    # release-readiness ticket 94: additive wrap, not a rewrite -- prepend one
    # new Choice ahead of whatever definition was built above (default /
    # limit-only / relationship+limit chain), so a $.limit_per_type override
    # is checked first and everything else is completely unchanged when it's
    # absent. Only mdm_sync_graph passes a non-empty limit_per_type_command.
    definition["States"]["HasLimitPerTypeOverride"] = {
        "Type": "Choice",
        "Choices": [{
            "And": [
                {"Variable": "$.limit_per_type", "IsPresent": True},
                {"Variable": "$.limit_per_type", "IsNumeric": True},
            ],
            "Next": "RunMdmTaskWithLimitPerType",
        }],
        "Default": definition["StartAt"],
    }
    definition["States"]["RunMdmTaskWithLimitPerType"] = run_task_state(limit_per_type_command)
    definition["StartAt"] = "HasLimitPerTypeOverride"

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

def build_sec_fetch_lease_states(acquired_next_state, released_next_state):
    """Cross-command sec_fetch_active lease (release-readiness ticket 84):
    load_history is operator-triggered and ad-hoc (like bootstrap/
    bootstrap_full/targeted_resync, unlike the scheduled daily_incremental),
    so no operator-alert notification on defer -- the operator triggering it
    is already watching the run. load_history was restructured from the
    original parallel bootstrap-batch xN Map into a sequential
    (MaxConcurrency=1) windowed bootstrap-next pipeline (see the "Phased
    pipeline" comment above) -- no fan-out concern remains here; a single
    acquire/release wraps the whole real-SEC-fetching span (SeedUniverse
    through the ADV/firm-roster fetch chain), matching
    write_warehouse_mdm_gold_definition's daily_incremental branch shape
    almost exactly (this function can't share code with that one -- each is
    its own `python3 -` subprocess).
    """
    acquire = ecs_state(wh_medium_arn,
        "States.Array('acquire-sec-fetch-lease', '--run-id', $$.Execution.Name)",
        next_state="ReadSecFetchLeaseResult", retry_secs=30)
    acquire["ResultPath"] = None

    read_result = {
        "Type": "Task",
        "Resource": "arn:aws:states:::aws-sdk:s3:getObject",
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "States.Format('warehouse/bronze/reference/sec_fetch_lease/runs/{}/lease_result.json', $$.Execution.Name)",
        },
        "ResultSelector": {"parsed.$": "States.StringToJson($.Body)"},
        "ResultPath": "$.sec_fetch_lease_check",
        "Next": "SecFetchLeaseAcquiredCheck",
    }

    acquired_check = {
        "Type": "Choice",
        "Comment": "lease_result.json (not a plain ecs:runTask.sync field) is the source of truth for whether this run holds the shared cross-command sec_fetch_active lease.",
        "Choices": [
            {
                "Variable": "$.sec_fetch_lease_check.parsed.lease_acquired",
                "BooleanEquals": True,
                "Next": acquired_next_state,
            }
        ],
        "Default": "SecFetchDeferred",
    }

    release = ecs_state(wh_medium_arn,
        "States.Array('release-sec-fetch-lease', '--run-id', $$.Execution.Name)",
        next_state=released_next_state, retry_secs=30)
    release["ResultPath"] = None
    release["Catch"] = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLeaseFailedNonFatal"}]

    return {
        "AcquireSecFetchLease": acquire,
        "ReadSecFetchLeaseResult": read_result,
        "SecFetchLeaseAcquiredCheck": acquired_check,
        "SecFetchDeferred": {
            "Type": "Pass",
            "Comment": "sec_fetch_active lease already held by another SEC-fetching command -- an explicit disposition, not an invisible skip. No SEC/IAPD-fetch work started this run (release-readiness ticket 84).",
            "Parameters": {
                "disposition": "sec_fetch_deferred",
                "sec_fetch_lease_check.$": "$.sec_fetch_lease_check.parsed",
            },
            "ResultPath": "$.sec_fetch_deferred_summary",
            "End": True,
        },
        "ReleaseSecFetchLease": release,
        "ReleaseSecFetchLeaseFailedNonFatal": {
            "Type": "Pass",
            "Comment": "Release is best-effort -- a failure here must not mark an otherwise-successful run FAILED. The 16h stale-lease reclaim in acquire_pipeline_run_lease is the actual safety net for a wedged sec_fetch_active lease.",
            "Next": released_next_state,
        },
        # release-readiness ticket 86: SeedUniverse/MdmSeedUniverse/
        # ComputeWindows/Stage0CompanyIdentity/Stage1Parallel had no Catch --
        # a real failure in any of them (e.g. the immutable-object content
        # conflict found live during ticket 84's own verification) wedged
        # sec_fetch_active for the full 16h stale-reclaim window instead of
        # releasing promptly. Stage1BEntityFacts/Stage1BPerFiling/
        # Stage1BThirteenF are deliberately excluded -- AD-13 already routes
        # their failures forward to the next stage, which still reaches
        # ReleaseSecFetchLease on the happy path, so they were never
        # actually uncaught in the way this fixes. Distinct from
        # ReleaseSecFetchLease above (the happy-path release, which
        # continues into MdmRun): this path always ends in Fail, preserving
        # ExecutionsFailed/alarm visibility for a real work failure.
        "ReleaseSecFetchLeaseAfterFailure": {
            **ecs_state(wh_medium_arn,
                "States.Array('release-sec-fetch-lease', '--run-id', $$.Execution.Name)",
                next_state="SecFetchTaskFailed", retry_secs=30),
            "ResultPath": None,
            "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "SecFetchTaskFailed"}],
        },
        "SecFetchTaskFailed": {
            "Type": "Fail",
            "ErrorPath": "$.sec_fetch_task_error.Error",
            "CausePath": "$.sec_fetch_task_error.Cause",
        },
    }

def sec_fetch_task_catch():
    """ticket 86: shared Catch for load_history's currently-uncaught
    fetch-heavy-span states (SeedUniverse/MdmSeedUniverse/ComputeWindows/
    Stage0CompanyIdentity/Stage1Parallel)."""
    return [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.sec_fetch_task_error", "Next": "ReleaseSecFetchLeaseAfterFailure"}]

# Validate the optional operator repair flag before starting any ECS workload.
# An omitted value is normalized to false; malformed values fail with a named
# disposition instead of reaching a Choice state that can raise States.Runtime.
validate_force_input = {
    "Type": "Choice",
    "Comment": "Accept an omitted or boolean force input; reject every other type before workload execution.",
    "Choices": [
        {"Variable": "$.force", "IsPresent": False, "Next": "ForceDefault"},
        {"Variable": "$.force", "IsBoolean": True, "Next": "AcquireSecFetchLease"},
    ],
    "Default": "InvalidForceInput",
}
force_default = {
    "Type": "Pass",
    "Comment": "Normalize an omitted operator force input to false.",
    "Result": False,
    "ResultPath": "$.force",
    "Next": "AcquireSecFetchLease",
}
invalid_force_input = {
    "Type": "Fail",
    "Error": "InvalidForceInput",
    "Cause": "Optional execution input 'force' must be a JSON boolean when present.",
}

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
seed["Catch"] = sec_fetch_task_catch()

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
mdm_seed_universe["Catch"] = sec_fetch_task_catch()

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
    "Comment": "Route to ArtifactPolicyCheck directly when caller supplied total_cik_limit; otherwise inject the no-limit default.",
    "Choices": [
        {
            "Variable": "$.total_cik_limit",
            "IsPresent": True,
            "Next": "ArtifactPolicyCheck",
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
    "Next": "ArtifactPolicyCheck",
}

# (2c) ArtifactPolicyCheck → ArtifactPolicyDefault → ComputeWindows
# Same backward-compat pattern as WindowSizeCheck/Default above, for an optional
# $.artifact_policy SM input field passed through to per-window bootstrap-next
# (see `per_window` below). Default is 'all_attachments' — load_history is the
# canonical pipeline for loading BRAND-NEW company universes (CLAUDE.md "Load 10+
# companies"), so it must keep fetching ownership/ADV artifacts for genuinely new
# CIKs by default. A caller re-running load_history over an already-loaded universe
# purely to pick up new filings/backfill can opt in to '--artifact-policy skip' by
# passing {"artifact_policy": "skip"} explicitly — this must be an explicit choice,
# not the default, or first-time loads would silently stop capturing artifacts.
# (artifact-throttle 5-whys, see CLAUDE.md: fix #1 already makes cache-hit re-runs
# fast without this flag; this is only for callers who want to skip fetch entirely.)
artifact_policy_check = {
    "Type": "Choice",
    "Comment": "Route to FilingLookbackYearsCheck directly when caller supplied artifact_policy; otherwise inject the all_attachments default.",
    "Choices": [
        {
            "Variable": "$.artifact_policy",
            "IsPresent": True,
            "Next": "FilingLookbackYearsCheck",
        }
    ],
    "Default": "ArtifactPolicyDefault",
}

artifact_policy_default = {
    "Type": "Pass",
    "Comment": "Inject default artifact_policy='all_attachments' when caller passed {} or omitted "
               "the key, preserving artifact capture for brand-new CIKs loaded via load_history.",
    "Result": "all_attachments",
    "ResultPath": "$.artifact_policy",
    "Next": "FilingLookbackYearsCheck",
}

# (2d) FilingLookbackYearsCheck → FilingLookbackYearsDefault → ComputeWindows
# Same backward-compat pattern as WindowSizeCheck/ArtifactPolicyCheck above, for an
# optional $.filing_lookback_years SM input field passed through to per-window
# bootstrap-next (see `per_window` below). Unlike artifact_policy's default (which
# preserves full-artifact capture), the default here is 2 years -- unlike the CLI/code
# level default of 0 (disabled, used by every OTHER caller: daily_incremental,
# targeted_resync, bootstrap, etc., none of which pass this flag and are therefore
# unaffected), load_history's own default is intentionally bounded per an explicit
# operator decision (2026-08-05): general filing discovery (10-K/10-Q/8-K/DEF 14A/13F/
# ADV/etc) should not silently pull a company's entire multi-decade filing history on
# every load_history run. Still fully overridable per-execution via
# {"filing_lookback_years": N} (0 = full history, an explicit opt-in).
filing_lookback_years_check = {
    "Type": "Choice",
    "Comment": "Route to ComputeWindows directly when caller supplied filing_lookback_years; otherwise inject the 2-year default.",
    "Choices": [
        {
            "Variable": "$.filing_lookback_years",
            "IsPresent": True,
            "Next": "ComputeWindows",
        }
    ],
    "Default": "FilingLookbackYearsDefault",
}

filing_lookback_years_default = {
    "Type": "Pass",
    "Comment": "Inject default filing_lookback_years=2 when caller passed {} or omitted the key -- "
               "load_history-specific default, bounding general filing discovery. Pass "
               "{\"filing_lookback_years\": 0} explicitly for full history.",
    "Result": 2,
    "ResultPath": "$.filing_lookback_years",
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
# wh_large_arn, not wh_medium_arn (Company Identity Hydrate Elimination map,
# ticket 03): ComputeWindows already hydrated the full canonical silver.duckdb
# before this change (unchanged behavior); it now ALSO calls persist_run_manifest
# (see the compute-windows handler and its publish special-case in
# warehouse_orchestrator.py), which reads that same ~1GB+-and-growing canonical
# file fully into a Python bytes object for its immutable reference snapshot --
# an added working-set cost on top of the hydrate's own, on the exact canonical
# file whose growth already caused Stage0CompanyIdentity's live OOM. Belt-and-
# suspenders headroom, matching the same OOM-class precedent applied there and
# in gold-build-memory-reliability ticket 03's run_wh.
compute_windows = ecs_state(wh_large_arn,
    "States.Array('compute-windows', '--window-size', States.Format('{}', $.window_size), '--total-cik-limit', States.Format('{}', $.total_cik_limit), '--run-id', $$.Execution.Name)",
    next_state="Stage0CompanyIdentity")
# ComputeWindows publishes its durable window manifest to S3; its ECS result is
# not the data contract for later states. Preserve the normalized execution
# input so Stage0 and Stage1 still receive artifact_policy/force/defaults.
compute_windows["ResultPath"] = None
compute_windows["Catch"] = sec_fetch_task_catch()

# (3b) Stage0CompanyIdentity: Company Identity capture -- global reference data
# (company_tickers/company_tickers_exchange) plus per-CIK submissions.json
# metadata, decoupled from ownership (Form 3/4/5 + 13F) and ADV (Company
# Identity Pipeline wayfinder map, ticket 05). Runs BEFORE Branch A/B: the
# map's destination requires company data to land before ownership/ADV,
# since IS_INSIDER relationship derivation already depends on resolved
# Company entities (_derive_is_insider skips unresolved issuers). No
# dedicated MDM/graph stage here -- the existing MdmRun(--entity-type all)
# further down already resolves companies as part of its sweep
# (run_all() calls run_companies()), so a separate --entity-type company
# call would just redo that work.
#
# Delta-then-reduce DISTRIBUTED Map (Company Identity Hydrate Elimination map,
# ticket 03 -- superseding this stage's original windowed/offset-limit shape),
# mirroring write_warehouse_mdm_gold_definition's daily_incremental
# Stage0CompanyIdentityBounded/ReduceIdentityRefresh pair exactly: ComputeWindows
# now pre-batches the same ordered CIK list into cik_batches.jsonl (see its
# handler in warehouse_orchestrator.py) and declares those batches in a run
# manifest; each Map item runs bootstrap-fundamentals --mode company-identity
# with an explicit --cik-list + --identity-refresh-run-id, which persists only
# an immutable per-batch delta (bootstrap_fundamentals.py's identity_refresh_run_id
# branch) instead of hydrating the full canonical silver.duckdb and merging into
# it per window. A single ReduceIdentityRefresh state (below) merges the
# reference snapshot and every batch delta into canonical exactly once, before
# Stage1Parallel -- replacing 53 separate full-canonical hydrate+merge round
# trips (the live 2026-08-05 OOM's root cause) with one.
#
# Same MaxConcurrency=1 as before (all Branch A/B/Company-Identity stages write
# the same S3-backed unified silver DuckDB file -- concurrent writers risk a
# lost publish). Unlike Branch B's lenient AD-13 pattern (Stage1BEntityFacts/
# PerFiling/ThirteenF Catch and proceed on failure), this stage is STRICT like
# Branch A (ToleratedFailurePercentage=0, no Catch on the Map itself):
# silently proceeding past a company-identity failure would let ownership/MDM
# run against unresolved company data, the exact coupling problem this
# pipeline exists to untangle.
#
# Known, accepted regression from this restructuring (ticket 03's decision 4,
# deferred -- no CLI-level partial-resume shipped yet): a Stage0 failure now
# means NO batch's delta has reached canonical (ReduceIdentityRefresh never
# ran), so the entire Stage0 stage must re-run from scratch on retry --
# strictly worse than the old windowed shape, where each window published
# directly and a later window's failure left earlier windows' data durably in
# canonical. Verified AWS Step Functions Distributed Map redrive does NOT
# rescue this (ticket 04): this repo's sec_fetch_task_catch() routes every
# failure to a terminal Fail state, which AWS's own redrive semantics
# explicitly exclude from resumption.
#
# NOTE: write_warehouse_mdm_gold_definition's daily_incremental branch below
# builds the Stage0CompanyIdentityBounded/ReduceIdentityRefresh pair this shape
# was copied from -- these two functions can't share code directly (each is
# its own `python3 -` subprocess), so a shape change here (command flags,
# failure-handling policy, ItemReader key expression) must be mirrored there too.
per_batch_company_identity = ecs_state(wh_large_arn,
    "States.Array('bootstrap-fundamentals', '--mode', 'company-identity', "
    "'--cik-list', $.cik_list, '--identity-refresh-run-id', $.identity_refresh_run_id, "
    "'--run-id', $.identity_refresh_run_id)",
    is_end=True)

stage0_company_identity = {
    "Type": "Map",
    "Comment": "Stage 0: Company Identity capture, delta-then-reduce (MaxConcurrency=1, strict) -- runs before ownership/ADV so IS_INSIDER derivation sees resolved Company entities.",
    "MaxConcurrency": 1,
    "ToleratedFailurePercentage": 0,
    "ItemReader": {
        "Resource": "arn:aws:states:::s3:getObject",
        "ReaderConfig": {"InputType": "JSONL", "MaxItems": 100000},
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_batches.jsonl', $$.Execution.Name)",
        },
    },
    # ItemSelector is evaluated in the parent Map execution. Copy the parent
    # run's identity into each child input before the DISTRIBUTED processor
    # starts -- inside a child, $$.Execution.Name is the CHILD execution name,
    # not the parent's, and bootstrap_fundamentals.py hard-fails when
    # --run-id doesn't match --identity-refresh-run-id (bootstrap_fundamentals.py:86-88).
    "ItemSelector": {
        "cik_list.$": "$$.Map.Item.Value.cik_list",
        "identity_refresh_run_id.$": "$$.Execution.Name",
    },
    "ItemProcessor": {
        "ProcessorConfig": {
            "Mode": "DISTRIBUTED",
            "ExecutionType": "STANDARD",
        },
        "StartAt": "RunCompanyIdentityBatch",
        "States": {"RunCompanyIdentityBatch": per_batch_company_identity},
    },
    "ResultPath": None,
    "Next": "ReduceIdentityRefresh",
    "Catch": sec_fetch_task_catch(),
}

# large, not medium: this reducer merges the reference snapshot plus every
# Stage0CompanyIdentity batch delta (up to ~53 at load_history scale) into
# canonical sequentially in one task -- same OOM class release-readiness
# ticket 83 already found and fixed for daily_incremental's identical reducer
# (belt-and-suspenders headroom over the code-level peak-disk fix, PR #360).
reduce_identity_refresh = ecs_state(wh_large_arn,
    "States.Array('reduce-identity-refresh', '--run-id', $$.Execution.Name, '--max-attempts', '3')",
    next_state="Stage1Parallel")
# D-15 bug class (see test_fetch_and_ingest_adv_bulk_states_preserve_sm_input_
# via_result_path_null's docstring): an ecs:runTask.sync Task without
# ResultPath=null replaces $ entirely with its own ECS result, destroying
# $.artifact_policy/$.filing_lookback_years that Stage1Parallel's
# WindowedBootstrap ItemSelector reads immediately after this state.
reduce_identity_refresh["ResultPath"] = None
# The command performs the bounded reducer-only retry itself (--max-attempts).
# Step Functions must not create an additional retry envelope with a
# different budget or accidentally re-enter Map work.
reduce_identity_refresh["Retry"] = [{"ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": 1,
                                      "BackoffRate": 1.0, "MaxAttempts": 1}]
reduce_identity_refresh["Catch"] = sec_fetch_task_catch()

# (4) Stage1Parallel: Branch A ownership bootstrap. Branch B fundamentals is
# intentionally sequenced after this state because all Branch B modes now write
# the same canonical SEC silver DuckDB database as Branch A. Running two ECS
# tasks against the same S3-backed DuckDB artifact would race the hydrate/publish
# round trip and could drop whichever task published second.
#
# (4a) Branch A — WindowedBootstrap DISTRIBUTED Map.
# Per-window command: bootstrap-next --silver-only --cik-limit M --cik-offset N
# --run-id <execution-name>. Gold/Snowflake publication belongs exclusively to
# the final GoldRefresh state after every Silver/fundamentals/MDM stage.
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
    "States.Array('bootstrap-next', '--silver-only', '--cik-limit', States.Format('{}', $.window_limit), '--cik-offset', States.Format('{}', $.window_offset), '--tracking-status-filter', 'active,bootstrap_pending', '--artifact-policy', States.Format('{}', $.artifact_policy), '--filing-lookback-years', States.Format('{}', $.filing_lookback_years), '--run-id', $$.Execution.Name)",
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
    # ItemReader rows carry only the window bounds. Project the execution-level
    # artifact policy into every child input before RunWindow evaluates its
    # command expression; otherwise $.artifact_policy raises States.Runtime.
    "ItemSelector": {
        "window_offset.$": "$$.Map.Item.Value.window_offset",
        "window_limit.$": "$$.Map.Item.Value.window_limit",
        "artifact_policy.$": "$.artifact_policy",
        "filing_lookback_years.$": "$.filing_lookback_years",
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
    "Catch": sec_fetch_task_catch(),
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
    "Next": "DatasetPeriodCheck",
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
    "Next": "DatasetPeriodCheck",
}

# (4d) AdvBulkFetch stage (adv-fetch-pipeline-wiring spec, ticket 01 — ADV Pipeline map
# ticket 06 decisions 2/4): fetches new SEC/IAPD advFilingData monthly archives and
# ingests them into ADV silver, so MdmRun (which resolves adviser/fund entities as part
# of its --entity-type all sweep) always sees fresh ADV data in the same execution.
# Single ECS task pair, not a windowed Map — fetch-adv-bulk is not CIK-scoped, matching
# GoldRefresh's precedent of one task for whole-warehouse-state work.
#
# DatasetPeriodCheck/DatasetPeriodDefault mirrors ArtifactPolicyCheck/ArtifactPolicyDefault's
# existing Check-Default pattern: dataset_period is optional SM input for manual repair
# only; an absent value defaults to an empty string, which fetch-adv-bulk's own dispatch
# (warehouse_orchestrator.py) already treats identically to an omitted --dataset-period.
dataset_period_check = {
    "Type": "Choice",
    "Comment": "Route to ForceCheck directly when caller supplied dataset_period; otherwise inject the empty-string default.",
    "Choices": [
        {
            "Variable": "$.dataset_period",
            "IsPresent": True,
            "Next": "ForceCheck",
        }
    ],
    "Default": "DatasetPeriodDefault",
}

dataset_period_default = {
    "Type": "Pass",
    "Comment": "Inject default dataset_period='' when caller passed {} or omitted the key — fetch-adv-bulk auto-detects the rolling window in that case.",
    "Result": "",
    "ResultPath": "$.dataset_period",
    "Next": "ForceCheck",
}

# ForceCheck: --force is a bare boolean CLI flag (argparse action='store_true'), unlike
# artifact_policy/dataset_period which are always-present *value* flags States.Format can
# interpolate into a single command array. A boolean flag's token must be conditionally
# present or absent entirely, which States.Format cannot do within one array — so this
# branches to two literal FetchAdvBulk Task definitions instead of injecting a value.
force_check = {
    "Type": "Choice",
    "Comment": "Route to FetchAdvBulkForced (includes --force) when caller supplied force=true; otherwise FetchAdvBulk (no --force), the normal path.",
    "Choices": [
        {
            "Variable": "$.force",
            "IsPresent": False,
            "Next": "FetchAdvBulk",
        },
        {
            "Variable": "$.force",
            "BooleanEquals": True,
            "Next": "FetchAdvBulkForced",
        },
        {
            "Variable": "$.force",
            "BooleanEquals": False,
            "Next": "FetchAdvBulk",
        },
    ],
    "Default": "InvalidForceInput",
}

# Next="ReleaseSecFetchLease", not "MdmRun" directly -- these ADV/firm-roster
# fetch stages are still inside the sec_fetch_active fetch-heavy span
# (release-readiness ticket 84), so a failure here must still release the
# lease before falling through to MDM, not skip release entirely.
adv_bulk_fetch_catch = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLease"}]

fetch_adv_bulk = ecs_state(wh_medium_arn,
    "States.Array('fetch-adv-bulk', '--dataset-period', States.Format('{}', $.dataset_period), '--run-id', $$.Execution.Name)",
    next_state="IngestAdvBulkSources")
fetch_adv_bulk["Catch"] = adv_bulk_fetch_catch
# ResultPath: null preserves $.dataset_period/$.force unchanged into the next state --
# without this the ECS runTask.sync result object replaces the entire input (D-15 bug,
# see the `seed` state's comment above for the original occurrence of this class of bug).
fetch_adv_bulk["ResultPath"] = None

fetch_adv_bulk_forced = ecs_state(wh_medium_arn,
    "States.Array('fetch-adv-bulk', '--dataset-period', States.Format('{}', $.dataset_period), '--force', '--run-id', $$.Execution.Name)",
    next_state="IngestAdvBulkSources")
fetch_adv_bulk_forced["Catch"] = adv_bulk_fetch_catch
fetch_adv_bulk_forced["ResultPath"] = None

# IngestAdvBulkSources re-derives fetch-adv-bulk's manifest path independently
# (bronze_root/runs/fetch-adv-bulk/<run-id>/source_manifest.json, confirmed against
# tests/application/test_fetch_adv_bulk_command.py) rather than the state machine
# capturing FetchAdvBulk's literal output — mirroring how Stage0CompanyIdentity
# re-derives cik_windows.jsonl's S3 key the same way instead of passing it through
# execution state.
ingest_adv_bulk_sources = ecs_state(wh_medium_arn,
    "States.Array('ingest-relationship-sources', '--source-manifest', "
    f"States.Format('s3://{bronze_bucket_name}/warehouse/bronze/runs/fetch-adv-bulk/{{}}/source_manifest.json', $$.Execution.Name), "
    "'--run-id', $$.Execution.Name)",
    next_state="FirmRosterForceCheck")
ingest_adv_bulk_sources["Catch"] = adv_bulk_fetch_catch
ingest_adv_bulk_sources["ResultPath"] = None

# Firm Roster completeness cross-check (adv-firm-roster-crosscheck spec, ticket 02):
# fetch-firm-roster + ingest-relationship-sources, sharing this same Stage and the
# same $.dataset_period/$.force SM-input fields the advFilingData fetch above already
# uses -- one shared manual-repair override for the whole AdvBulkFetch stage, not a
# separate schedule. Re-checks $.force (FirmRosterForceCheck) rather than reusing
# ForceCheck's own routing, since ForceCheck already routed to FetchAdvBulk/
# FetchAdvBulkForced above and a Choice state can only have one Next per branch.
firm_roster_force_check = {
    "Type": "Choice",
    "Comment": "Route to FetchFirmRosterForced (includes --force) when caller supplied force=true; otherwise FetchFirmRoster (no --force).",
    "Choices": [
        {
            "Variable": "$.force",
            "IsPresent": False,
            "Next": "FetchFirmRoster",
        },
        {
            "Variable": "$.force",
            "BooleanEquals": True,
            "Next": "FetchFirmRosterForced",
        },
        {
            "Variable": "$.force",
            "BooleanEquals": False,
            "Next": "FetchFirmRoster",
        },
    ],
    "Default": "InvalidForceInput",
}

fetch_firm_roster = ecs_state(wh_medium_arn,
    "States.Array('fetch-firm-roster', '--dataset-period', States.Format('{}', $.dataset_period), '--run-id', $$.Execution.Name)",
    next_state="IngestFirmRosterSources")
fetch_firm_roster["Catch"] = adv_bulk_fetch_catch
fetch_firm_roster["ResultPath"] = None

fetch_firm_roster_forced = ecs_state(wh_medium_arn,
    "States.Array('fetch-firm-roster', '--dataset-period', States.Format('{}', $.dataset_period), '--force', '--run-id', $$.Execution.Name)",
    next_state="IngestFirmRosterSources")
fetch_firm_roster_forced["Catch"] = adv_bulk_fetch_catch
fetch_firm_roster_forced["ResultPath"] = None

ingest_firm_roster_sources = ecs_state(wh_medium_arn,
    "States.Array('ingest-relationship-sources', '--source-manifest', "
    f"States.Format('s3://{bronze_bucket_name}/warehouse/bronze/runs/fetch-firm-roster/{{}}/source_manifest.json', $$.Execution.Name), "
    "'--run-id', $$.Execution.Name)",
    next_state="ReleaseSecFetchLease")
ingest_firm_roster_sources["Catch"] = adv_bulk_fetch_catch
ingest_firm_roster_sources["ResultPath"] = None

# sec_fetch_active lease (release-readiness ticket 84): acquired right
# before SeedUniverse, released right before MdmRun -- spans every state
# that actually calls SEC/IAPD (SeedUniverse, Stage0CompanyIdentity, Branch
# A/B windowed bootstrap+fundamentals, and the ADV/firm-roster fetch chain).
# MdmSeedUniverse (an upsert from data SeedUniverse already fetched, no SEC
# call itself) rides inside the span since it's sandwiched between two
# fetch stages -- a few minutes of over-holding, not hours.
sec_fetch_lease_states = build_sec_fetch_lease_states("SeedUniverse", "MdmRun")

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
        "(3b) Stage0CompanyIdentity — Company Identity capture (Company Identity Pipeline "
        "wayfinder map, ticket 05), strict, runs before ownership/ADV so IS_INSIDER derivation "
        "sees resolved Company entities, "
        "(4) Stage1Parallel — Branch A ownership (bootstrap-next) writes unified SEC silver, "
        "(4b) Stage1BEntityFacts then (4c) Stage1BPerFiling then Stage1BThirteenF — Branch B "
        "fundamentals modes run sequentially after Branch A because they share the same silver "
        "DuckDB artifact; Branch B failures are caught so the pipeline still advances (AD-13), "
        "(4d) AdvBulkFetch — fetch-adv-bulk + ingest-relationship-sources (adv-fetch-pipeline-"
        "wiring spec), then fetch-firm-roster + ingest-relationship-sources (adv-firm-roster-"
        "crosscheck spec, ticket 02), both lenient like Branch B, so MDM sees fresh ADV silver "
        "and the Firm Roster completeness cross-check stays current in this execution, "
        "(5) MDM entity resolution + export to Snowflake mirror + Neo4j sync in bulk "
        "(data-architecture Issue 3: export precedes sync-graph so graph reflects this run), "
        "(6) single gold build + Snowflake export manifest, "
        "(7) write run-summary.json with window_count and cik_count from S3 manifests. "
        "Implements CHUNK-02 (sequential windowed SM) and CHUNK-04 SM-side."
    ),
    "StartAt": "ValidateForceInput",
    "States": {
        "ValidateForceInput": validate_force_input,
        "ForceDefault":       force_default,
        "InvalidForceInput":  invalid_force_input,
        **sec_fetch_lease_states,
        "SeedUniverse":      seed,
        "MdmSeedUniverse":   mdm_seed_universe,
        "WindowSizeCheck":   window_size_check,
        "WindowSizeDefault": window_size_default,
        "TotalCikLimitCheck":   total_cik_limit_check,
        "TotalCikLimitDefault": total_cik_limit_default,
        "ArtifactPolicyCheck":   artifact_policy_check,
        "ArtifactPolicyDefault": artifact_policy_default,
        "FilingLookbackYearsCheck":   filing_lookback_years_check,
        "FilingLookbackYearsDefault": filing_lookback_years_default,
        "ComputeWindows":    compute_windows,
        "Stage0CompanyIdentity": stage0_company_identity,
        "ReduceIdentityRefresh": reduce_identity_refresh,
        "Stage1Parallel":    stage1_parallel,
        "Stage1BEntityFacts": fundamentals_entity_facts,
        "Stage1BPerFiling":  fundamentals_per_filing,
        "Stage1BThirteenF":  fundamentals_thirteenf,
        "DatasetPeriodCheck":   dataset_period_check,
        "DatasetPeriodDefault": dataset_period_default,
        "ForceCheck":           force_check,
        "FetchAdvBulk":         fetch_adv_bulk,
        "FetchAdvBulkForced":   fetch_adv_bulk_forced,
        "IngestAdvBulkSources": ingest_adv_bulk_sources,
        "FirmRosterForceCheck":     firm_roster_force_check,
        "FetchFirmRoster":          fetch_firm_roster,
        "FetchFirmRosterForced":    fetch_firm_roster_forced,
        "IngestFirmRosterSources":  ingest_firm_roster_sources,
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
  local bronze_bucket_name="$7"   # daily_incremental's Stage0CompanyIdentity ItemReader
  local operator_alert_topic_arn="$8" # daily_incremental deferral notification target

  python3 - "$output_file" "$CLUSTER_ARN" \
    "$wh_task_medium_arn" "$mdm_task_small_arn" "$mdm_task_medium_arn" "$wh_task_large_arn" \
    "edgar-warehouse" "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" \
    "$MDM_RUN_LIMIT" "$MDM_GRAPH_LIMIT" "$workflow_name" "$bronze_bucket_name" \
    "$operator_alert_topic_arn" <<'PY'
import json, pathlib, sys

(output_file, cluster_arn,
 wh_medium_arn, mdm_small_arn, mdm_medium_arn, wh_large_arn,
 container_name, subnet_json, security_group_json,
 mdm_run_limit, mdm_graph_limit, workflow_name, bronze_bucket_name,
 operator_alert_topic_arn) = sys.argv[1:]

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

# wh_large_arn, not wh_medium_arn (2026-07-30, gold-build-memory-reliability ticket 03):
# this is the state that actually runs `bootstrap`/`daily-incremental` themselves --
# both are in GOLD_AFFECTING_COMMANDS (they do bronze+silver+gold in one command) and
# this exact step, on wh_medium_arn, is what OOM-killed daily_incremental in prod
# (task-def edgartools-prod-medium:92, 4096MB, mid-sec_thirteenf_holding). Note this
# workflow's task profile was NEVER resolved via workflow_profile() -- that function's
# daily_incremental/bootstrap cases are dead code, since write_warehouse_mdm_gold_definition
# (this function) builds their state machines directly and was never wired through it.
run_wh = ecs_state(wh_large_arn,
    f"States.Array('{wh_cmd}', '--run-id', $$.Execution.Name)",
    next_state="MdmRun")
if workflow_name == "daily_incremental":
    # Scheduled daily/backstop runs must derive filing candidates from an exact,
    # freshly forced index union. Identity selection remains independently scoped.
    run_wh["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"] = (
        "States.Array('daily-incremental', '--recurring-index-lookback-days', '7', "
        "'--run-id', $$.Execution.Name)"
    )
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

def build_sec_fetch_lease_states(acquired_next_state, released_next_state):
    """Cross-command sec_fetch_active lease (release-readiness ticket 84,
    implementing ticket 80's Phase 1 primitive) -- prevents this command's
    SEC/IAPD-fetching phase from running concurrently with any of the other
    4 SEC-fetching commands platform-wide. Mirrors the identity-refresh
    lease pattern's shape (AcquireLease/ReadLeaseResult/LeaseAcquiredCheck/
    Deferred/ReleaseLease/ReleaseLeaseFailedNonFatal) but is deliberately a
    defer-and-terminate disposition, not a polling wait: an operator-
    triggered ad-hoc run (bootstrap) relies on the operator re-triggering
    once free, matching how these commands are already operated today (no
    auto-retry exists for their failures either); the scheduled
    daily_incremental relies on its own next scheduled slot, same as its
    existing identity-refresh lease. No mode/backstop concept, unlike the
    identity-refresh lease -- a caller either gets the lease or is deferred.
    Notification-on-defer is conditional on operator_alert_topic_arn being
    non-empty (only daily_incremental currently supplies one; ad-hoc
    commands' operators are already watching their own run).
    """
    acquire = ecs_state(wh_medium_arn,
        "States.Array('acquire-sec-fetch-lease', '--run-id', $$.Execution.Name)",
        next_state="ReadSecFetchLeaseResult", retry_secs=30)
    acquire["ResultPath"] = None

    read_result = {
        "Type": "Task",
        "Resource": "arn:aws:states:::aws-sdk:s3:getObject",
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "States.Format('warehouse/bronze/reference/sec_fetch_lease/runs/{}/lease_result.json', $$.Execution.Name)",
        },
        "ResultSelector": {"parsed.$": "States.StringToJson($.Body)"},
        "ResultPath": "$.sec_fetch_lease_check",
        "Next": "SecFetchLeaseAcquiredCheck",
    }

    acquired_check = {
        "Type": "Choice",
        "Comment": "lease_result.json (not a plain ecs:runTask.sync field) is the source of truth for whether this run holds the shared cross-command sec_fetch_active lease.",
        "Choices": [
            {
                "Variable": "$.sec_fetch_lease_check.parsed.lease_acquired",
                "BooleanEquals": True,
                "Next": acquired_next_state,
            }
        ],
        "Default": "NotifySecFetchDeferred" if operator_alert_topic_arn else "SecFetchDeferred",
    }

    states = {
        "AcquireSecFetchLease": acquire,
        "ReadSecFetchLeaseResult": read_result,
        "SecFetchLeaseAcquiredCheck": acquired_check,
        "SecFetchDeferred": {
            "Type": "Pass",
            "Comment": "sec_fetch_active lease already held by another SEC-fetching command -- an explicit disposition, not an invisible skip. No SEC/IAPD-fetch work started this run (release-readiness ticket 84).",
            "Parameters": {
                "disposition": "sec_fetch_deferred",
                "sec_fetch_lease_check.$": "$.sec_fetch_lease_check.parsed",
            },
            "ResultPath": "$.sec_fetch_deferred_summary",
            "End": True,
        },
    }
    if operator_alert_topic_arn:
        states["NotifySecFetchDeferred"] = {
            "Type": "Task",
            "Comment": "Notify the AWS Operator for every sec_fetch_active lease-busy slot before returning the explicit deferred disposition. A delivery failure is not relabeled as a benign defer.",
            "Resource": "arn:aws:states:::sns:publish",
            "Parameters": {
                "TopicArn": operator_alert_topic_arn,
                "Subject": f"EdgarTools {display} deferred (sec-fetch lease busy)",
                "Message.$": "States.JsonToString($.sec_fetch_lease_check.parsed)",
            },
            "ResultPath": None,
            "Retry": [{
                "ErrorEquals": ["States.TaskFailed"],
                "IntervalSeconds": 5,
                "BackoffRate": 2.0,
                "MaxAttempts": 3,
            }],
            "Next": "SecFetchDeferred",
        }

    release = ecs_state(wh_medium_arn,
        "States.Array('release-sec-fetch-lease', '--run-id', $$.Execution.Name)",
        next_state=released_next_state, retry_secs=30)
    release["ResultPath"] = None
    release["Catch"] = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLeaseFailedNonFatal"}]
    states["ReleaseSecFetchLease"] = release
    states["ReleaseSecFetchLeaseFailedNonFatal"] = {
        "Type": "Pass",
        "Comment": "Release is best-effort -- a failure here must not mark an otherwise-successful run FAILED. The 16h stale-lease reclaim in acquire_pipeline_run_lease is the actual safety net for a wedged sec_fetch_active lease.",
        "Next": released_next_state,
    }

    # release-readiness ticket 86: a real failure inside the fetch-heavy span
    # (found live -- an immutable-object content conflict wedged this exact
    # lease during ticket 84's own verification) must still release
    # sec_fetch_active promptly instead of leaving it held for the full 16h
    # stale-reclaim window, unlike the identity-refresh lease's established
    # "release is best-effort" convention -- sec_fetch_active is shared
    # across all 5 SEC-fetching commands, so a wedge here blocks all of them,
    # not just this command's own next run. Distinct from
    # ReleaseSecFetchLease/ReleaseSecFetchLeaseFailedNonFatal above (the
    # happy-path release, which continues the pipeline into MDM/gold): this
    # path always ends in Fail, preserving ExecutionsFailed/alarm visibility
    # for a real work failure instead of silently reporting success.
    release_after_failure = ecs_state(wh_medium_arn,
        "States.Array('release-sec-fetch-lease', '--run-id', $$.Execution.Name)",
        next_state="SecFetchTaskFailed", retry_secs=30)
    release_after_failure["ResultPath"] = None
    release_after_failure["Catch"] = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "SecFetchTaskFailed"}]
    states["ReleaseSecFetchLeaseAfterFailure"] = release_after_failure
    states["SecFetchTaskFailed"] = {
        "Type": "Fail",
        "ErrorPath": "$.sec_fetch_task_error.Error",
        "CausePath": "$.sec_fetch_task_error.Cause",
    }
    return states


def sec_fetch_task_catch():
    """Ticket 86's shared Catch clause -- attach to every currently-uncaught
    Task/Map state inside the sec_fetch_active fetch-heavy span so a real
    failure releases the lease promptly instead of leaving it held for the
    16h stale-reclaim window."""
    return [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.sec_fetch_task_error", "Next": "ReleaseSecFetchLeaseAfterFailure"}]

# All workflows except daily_incremental seed the universe first so any
# bootstrap_pending CIKs are enrolled before the main pipeline step runs.
if workflow_name != "daily_incremental":
    seed_universe = ecs_state(wh_medium_arn,
        "States.Array('seed-universe', '--run-id', $$.Execution.Name)",
        next_state="RunWarehouseTask", retry_secs=60)
    # sec_fetch_active lease (release-readiness ticket 84): SeedUniverse
    # (fetches company_tickers.json from SEC) and RunWarehouseTask (the
    # actual bootstrap SEC-fetch loop) are the fetch-heavy span; MDM/gold
    # never call SEC, so the lease releases right before MdmRun.
    run_wh["Next"] = "ReleaseSecFetchLease"
    # ticket 86: both states were previously uncaught -- a failure in
    # either wedged sec_fetch_active for the full 16h stale-reclaim window.
    seed_universe["Catch"] = sec_fetch_task_catch()
    run_wh["Catch"] = sec_fetch_task_catch()
    sec_fetch_lease_states = build_sec_fetch_lease_states("SeedUniverse", "MdmRun")
    definition = {
        "Comment": (
            f"{display}: (0) acquire cross-command sec_fetch_active lease, (0b) seed universe, "
            "(1) bronze+silver capture, (1b) release sec_fetch_active lease, "
            "(2) MDM entity resolution + Neo4j sync, (3) gold build + Snowflake export manifest."
        ),
        "StartAt": "AcquireSecFetchLease",
        "States": {
            **sec_fetch_lease_states,
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
    # Stage0CompanyIdentityBounded: Company Identity Pipeline wayfinder map,
    # ticket 06. A strict, MaxConcurrency=1, delta-then-reduce Map --
    # bootstrap-fundamentals --mode company-identity over explicit
    # --cik-list batches (compute-identity-refresh-window's cik_batches.jsonl),
    # each persisting only an immutable delta, merged into canonical exactly
    # once by ReduceIdentityRefresh below -- ahead of the existing
    # RunWarehouseTask/MDM chain, so company data is current before the
    # existing mdm-run(--entity-type all) resolves companies as part of its
    # sweep (run_all() calls run_companies()) -- no separate --entity-type
    # company call needed. daily_incremental had zero prod executions ever
    # (confirmed via list-executions) as of ticket 06, so this was a clean
    # restructure, not a migration of live behavior.
    #
    # No SeedUniverse/MdmSeedUniverse here, matching daily_incremental's
    # existing choice to skip seed-universe entirely -- it processes the
    # already-tracked universe for daily updates, not newly-discovered CIKs.
    # batch_size is a fixed literal (not SM-input-configurable like
    # load_history's WindowSizeCheck/TotalCikLimitCheck): daily_incremental is
    # a scheduled job that always runs the same shape, unlike load_history's
    # operator-triggered, variously-scoped ad-hoc runs.
    #
    # NOTE: write_load_history_definition's Stage0CompanyIdentity (Company
    # Identity Hydrate Elimination map, ticket 03) was restructured to this
    # same delta-then-reduce shape -- these two functions can't share code
    # directly (each is its own `python3 -` subprocess), so a shape change
    # here (command flags, failure-handling policy, ItemReader key
    # expression) must be mirrored there too.
    #
    # refresh_mode (release-readiness ticket 45/49, "Decide whether/how to
    # narrow daily_incremental's Stage 0"): the full-universe ComputeWindows ->
    # Stage0CompanyIdentity pair below took 10h16m alone on the first-ever prod
    # execution (ticket 45's evidence), because it reprocesses the entire
    # ~26,300-CIK tracked universe every run instead of just the CIKs that
    # actually filed something recently. RefreshMode branches on
    # $.refresh_mode: "backstop" selects the complete active company-eligible
    # universe (the weekly Identity Backstop Sweep); the default "daily" path
    # intersects the trailing 7 days' impacted CIKs with that same bounded
    # universe. Both use the explicit-CIK Stage 0 Map and converge on
    # RunWarehouseTask.
    #
    # AcquireLease/ReleaseLease (release-readiness ticket 49, go-live follow-up):
    # a run-level lease shared by the Daily Identity Refresh and the Identity
    # Backstop Sweep so they never run concurrently. ecs:runTask.sync doesn't
    # surface app-level stdout/metrics to a Choice state, so the acquire
    # command writes lease_result.json to S3 (bronze root) as its source of
    # truth; ReadLeaseResult reads it back via the aws-sdk:s3:getObject
    # service integration and States.StringToJson, and LeaseAcquiredCheck
    # branches on the parsed lease_acquired boolean. An explicit
    # lease_acquired=false routes to Deferred -- an explicit terminal state,
    # not an invisible skip -- and starts no downstream data work.
    #
    # NOTE (deliberate, found sharp in code review): ReadLeaseResult has no
    # Retry/Catch. A missing or corrupt lease_result.json (S3 write failure,
    # object not found) fails the Task outright -- it does NOT fall through
    # to Deferred. This is intentional: "lease busy" (a benign, expected
    # outcome) and "something is actually broken" (an unknown failure mode)
    # are different dispositions, and silently treating the latter as the
    # former would mask real bugs behind a falsely reassuring "deferred, all
    # good" event. An unreadable lease result fails the execution loudly
    # instead.
    #
    # Stale-lease reclaim (20h -- 2h of margin past the Identity Backstop
    # Sweep's own 18h completion/alarm bound, so a new run's acquire can't
    # race a legitimately-still-finishing backstop mid-ReleaseLease) lives in
    # acquire_pipeline_run_lease itself (silver_store.py), not here, so a
    # crashed run can't wedge the schedule permanently -- release-on-failure
    # elsewhere in this chain is therefore best-effort, not wrapped in Catch
    # on every downstream state.
    validate_force_input = {
        "Type": "Choice",
        "Comment": "Accept an omitted or boolean force input; reject every other type before workload execution.",
        "Choices": [
            {"Variable": "$.force", "IsPresent": False, "Next": "ForceDefault"},
            {"Variable": "$.force", "IsBoolean": True, "Next": "RefreshModeCheck"},
        ],
        "Default": "InvalidForceInput",
    }
    force_default = {
        "Type": "Pass",
        "Comment": "Normalize an omitted operator force input to false.",
        "Result": False,
        "ResultPath": "$.force",
        "Next": "RefreshModeCheck",
    }
    invalid_force_input = {
        "Type": "Fail",
        "Error": "InvalidForceInput",
        "Cause": "Optional execution input 'force' must be a JSON boolean when present.",
    }

    refresh_mode_check = {
        "Type": "Choice",
        "Comment": "Route to AcquireLease directly when caller supplied refresh_mode; otherwise inject the 'daily' default.",
        "Choices": [
            {
                "Variable": "$.refresh_mode",
                "IsPresent": True,
                "Next": "AcquireLease",
            }
        ],
        "Default": "RefreshModeDefault",
    }
    refresh_mode_default = {
        "Type": "Pass",
        "Comment": "Inject default refresh_mode='daily' when caller passed {} or omitted the key.",
        "Result": "daily",
        "ResultPath": "$.refresh_mode",
        "Next": "AcquireLease",
    }

    acquire_lease = ecs_state(wh_medium_arn,
        "States.Array('acquire-identity-refresh-lease', '--mode', States.Format('{}', $.refresh_mode), "
        "'--run-id', $$.Execution.Name)",
        next_state="ReadLeaseResult", retry_secs=30)
    acquire_lease["ResultPath"] = None

    read_lease_result = {
        "Type": "Task",
        "Resource": "arn:aws:states:::aws-sdk:s3:getObject",
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "States.Format('warehouse/bronze/reference/identity_refresh_lease/runs/{}/lease_result.json', $$.Execution.Name)",
        },
        "ResultSelector": {"parsed.$": "States.StringToJson($.Body)"},
        "ResultPath": "$.lease_check",
        "Next": "LeaseAcquiredCheck",
    }

    lease_acquired_check = {
        "Type": "Choice",
        "Comment": "lease_result.json (not a plain ecs:runTask.sync field) is the source of truth for whether this run holds the shared Daily Identity Refresh / Identity Backstop Sweep lease.",
        "Choices": [
            {
                "Variable": "$.lease_check.parsed.lease_acquired",
                "BooleanEquals": True,
                "Next": "ApplyEffectiveRefreshMode",
            }
        ],
        "Default": "NotifyDeferred",
    }

    notify_deferred = {
        "Type": "Task",
        "Comment": "Notify the AWS Operator for every lease-busy slot before returning the explicit deferred disposition. A delivery failure is not relabeled as a benign defer.",
        "Resource": "arn:aws:states:::sns:publish",
        "Parameters": {
            "TopicArn": operator_alert_topic_arn,
            "Subject": "EdgarTools Daily Identity Refresh deferred",
            "Message.$": "States.JsonToString($.lease_check.parsed)",
        },
        "ResultPath": None,
        "Retry": [{
            "ErrorEquals": ["States.TaskFailed"],
            "IntervalSeconds": 5,
            "BackoffRate": 2.0,
            "MaxAttempts": 3,
        }],
        "Next": "Deferred",
    }

    apply_effective_refresh_mode = {
        "Type": "Pass",
        "Comment": "Overwrite $.refresh_mode with the lease-resolved effective mode. An overdue backstop (persisted on pipeline_run_lease.backstop_overdue, set when a prior 'backstop' attempt was deferred) takes priority over whatever this trigger's own regular schedule slot requested (release-readiness ticket 45's 'prioritize the next available slot' requirement) -- acquire-identity-refresh-lease resolves that server-side and lease_result.json carries the resolved value, not the raw trigger payload, so RefreshMode's dispatch below must read from there instead of the original $.refresh_mode.",
        "InputPath": "$.lease_check.parsed.mode",
        "ResultPath": "$.refresh_mode",
        "Next": "AcquireSecFetchLease",
    }

    deferred = {
        "Type": "Pass",
        "Comment": "Lease already held by another run -- an explicit disposition, not an invisible skip. No downstream data work started; the next successful refresh catches up filing-signaled work (release-readiness ticket 45).",
        # A labeled top-level field, not just app-level events buried in
        # CloudWatch: an operator glancing at this execution's own output in
        # the Step Functions console sees why it stopped without digging.
        "Parameters": {
            "disposition": "deferred",
            "lease_check.$": "$.lease_check.parsed",
        },
        "ResultPath": "$.deferred_summary",
        "End": True,
    }

    # large, not medium (release-readiness ticket 89): a real prod run's
    # ReleaseLease OOM-killed (exit 137) on medium's 4096MB on all 4
    # attempts, right after ReduceIdentityRefresh/GoldRefresh had just made
    # canonical heavier within the same run -- same root cause ticket 83
    # already fixed for ReduceIdentityRefresh above. The Catch below only
    # stops that from failing an otherwise-successful gold build; it does
    # not make the release succeed, so every retry left the lease
    # permanently held with no visible error (execution still SUCCEEDED).
    release_lease = ecs_state(wh_large_arn,
        "States.Array('release-identity-refresh-lease', '--run-id', $$.Execution.Name)",
        is_end=True, retry_secs=30)
    release_lease["Catch"] = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseLeaseFailedNonFatal"}]

    release_lease_failed_non_fatal = {
        "Type": "Pass",
        "Comment": "Release is best-effort -- a failure here must not mark an otherwise-successful gold build FAILED. The 18h stale-lease reclaim in acquire_pipeline_run_lease is the actual safety net for a wedged lease.",
        "End": True,
    }

    # GoldRefresh (`gold`, built above) is shared with the bootstrap branch's
    # standalone definition, which is_end=True there. Mutating it here is
    # safe: this Python process only ever executes one of the if/else
    # branches per invocation (see run_wh["Next"] retarget above, same
    # pattern), so bootstrap's own use of `gold` is never affected.
    del gold["End"]
    gold["Next"] = "ReleaseLease"
    refresh_mode = {
        "Type": "Choice",
        "Comment": "Both scheduled identity modes use the active operating-or-current-SEC-ticker universe: backstop selects the complete eligible set; daily intersects it with the trailing index window.",
        "Choices": [
            {
                "Variable": "$.refresh_mode",
                "StringEquals": "backstop",
                "Next": "ComputeIdentityBackstopUniverse",
            }
        ],
        "Default": "ComputeIdentityRefreshWindow",
    }

    compute_identity_refresh_window = ecs_state(wh_medium_arn,
        "States.Array('compute-identity-refresh-window', '--mode', 'daily', "
        "'--lookback-days', '7', "
        "'--batch-size', '500', '--run-id', $$.Execution.Name)",
        next_state="Stage0CompanyIdentityBounded")
    compute_identity_refresh_window["ResultPath"] = None
    # ticket 86: previously uncaught -- these states, plus
    # Stage0CompanyIdentityBounded/ReduceIdentityRefresh/RunWarehouseTask
    # below, are all inside the sec_fetch_active fetch-heavy span with no
    # release-on-failure path before this fix.
    compute_identity_refresh_window["Catch"] = sec_fetch_task_catch()

    compute_identity_backstop_universe = ecs_state(wh_medium_arn,
        "States.Array('compute-identity-refresh-window', '--mode', 'backstop', "
        "'--batch-size', '500', '--run-id', $$.Execution.Name)",
        next_state="Stage0CompanyIdentityBounded")
    compute_identity_backstop_universe["ResultPath"] = None
    compute_identity_backstop_universe["Catch"] = sec_fetch_task_catch()

    per_batch_company_identity = ecs_state(wh_medium_arn,
        "States.Array('bootstrap-fundamentals', '--mode', 'company-identity', "
        "'--cik-list', $.cik_list, '--identity-refresh-run-id', $.identity_refresh_run_id, "
        "'--run-id', $.identity_refresh_run_id)",
        is_end=True)

    # large, not medium (release-readiness ticket 83): a real prod run was
    # OOM-killed (exit 137) on medium's 4096MB mid-merge on the largest
    # protected table, even after the code-level fix (this same ticket)
    # that stopped holding every verified candidate as Python bytes for the
    # whole reducer call. Belt-and-suspenders headroom, matching the
    # gold-build-memory-reliability precedent's RunWarehouseTask move.
    reduce_identity_refresh = ecs_state(wh_large_arn,
        "States.Array('reduce-identity-refresh', '--run-id', $$.Execution.Name, '--max-attempts', '3')",
        next_state="RunWarehouseTask")
    # The command performs the bounded reducer-only retry itself. Step
    # Functions must not create an additional retry envelope with a different
    # budget or accidentally re-enter Map work.
    reduce_identity_refresh["Retry"] = [{"ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": 1,
                                          "BackoffRate": 1.0, "MaxAttempts": 1}]
    reduce_identity_refresh["Catch"] = sec_fetch_task_catch()

    stage0_company_identity_bounded = {
        "Type": "Map",
        "Comment": "Stage 0 scheduled company identity: explicit CIK batches already bounded by the shared active operating-or-current-SEC-ticker eligibility contract.",
        "MaxConcurrency": 1,
        "ToleratedFailurePercentage": 0,
        "ItemReader": {
            "Resource": "arn:aws:states:::s3:getObject",
            "ReaderConfig": {"InputType": "JSONL", "MaxItems": 100000},
            "Parameters": {
                "Bucket": bronze_bucket_name,
                "Key.$": "States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_batches.jsonl', $$.Execution.Name)",
            },
        },
        # ItemSelector is evaluated in the parent Map execution. Copy the
        # parent daily-run identity into each child input before the
        # DISTRIBUTED processor starts; inside a child, $$.Execution.Name is
        # the child execution name and cannot address the parent's run plan.
        "ItemSelector": {
            "cik_list.$": "$$.Map.Item.Value.cik_list",
            "identity_refresh_run_id.$": "$$.Execution.Name",
        },
        "ItemProcessor": {
            "ProcessorConfig": {"Mode": "DISTRIBUTED", "ExecutionType": "STANDARD"},
            "StartAt": "RunCompanyIdentityBatch",
            "States": {"RunCompanyIdentityBatch": per_batch_company_identity},
        },
        "ResultPath": None,
        "Next": "ReduceIdentityRefresh",
        "Catch": sec_fetch_task_catch(),
    }

    # AdvBulkFetch stage (adv-fetch-pipeline-wiring spec, ticket 02 — ADV Pipeline map
    # ticket 06 decisions 2/4), inserted between RunWarehouseTask and MdmRun. Identical
    # shape to write_load_history_definition's own AdvBulkFetch stage (same "keep in
    # sync" duplication convention Stage0CompanyIdentity already established for this
    # file) — see that function's comments for the full rationale. run_wh was built
    # above with Next="MdmRun" for the shared bootstrap/daily_incremental case; retarget
    # it here since this branch only executes for daily_incremental.
    run_wh["Next"] = "DatasetPeriodCheck"
    run_wh["ResultPath"] = None
    run_wh["Catch"] = sec_fetch_task_catch()

    dataset_period_check = {
        "Type": "Choice",
        "Comment": "Route to ForceCheck directly when caller supplied dataset_period; otherwise inject the empty-string default.",
        "Choices": [
            {
                "Variable": "$.dataset_period",
                "IsPresent": True,
                "Next": "ForceCheck",
            }
        ],
        "Default": "DatasetPeriodDefault",
    }

    dataset_period_default = {
        "Type": "Pass",
        "Comment": "Inject default dataset_period='' when caller passed {} or omitted the key — fetch-adv-bulk auto-detects the rolling window in that case.",
        "Result": "",
        "ResultPath": "$.dataset_period",
        "Next": "ForceCheck",
    }

    force_check = {
        "Type": "Choice",
        "Comment": "Route to FetchAdvBulkForced (includes --force) when caller supplied force=true; otherwise FetchAdvBulk (no --force), the normal path.",
        "Choices": [
            {
                "Variable": "$.force",
                "IsPresent": False,
                "Next": "FetchAdvBulk",
            },
            {
                "Variable": "$.force",
                "BooleanEquals": True,
                "Next": "FetchAdvBulkForced",
            },
            {
                "Variable": "$.force",
                "BooleanEquals": False,
                "Next": "FetchAdvBulk",
            },
        ],
        "Default": "InvalidForceInput",
    }

    # Next="ReleaseSecFetchLease", not "MdmRun" directly -- these ADV/firm-roster
    # fetch stages are still inside the sec_fetch_active fetch-heavy span
    # (release-readiness ticket 84), so a failure here must still release the
    # lease before falling through to MDM, not skip release entirely.
    adv_bulk_fetch_catch = [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLease"}]

    fetch_adv_bulk = ecs_state(wh_medium_arn,
        "States.Array('fetch-adv-bulk', '--dataset-period', States.Format('{}', $.dataset_period), '--run-id', $$.Execution.Name)",
        next_state="IngestAdvBulkSources")
    fetch_adv_bulk["Catch"] = adv_bulk_fetch_catch
    fetch_adv_bulk["ResultPath"] = None

    fetch_adv_bulk_forced = ecs_state(wh_medium_arn,
        "States.Array('fetch-adv-bulk', '--dataset-period', States.Format('{}', $.dataset_period), '--force', '--run-id', $$.Execution.Name)",
        next_state="IngestAdvBulkSources")
    fetch_adv_bulk_forced["Catch"] = adv_bulk_fetch_catch
    fetch_adv_bulk_forced["ResultPath"] = None

    ingest_adv_bulk_sources = ecs_state(wh_medium_arn,
        "States.Array('ingest-relationship-sources', '--source-manifest', "
        f"States.Format('s3://{bronze_bucket_name}/warehouse/bronze/runs/fetch-adv-bulk/{{}}/source_manifest.json', $$.Execution.Name), "
        "'--run-id', $$.Execution.Name)",
        next_state="FirmRosterForceCheck")
    ingest_adv_bulk_sources["Catch"] = adv_bulk_fetch_catch
    ingest_adv_bulk_sources["ResultPath"] = None

    # Firm Roster completeness cross-check (adv-firm-roster-crosscheck spec, ticket 02) --
    # same shape/rationale as load_history's copy above (kept in sync per this file's
    # documented Stage0CompanyIdentity duplication convention).
    firm_roster_force_check = {
        "Type": "Choice",
        "Comment": "Route to FetchFirmRosterForced (includes --force) when caller supplied force=true; otherwise FetchFirmRoster (no --force).",
        "Choices": [
            {
                "Variable": "$.force",
                "IsPresent": False,
                "Next": "FetchFirmRoster",
            },
            {
                "Variable": "$.force",
                "BooleanEquals": True,
                "Next": "FetchFirmRosterForced",
            },
            {
                "Variable": "$.force",
                "BooleanEquals": False,
                "Next": "FetchFirmRoster",
            },
        ],
        "Default": "InvalidForceInput",
    }

    fetch_firm_roster = ecs_state(wh_medium_arn,
        "States.Array('fetch-firm-roster', '--dataset-period', States.Format('{}', $.dataset_period), '--run-id', $$.Execution.Name)",
        next_state="IngestFirmRosterSources")
    fetch_firm_roster["Catch"] = adv_bulk_fetch_catch
    fetch_firm_roster["ResultPath"] = None

    fetch_firm_roster_forced = ecs_state(wh_medium_arn,
        "States.Array('fetch-firm-roster', '--dataset-period', States.Format('{}', $.dataset_period), '--force', '--run-id', $$.Execution.Name)",
        next_state="IngestFirmRosterSources")
    fetch_firm_roster_forced["Catch"] = adv_bulk_fetch_catch
    fetch_firm_roster_forced["ResultPath"] = None

    ingest_firm_roster_sources = ecs_state(wh_medium_arn,
        "States.Array('ingest-relationship-sources', '--source-manifest', "
        f"States.Format('s3://{bronze_bucket_name}/warehouse/bronze/runs/fetch-firm-roster/{{}}/source_manifest.json', $$.Execution.Name), "
        "'--run-id', $$.Execution.Name)",
        next_state="ReleaseSecFetchLease")
    ingest_firm_roster_sources["Catch"] = adv_bulk_fetch_catch
    ingest_firm_roster_sources["ResultPath"] = None

    # sec_fetch_active lease (release-readiness ticket 84): acquired right
    # before RefreshMode dispatch, released right before MdmRun -- spans
    # every state that actually calls SEC/IAPD (identity-window compute,
    # Stage0CompanyIdentityBounded, ReduceIdentityRefresh [no SEC calls
    # itself, but sandwiched between two fetch stages], RunWarehouseTask,
    # and the ADV/firm-roster fetch chain). Independent of AcquireLease/
    # ReleaseLease above -- that lease prevents overlapping daily_incremental/
    # backstop runs of THIS command; this one prevents concurrent SEC/IAPD
    # traffic ACROSS the 5 different SEC-fetching commands.
    sec_fetch_lease_states = build_sec_fetch_lease_states("RefreshMode", "MdmRun")

    definition = {
        "Comment": (
            f"{display}: (0) RefreshMode -- backstop (complete company-eligible universe, weekly) vs "
            "daily (index-impacted company-eligible intersection, default), both emitted by "
            "compute-identity-refresh-window -- release-readiness ticket 45/49/51, "
            "(0a) AcquireSecFetchLease -- cross-command sec_fetch_active lease (ticket 84), "
            "(0b) Stage0CompanyIdentityBounded -- Company Identity capture, strict, runs "
            "before ownership/ADV so IS_INSIDER derivation sees resolved Company entities, "
            "(1) bronze+silver capture, (1a) ReleaseSecFetchLease, (1b) AdvBulkFetch -- fetch-adv-bulk + "
            "ingest-relationship-sources (adv-fetch-pipeline-wiring spec), then fetch-firm-roster "
            "+ ingest-relationship-sources (adv-firm-roster-crosscheck spec, ticket 02), both "
            "lenient, so MDM sees fresh ADV silver and the Firm Roster cross-check stays current, "
            "(2) MDM entity resolution + Neo4j sync, (3) gold build + "
            "Snowflake export manifest."
        ),
        "StartAt": "ValidateForceInput",
        "TimeoutSeconds": 18 * 60 * 60,
        "States": {
            "ValidateForceInput": validate_force_input,
            "ForceDefault":       force_default,
            "InvalidForceInput":  invalid_force_input,
            "RefreshModeCheck":   refresh_mode_check,
            "RefreshModeDefault": refresh_mode_default,
            "AcquireLease":       acquire_lease,
            "ReadLeaseResult":    read_lease_result,
            "LeaseAcquiredCheck": lease_acquired_check,
            "NotifyDeferred":      notify_deferred,
            "ApplyEffectiveRefreshMode": apply_effective_refresh_mode,
            "Deferred":           deferred,
            **sec_fetch_lease_states,
            "RefreshMode":        refresh_mode,
            "ComputeIdentityRefreshWindow": compute_identity_refresh_window,
            "ComputeIdentityBackstopUniverse": compute_identity_backstop_universe,
            "Stage0CompanyIdentityBounded": stage0_company_identity_bounded,
            "ReduceIdentityRefresh": reduce_identity_refresh,
            "RunWarehouseTask": run_wh,
            "DatasetPeriodCheck":   dataset_period_check,
            "DatasetPeriodDefault": dataset_period_default,
            "ForceCheck":           force_check,
            "FetchAdvBulk":         fetch_adv_bulk,
            "FetchAdvBulkForced":   fetch_adv_bulk_forced,
            "IngestAdvBulkSources": ingest_adv_bulk_sources,
            "FirmRosterForceCheck":    firm_roster_force_check,
            "FetchFirmRoster":         fetch_firm_roster,
            "FetchFirmRosterForced":   fetch_firm_roster_forced,
            "IngestFirmRosterSources": ingest_firm_roster_sources,
            "MdmRun":           mdm_run,
            "MdmBackfill":      mdm_backfill,
            "MdmExport":        mdm_export,
            "MdmSync":          mdm_sync,
            "MdmVerify":        mdm_verify,
            "GoldRefresh":      gold,
            "ReleaseLease":     release_lease,
            "ReleaseLeaseFailedNonFatal": release_lease_failed_non_fatal,
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
    "edgar-warehouse" "$BRONZE_BUCKET_NAME" "$WAREHOUSE_BUCKET_NAME" \
    "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" \
    "$BOOTSTRAP_BATCH_CONCURRENCY" "$MDM_RUN_LIMIT" "$MDM_GRAPH_LIMIT" <<'PY'
import json, pathlib, sys

(output_file, cluster_arn,
 wh_medium_arn, mdm_small_arn, mdm_medium_arn, wh_large_arn,
 container_name, bronze_bucket_name, warehouse_bucket_name, subnet_json, security_group_json,
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

release_mode_check = {
    "Type": "Choice",
    "Comment": "Route an explicitly requested Ticket 20 execution to the immutable manifest path.",
    "Choices": [{
        "Variable": "$.release_mode",
        "BooleanEquals": True,
        "Next": "StrictManifestCheck",
    }],
    "Default": "BatchSizeCheck",
}

def non_empty_string_clauses(variable):
    return [
        {"Variable": variable, "IsPresent": True},
        {"Variable": variable, "IsString": True},
        {"Not": {"Variable": variable, "StringEquals": ""}},
    ]

strict_manifest_check = {
    "Type": "Choice",
    "Comment": "Strict release requires both immutable S3 keys before any workload starts.",
    "Choices": [{
        "And": sum((
            non_empty_string_clauses(variable)
            for variable in (
                "$.candidate_manifest_key",
                "$.candidate_batches_key",
                "$.attestations.warehouse",
                "$.attestations.mdm",
                "$.attestations.graph",
                "$.attestations.release_data_operator",
                "$.attestations.release_owner",
            )
        ), []),
        "Next": "StrictBatchSilver",
    }],
    "Default": "StrictInputMissing",
}

strict_input_missing = {
    "Type": "Fail",
    "Error": "StrictReleaseInputMissing",
    "Cause": "release_mode requires immutable manifest keys and five named attestations",
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
#
# wh_large_arn, not wh_medium_arn (confirmed live 2026-08-08, same OOM class as
# the daily_incremental gold-build fix above): each batch's canonical-silver
# merge (merge_candidate_into_canonical) copies and re-opens the whole growing
# silver.duckdb -- exit 137 OutOfMemoryError on medium (4096MB) once the
# canonical DB passed ~1GB (sec_thirteenf_holding alone at 6.8M rows). This
# state's Map Comment records a 2026-06-25 81/81 PASS on medium, from before
# that growth -- medium was sufficient then, not now.
batch = ecs_state(wh_large_arn,
    "States.Array('bootstrap-batch', '--cik-list', $.cik_list, '--artifact-policy', 'skip', '--parser-policy', 'skip', '--run-id', $$.Execution.Name)",
    is_end=True)

batch_map = {
    "Type": "Map",
    "MaxConcurrency": 2,
    "Comment": "First-load recovery from cached bronze. Lowered 4->2 2026-08-08 (same fix as silver_mdm_gold's strict batch Map, 2026-07-22): all N concurrent batches merge into and publish the same canonical silver.duckdb via an ETag-guarded promote, so N-way concurrency is an N-way race on that one object. Confirmed live: one batch needed 72 PromotionConflictError retries in an 8-minute window at MaxConcurrency=4 against a ~1.6GB canonical file -- every retry re-downloads/re-merges/re-uploads the whole file, and this was the dominant driver of silver_publish climbing from ~95s to 2-6+ minutes per batch. No data loss at MaxConcurrency=4 (the retry loop is race-safe by construction), just retry-storm cost that was never worth paying. Originally validated end-to-end at MaxConcurrency=4 (run bronze-seed-silver-gold-1782384165, 2026-06-25: 81/81 BatchSilver batches succeeded, zero sec_pull_started, full chain through GoldRefresh SUCCEEDED) and MaxConcurrency=2 (run bronze-seed-silver-gold-1782351277, 2026-06-24/25) -- both passed then, when canonical was far smaller.",
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

strict_batch = ecs_state(wh_medium_arn,
    "States.Array('bootstrap-batch', '--cik-list', $.cik_list, '--artifact-policy', 'all_attachments', '--parser-policy', 'branch_b_deferred', '--release-mode', '--candidate-manifest', States.Format('s3://" + bronze_bucket_name + "/{}', $.candidate_manifest_key), '--run-id', $.release_run_id)",
    is_end=True)
# Generic States.TaskFailed retries cannot distinguish a transient SEC/network
# failure from a deterministic parser or manifest failure. Strict mode therefore
# fails once and requires an explicit repair/replay decision.
strict_batch.pop("Retry", None)

strict_batch_map = {
    "Type": "Map",
    "MaxConcurrency": 2,
    "Comment": "Ticket 20 strict candidate execution. Every batch is manifest-bounded and fail-closed. Lowered 4->2 2026-07-22: every concurrently-finishing batch merges into and publishes the same canonical silver.duckdb via an ETag-guarded promote, so N-way concurrency means an N-way race on that single object -- production hit this repeatedly at MaxConcurrency=4 (PromotionConflictError aborting an otherwise-complete batch). A retry loop now exists for the conflict (_publish_silver_database_with_retry), but lower concurrency reduces how often it's needed in the first place.",
    "ToleratedFailurePercentage": 0,
    "ItemReader": {
        "Resource": "arn:aws:states:::s3:getObject",
        "ReaderConfig": {"InputType": "JSONL", "MaxItems": 100000},
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "$.candidate_batches_key",
        },
    },
    "ItemSelector": {
        "cik_list.$": "$$.Map.Item.Value.cik_list",
        "candidate_manifest_key.$": "$.candidate_manifest_key",
        "release_run_id.$": "$$.Execution.Name",
    },
    "ItemProcessor": {
        "ProcessorConfig": {"Mode": "DISTRIBUTED", "ExecutionType": "STANDARD"},
        "StartAt": "RunStrictBatch",
        "States": {"RunStrictBatch": strict_batch},
    },
    "ResultPath": None,
    # Ticket 21: MDM must run before reconcile so IS_INSIDER versions exist for
    # verify-insider-coverage, which reconcile binds into PASS evidence.
    "Next": "StrictMdmRun",
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

# Ticket 21 chain (release_mode):
#   StrictBatchSilver -> StrictMdmRun -> Backfill -> Idempotency
#   -> StrictInsiderCoverage -> Reconcile (binds insider_coverage into PASS evidence)
#   -> Export -> Sync -> VerifyCandidate -> Activate -> Verify -> Gold
#
# Insider coverage must run AFTER MDM derives persons + IS_INSIDER. Reconcile
# must run AFTER insider coverage so bulk-load evidence cannot PASS without the
# insider-scoped completeness block.
insider_coverage_uri = (
    "States.Format('s3://"
    + warehouse_bucket_name
    + "/warehouse/release-evidence/{}/insider_coverage.json', $$.Execution.Name)"
)
strict_mdm_run = ecs_state(mdm_medium_arn, "States.Array('mdm', 'run', '--entity-type', 'all')", next_state="StrictMdmBackfill")
strict_mdm_backfill = ecs_state(mdm_medium_arn, "States.Array('mdm', 'backfill-relationships')", next_state="StrictMdmIdempotency")
strict_mdm_idempotency = ecs_state(
    mdm_medium_arn,
    "States.Array('mdm', 'backfill-relationships')",
    next_state="StrictInsiderCoverage",
)
strict_insider_coverage = ecs_state(
    mdm_medium_arn,
    "States.Array('mdm', 'verify-insider-coverage', '--output', " + insider_coverage_uri + ")",
    next_state="ReconcileRelationshipRelease",
    retry_secs=60,
)
# Fail closed on unresolved insiders (exit 1). No Catch.
strict_insider_coverage.pop("Retry", None)
strict_reconcile = ecs_state(
    wh_medium_arn,
    "States.Array("
    "'reconcile-relationship-release', "
    "'--candidate-manifest', States.Format('s3://" + bronze_bucket_name + "/{}', $.candidate_manifest_key), "
    "'--run-id', $$.Execution.Name, "
    "'--attestations-json', States.JsonToString($.attestations), "
    "'--execution-arn', $$.Execution.Id, "
    "'--insider-coverage', " + insider_coverage_uri + ")",
    next_state="StrictMdmExport",
    retry_secs=60,
)
strict_mdm_export = ecs_state(mdm_medium_arn, "States.Array('mdm', 'export')", next_state="StrictMdmSync")
# sync-graph publishes into an execution-scoped generation-id (not a fresh
# random UUID each call, its no-flag default) so StrictMdmSyncIdempotency's
# second sync-graph call targets the SAME generation (a real idempotency
# check, not a second unrelated one), and so StrictMdmVerifyCandidate/
# StrictMdmActivate below can reference it deterministically. Before this,
# nothing in any pipeline ever activated a generation, so the graph a
# strict run just synced could never become the one StrictMdmVerify checks
# (RSYNC-02 bootstrap gap).
strict_mdm_sync = ecs_state(mdm_medium_arn,
    "States.Array('mdm', 'sync-graph', '--generation-id', $$.Execution.Name)",
    next_state="StrictMdmSyncIdempotency")
strict_mdm_sync_idempotency = ecs_state(mdm_medium_arn,
    "States.Array('mdm', 'sync-graph', '--generation-id', $$.Execution.Name)",
    next_state="StrictMdmVerifyCandidate")
# Verifies this run's candidate generation specifically (not the
# currently-active one) -- on pass this promotes it 'building' -> 'verified',
# the only status StrictMdmActivate's graph-activate accepts (07-05 RSYNC-02).
# No Catch: Ticket 20 fails closed on graph parity (PR #139), so a candidate
# that doesn't verify must fail the whole execution, not silently skip ahead.
# --skip-native-app: GRAPH_APP_NODES/GRAPH_APP_EDGES (and therefore the Native
# App's GRAPH_INFO/BFS/WCC capability checks) are views scoped to whatever
# generation is currently ACTIVE, not the candidate passed via --generation-id
# -- confirmed empirically 2026-07-23 (candidate check against them fails with
# "Loading from an empty nodes table" before first activation, and passes only
# after StrictMdmActivate flips the pointer). Running them here would test the
# OLD active graph, not this candidate, and would deadlock a first-ever
# activation forever. Capability is still checked for real by StrictMdmVerify
# below, once this candidate is actually the active generation.
strict_mdm_verify_candidate = ecs_state(mdm_small_arn,
    "States.Array('mdm', 'verify-graph', '--generation-id', $$.Execution.Name, '--skip-native-app')",
    next_state="StrictMdmActivate")
strict_mdm_activate = ecs_state(mdm_small_arn,
    "States.Array('mdm', 'graph-activate', '--generation-id', $$.Execution.Name)",
    next_state="StrictMdmVerify")
strict_mdm_verify = ecs_state(mdm_small_arn, "States.Array('mdm', 'verify-graph')", next_state="StrictGoldRefresh")
strict_gold = ecs_state(wh_large_arn, "States.Array('gold-refresh', '--run-id', $$.Execution.Name)", is_end=True, retry_secs=60)

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
    "StartAt": "ReleaseModeCheck",
    "States": {
        "ReleaseModeCheck": release_mode_check,
        "StrictManifestCheck": strict_manifest_check,
        "StrictInputMissing": strict_input_missing,
        "StrictBatchSilver": strict_batch_map,
        "StrictMdmRun": strict_mdm_run,
        "StrictMdmBackfill": strict_mdm_backfill,
        "StrictMdmIdempotency": strict_mdm_idempotency,
        "StrictInsiderCoverage": strict_insider_coverage,
        "ReconcileRelationshipRelease": strict_reconcile,
        "StrictMdmExport": strict_mdm_export,
        "StrictMdmSync": strict_mdm_sync,
        "StrictMdmSyncIdempotency": strict_mdm_sync_idempotency,
        "StrictMdmVerifyCandidate": strict_mdm_verify_candidate,
        "StrictMdmActivate": strict_mdm_activate,
        "StrictMdmVerify": strict_mdm_verify,
        "StrictGoldRefresh": strict_gold,
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

write_generation_build_definition() {
  local output_file="$1"
  local mdm_task_small_arn="$2"   # mdm small  (generation-fan-in, generation-retry-failed-partitions, generation-activate: bookkeeping only)
  local mdm_task_medium_arn="$3"  # mdm medium (generation-plan, per-partition generation-build-partition: reads mdm_entity/mdm_relationship_instance)

  python3 - "$output_file" "$CLUSTER_ARN" \
    "$mdm_task_small_arn" "$mdm_task_medium_arn" \
    "edgar-warehouse" "$BRONZE_BUCKET_NAME" "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" \
    "$MDM_GRAPH_RULE_VERSION" "$MDM_GRAPH_SCHEMA_VERSION" "$MDM_GENERATION_PARTITION_CONCURRENCY" <<'PY'
import json, pathlib, sys

(output_file, cluster_arn,
 mdm_small_arn, mdm_medium_arn,
 container_name, bronze_bucket_name, subnet_json, security_group_json,
 default_rule_version, default_schema_version, partition_concurrency) = sys.argv[1:]

subnets = json.loads(subnet_json)
security_groups = json.loads(security_group_json)

def ecs_state(task_def_arn, cmd_expr, next_state=None, is_end=False, retry_secs=60, max_attempts=2):
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
                   "BackoffRate": 2.0, "MaxAttempts": max_attempts}],
    }
    if is_end:
        s["End"] = True
    else:
        s["Next"] = next_state
    return s

# (0) RuleVersionCheck/Default, SchemaVersionCheck/Default: same D-15 backward-compat
# pattern as load_history's WindowSizeCheck/Default -- {} is a valid trigger input.
rule_version_check = {
    "Type": "Choice",
    "Comment": "Route to SchemaVersionCheck directly when caller supplied rule_version; otherwise inject the default.",
    "Choices": [{"Variable": "$.rule_version", "IsPresent": True, "Next": "SchemaVersionCheck"}],
    "Default": "RuleVersionDefault",
}
rule_version_default = {
    "Type": "Pass",
    "Comment": "Inject default rule_version when caller passed {} or omitted the key.",
    "Result": default_rule_version,
    "ResultPath": "$.rule_version",
    "Next": "SchemaVersionCheck",
}
schema_version_check = {
    "Type": "Choice",
    "Comment": "Route to GenerationPlan directly when caller supplied schema_version; otherwise inject the default.",
    "Choices": [{"Variable": "$.schema_version", "IsPresent": True, "Next": "GenerationPlan"}],
    "Default": "SchemaVersionDefault",
}
schema_version_default = {
    "Type": "Pass",
    "Comment": "Inject default schema_version when caller passed {} or omitted the key.",
    "Result": default_schema_version,
    "ResultPath": "$.schema_version",
    "Next": "GenerationPlan",
}

# (1) GenerationPlan: freezes a committed MDM watermark, plans one partition per
# active node/relationship type (07-04 generation.py), and writes
# reference/mdm_generation/runs/<execution-name>/{generation.json,partitions.jsonl}
# to S3 bronze (same ItemReader side-channel convention as load_history's
# cik_windows.jsonl) so BuildPartitions' Distributed Map below can fan out
# without Step Functions ever needing to thread the generation_id through task
# output -- ecs:runTask.sync does not surface container stdout as state output.
generation_plan = ecs_state(mdm_medium_arn,
    "States.Array('mdm', 'generation-plan', '--run-id', $$.Execution.Name, '--rule-version', $.rule_version, '--schema-version', $.schema_version)",
    next_state="BuildPartitions", retry_secs=60)
generation_plan["ResultPath"] = None

# (2) BuildPartitions: bounded-concurrency DISTRIBUTED Map, one ECS task per
# partition. Mode is DISTRIBUTED, not INLINE, for the same reason as
# load_history's WindowedBootstrap: ItemReader (reading partitions.jsonl from
# S3) requires Mode=DISTRIBUTED. MaxConcurrency bounds parallel partition
# builds (default 8, see --mdm-generation-partition-concurrency) so this fans
# out without unbounded Fargate task creation. Each item carries only
# partition_id -- build_partition() is self-sufficient from that alone (07-04
# generation.py). ToleratedFailurePercentage=100: a partition build failure is
# not fatal to the whole Map (the per-partition CLI command marks its own row
# 'failed' before re-raising, see generation-build-partition), so the Map
# always finishes and FanIn -- not this Map -- is the single authority on
# pass/fail for the generation as a whole.
per_partition = ecs_state(mdm_medium_arn,
    "States.Array('mdm', 'generation-build-partition', '--partition-id', $.partition_id)",
    is_end=True, retry_secs=60)

build_partitions = {
    "Type": "Map",
    "Comment": "Fan out one ECS task per generation partition (node/relationship type, or shard). Bounded concurrency, partial-failure tolerant -- FanIn is the sole authority on pass/fail, not this Map.",
    "MaxConcurrency": int(partition_concurrency),
    "ToleratedFailurePercentage": 100,
    "ItemReader": {
        "Resource": "arn:aws:states:::s3:getObject",
        "ReaderConfig": {"InputType": "JSONL", "MaxItems": 100000},
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "States.Format('warehouse/bronze/reference/mdm_generation/runs/{}/partitions.jsonl', $$.Execution.Name)",
        },
    },
    "ItemProcessor": {
        "ProcessorConfig": {"Mode": "DISTRIBUTED", "ExecutionType": "STANDARD"},
        "StartAt": "BuildPartition",
        "States": {"BuildPartition": per_partition},
    },
    "ResultPath": None,
    "Next": "FanIn",
}

# (3) FanIn: verifies the complete partition set (no missing/duplicate shards,
# no mixed watermark/rule/schema version, no endpoint gaps, everything
# built/reused) and marks the generation verified or failed (07-04
# fan_in_generation). Exits non-zero on failure so Catch routes to
# RetryFailedPartitions instead of Activate -- Activate must never run on an
# unverified generation.
fan_in = ecs_state(mdm_small_arn,
    "States.Array('mdm', 'generation-fan-in', '--run-id', $$.Execution.Name)",
    next_state="Activate", retry_secs=30, max_attempts=1)
fan_in["Catch"] = [{
    "ErrorEquals": ["States.ALL"],
    "ResultPath": None,
    "Next": "RetryFailedPartitions",
}]

# (4) RetryFailedPartitions: resets only 'failed' partitions back to 'pending'
# (built/reused partitions are untouched -- content-addressed reuse means a
# retry never redoes finished work, 07-04 retry_failed_partitions) and
# terminates this execution. Operators re-trigger generation_build with the
# same rule_version/schema_version; GenerationPlan's content-hash reuse means
# partitions already built by this failed attempt are inherited for free by
# the next run instead of being rebuilt.
retry_failed_partitions_state = ecs_state(mdm_small_arn,
    "States.Array('mdm', 'generation-retry-failed-partitions', '--run-id', $$.Execution.Name)",
    is_end=True, retry_secs=30, max_attempts=1)

# (5) Activate: only reachable via FanIn's Next (never via its Catch), so a
# generation can only be activated after fan-in verification passes.
activate = ecs_state(mdm_small_arn,
    "States.Array('mdm', 'generation-activate', '--run-id', $$.Execution.Name)",
    is_end=True, retry_secs=30, max_attempts=1)

definition = {
    "Comment": (
        "Parallel immutable graph generation build (07-04, RSYNC-04): plan one "
        "partition per active node/relationship type, build partitions "
        "independently with bounded concurrency and per-partition retry, "
        "fan-in verify the complete set, then activate -- only after "
        "verification passes. New MDM writes queue independently via the "
        "publication outbox (07-03) the whole time; they are never blocked by "
        "an in-flight build, and are picked up by the NEXT generation, not "
        "this one. Trigger with: {} or "
        "{\"rule_version\": \"v2\", \"schema_version\": \"v1\"}"
    ),
    "StartAt": "RuleVersionCheck",
    "States": {
        "RuleVersionCheck": rule_version_check,
        "RuleVersionDefault": rule_version_default,
        "SchemaVersionCheck": schema_version_check,
        "SchemaVersionDefault": schema_version_default,
        "GenerationPlan": generation_plan,
        "BuildPartitions": build_partitions,
        "FanIn": fan_in,
        "RetryFailedPartitions": retry_failed_partitions_state,
        "Activate": activate,
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
  # sec_fetch_active cross-command lease (release-readiness ticket 84):
  # only bootstrap_full and targeted_resync are among the 5 SEC-fetching
  # commands (CLAUDE.md's Phased Pipeline scope); full_reconcile,
  # load_daily_form_index_for_date, catch_up_daily_form_index, gold_refresh,
  # and seed_universe don't call SEC at meaningful volume and stay unwrapped.
  wrap_with_sec_fetch_lease=""
  if [[ "$workflow" == "bootstrap_full" || "$workflow" == "targeted_resync" ]]; then
    wrap_with_sec_fetch_lease="true"
  fi
  write_single_workflow_definition "$definition_file" "$task_definition_arn" "$command_expression" "$cik_command_expression" \
    "$BRONZE_BUCKET_NAME" "$wrap_with_sec_fetch_lease"
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
    "bootstrap" "$BRONZE_BUCKET_NAME" ""
  recent10_state_machine_arn="$(upsert_state_machine bootstrap "$recent10_definition_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
  printf ',\n' >> "$WORKFLOW_ARNS_FILE"
  python3 - "bootstrap" "$recent10_state_machine_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
import json, sys
print(f"  {json.dumps(sys.argv[1])}: {json.dumps(sys.argv[2])}", end="")
PY

  # daily_incremental: daily new filings → MDM chain → gold. Same pipeline shape.
  if is_empty "$OPERATOR_ALERT_TOPIC_ARN"; then
    fail "--operator-alert-topic-arn is required when deploying daily_incremental with MDM"
  fi
  require_confirmed_operator_alert_topic "$OPERATOR_ALERT_TOPIC_ARN"
  daily_definition_file="$(json_file sfn-daily-incremental)"
  write_warehouse_mdm_gold_definition "$daily_definition_file" \
    "$TASK_DEF_MEDIUM_ARN" "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_MDM_MEDIUM_ARN" "$TASK_DEF_LARGE_ARN" \
    "daily_incremental" "$BRONZE_BUCKET_NAME" "$OPERATOR_ALERT_TOPIC_ARN"
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

  # ownership_mdm_gold: Form 3/4/5 already in silver → persons + IS_INSIDER only
  # (Ticket 21). Companies are NOT re-resolved — they do not change on an
  # insider load. No full mdm run --entity-type all.
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
        "Ticket 21 insider path: optional parse-ownership-bronze, then PERSON-only "
        "MDM resolve + IS_INSIDER derive (no company re-load), export/sync-graph, gold."
    ),
    "StartAt": "ParseOwnershipBronze",
    "States": {
        "ParseOwnershipBronze": ecs_state(wh_medium_arn,
            "States.Array('parse-ownership-bronze', '--run-id', $$.Execution.Name)",
            next_state="MdmPersons", retry_secs=60),
        # Companies are assumed already in MDM; only Form 3/4/5 persons.
        "MdmPersons": ecs_state(
            mdm_medium_arn,
            "States.Array('mdm', 'run', '--entity-type', 'person')",
            next_state="MdmIsInsider",
        ),
        "MdmIsInsider": ecs_state(
            mdm_medium_arn,
            "States.Array('mdm', 'derive-relationships', '--relationship-type', 'IS_INSIDER', '--target-per-type', '100000')",
            next_state="MdmExport",
        ),
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

  # residual_holds_graph: Ticket 20 residual after EMPLOYED_BY bulk-load —
  # populate security nodes + IS_INSIDER + HOLDS + COMPANY_HOLDS +
  # INSTITUTIONAL_HOLDS into MDM and the graph. Does NOT re-run companies
  # (issuers assumed present). INSTITUTIONAL_HOLDS is a separate step for
  # OOM safety (same pattern as scripts/ops/sync-relationships.sh).
  # Heavy stages use mdm-large (8 GiB): mdm-medium 2 GiB OOM'd on MdmSecurities
  # (prod residual-holds-20260725T221723Z, exit 137).
  residual_holds_graph_file="$(json_file sfn-residual-holds-graph)"
  python3 - "$residual_holds_graph_file" "$CLUSTER_ARN" \
    "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_MDM_LARGE_ARN" \
    "edgar-warehouse" "$PUBLIC_SUBNET_IDS_JSON" "$SECURITY_GROUP_IDS_JSON" <<'PY'
import json, pathlib, sys

(output_file, cluster_arn,
 mdm_small_arn, mdm_large_arn,
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

# Shared generation id for export→sync→verify (candidate publish, then activate
# is intentionally operator-driven for residual fills).
definition = {
    "Comment": (
        "Handoff residual pipeline: security nodes + IS_INSIDER + HOLDS + "
        "COMPANY_HOLDS + INSTITUTIONAL_HOLDS into MDM and Snowflake graph. "
        "Does not re-resolve companies. Does not claim Ticket 20 GO. "
        "Heavy stages use mdm-large (8 GiB) after prod MdmSecurities OOM on 2 GiB."
    ),
    "StartAt": "MdmSecurities",
    "States": {
        "MdmSecurities": ecs_state(
            mdm_large_arn,
            "States.Array('mdm', 'run', '--entity-type', 'security')",
            next_state="MdmPersons",
        ),
        "MdmPersons": ecs_state(
            mdm_large_arn,
            "States.Array('mdm', 'run', '--entity-type', 'person')",
            next_state="MdmIsInsider",
        ),
        "MdmIsInsider": ecs_state(
            mdm_large_arn,
            "States.Array('mdm', 'derive-relationships', '--relationship-type', 'IS_INSIDER', '--target-per-type', '100000')",
            next_state="MdmHolds",
        ),
        "MdmHolds": ecs_state(
            mdm_large_arn,
            "States.Array('mdm', 'derive-relationships', '--relationship-type', 'HOLDS', '--target-per-type', '100000')",
            next_state="MdmCompanyHolds",
        ),
        "MdmCompanyHolds": ecs_state(
            mdm_large_arn,
            "States.Array('mdm', 'derive-relationships', '--relationship-type', 'COMPANY_HOLDS', '--target-per-type', '100000')",
            next_state="MdmInstitutionalHolds",
        ),
        # Separate step + lower default target for OOM safety (13F holding table).
        "MdmInstitutionalHolds": ecs_state(
            mdm_large_arn,
            "States.Array('mdm', 'derive-relationships', '--relationship-type', 'INSTITUTIONAL_HOLDS', '--target-per-type', '50000')",
            next_state="MdmExport",
            retry_secs=180,
        ),
        "MdmExport": ecs_state(
            mdm_large_arn,
            "States.Array('mdm', 'export')",
            next_state="MdmSync",
        ),
        # Full-graph materialization (not residual types only). A type-filtered
        # sync produced incomplete candidate gen 69e139b0… (company/person/security
        # + HOLDS only) while verify without --generation-id checked the *active*
        # Ticket 20 gen against full MDM — parity failed on IS_INSIDER/HOLDS
        # (residual-holds-20260725T222735Z). Use Execution.Name as generation_id
        # so verify scopes the candidate; empty type filters = all MDM types.
        "MdmSync": ecs_state(
            mdm_large_arn,
            (
                "States.Array("
                "'mdm', 'sync-graph', "
                "'--generation-id', $$.Execution.Name, "
                "'--limit-per-type', '200000'"
                ")"
            ),
            next_state="MdmVerify",
            retry_secs=180,
        ),
        "MdmVerify": ecs_state(
            mdm_small_arn,
            (
                "States.Array("
                "'mdm', 'verify-graph', '--skip-native-app', "
                "'--generation-id', $$.Execution.Name"
                ")"
            ),
            is_end=True,
            retry_secs=60,
        ),
    },
}
pathlib.Path(output_file).write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
PY
  residual_holds_graph_arn="$(upsert_state_machine residual_holds_graph "$residual_holds_graph_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
  printf ',\n' >> "$WORKFLOW_ARNS_FILE"
  python3 - "residual_holds_graph" "$residual_holds_graph_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
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

  # generation_build: parallel immutable graph generation build (07-04, RSYNC-04).
  # Plan -> bounded-concurrency partition fan-out -> fan-in verify -> activate.
  # Standalone (not chained into load_history/bootstrap/daily_incremental yet --
  # 07-05 owns wiring the shared Snowflake activation pointer those pipelines read).
  generation_build_file="$(json_file sfn-generation-build)"
  write_generation_build_definition "$generation_build_file" \
    "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_MDM_MEDIUM_ARN"
  generation_build_arn="$(upsert_state_machine generation_build "$generation_build_file" "$STEP_FUNCTIONS_ROLE_ARN" "$LOGGING_CONFIGURATION_FILE")"
  printf ',\n' >> "$WORKFLOW_ARNS_FILE"
  python3 - "generation_build" "$generation_build_arn" >> "$WORKFLOW_ARNS_FILE" <<'PY'
import json, sys
print(f"  {json.dumps(sys.argv[1])}: {json.dumps(sys.argv[2])}", end="")
PY

  for workflow in mdm_migrate mdm_check_connectivity mdm_run mdm_backfill_relationships mdm_sync_graph mdm_verify_graph mdm_counts mdm_seed_universe mdm_seed_from_silver; do
    task_definition_arn="$(task_definition_for_mdm_workflow "$workflow")"
    command_expression="$(mdm_workflow_command_expression "$workflow")"
    limit_command_expression="$(mdm_workflow_limit_command_expression "$workflow")"
    relationship_command_expression="$(mdm_workflow_relationship_command_expression "$workflow")"
    relationship_limit_command_expression="$(mdm_workflow_relationship_limit_command_expression "$workflow")"
    limit_per_type_command_expression="$(mdm_workflow_limit_per_type_command_expression "$workflow")"
    definition_file="$(json_file "sfn-${workflow}")"
    write_mdm_workflow_definition "$definition_file" "$task_definition_arn" "$command_expression" "$limit_command_expression" "$relationship_command_expression" "$relationship_limit_command_expression" "$limit_per_type_command_expression"
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
  "$DEPLOY_MDM" "$MDM_DATABASE_SOURCE" "$TASK_DEF_MDM_SMALL_ARN" "$TASK_DEF_MDM_MEDIUM_ARN" "$TASK_DEF_MDM_LARGE_ARN" "$MDM_SILVER_DUCKDB" \
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
    mdm_large_task_definition,
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
    task_definitions["mdm_large"] = mdm_large_task_definition

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
