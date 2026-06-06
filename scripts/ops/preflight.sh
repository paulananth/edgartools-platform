#!/usr/bin/env bash
# Pre-flight check: verify every critical dependency before triggering bootstrap.
# Each check either passes ✓ or fails ✗ with a clear fix command.
# Run this before any load_history / silver_mdm_gold / gold-refresh trigger.
#
# Usage:
#   ./scripts/ops/preflight.sh
#   ./scripts/ops/preflight.sh --env dev --skip-snowflake
#   ./scripts/ops/preflight.sh --fix    # auto-fix what can be fixed

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARG=""
SNOW_CONN=""
SKIP_SNOWFLAKE=false
AUTO_FIX=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)             ENVIRONMENT="${2:?}"; shift 2 ;;
    --region)          AWS_REGION="${2:?}"; shift 2 ;;
    --profile)         AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    --snow-connection) SNOW_CONN="${2:?}"; shift 2 ;;
    --skip-snowflake)  SKIP_SNOWFLAKE=true; shift ;;
    --fix)             AUTO_FIX=true; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

NAME_PREFIX="edgartools-${ENVIRONMENT}"
SNOW_CONN="${SNOW_CONN:-${NAME_PREFIX}}"
ACCOUNT_ID="$(aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" sts get-caller-identity --query Account --output text 2>/dev/null)"

aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }
hr()   { printf '%.0s─' $(seq 1 65); echo; }

PASS=0
FAIL=0
WARN=0

check() {
  local label="$1" result="$2" fix="${3:-}"
  if [[ "$result" == "PASS" ]]; then
    printf "  ✓  %-50s\n" "$label"
    PASS=$(( PASS + 1 ))
  elif [[ "$result" == "WARN" ]]; then
    printf "  ⚠  %-50s\n" "$label"
    WARN=$(( WARN + 1 ))
  else
    printf "  ✗  %-50s\n" "$label"
    [[ -n "$fix" ]] && echo "       fix: $fix"
    FAIL=$(( FAIL + 1 ))
  fi
}

echo ""
hr
echo "  PRE-FLIGHT CHECK  ·  ${ENVIRONMENT}  ·  ${AWS_REGION}"
hr

# ── 1. ECS Cluster ────────────────────────────────────────────────────────────
echo ""
echo "AWS INFRASTRUCTURE"
CLUSTER_STATUS=$(aws_ ecs describe-clusters \
  --clusters "${NAME_PREFIX}-warehouse" \
  --query 'clusters[0].status' --output text 2>/dev/null || echo "NOT_FOUND")
check "ECS cluster ${NAME_PREFIX}-warehouse" \
  "$([[ "$CLUSTER_STATUS" == "ACTIVE" ]] && echo PASS || echo FAIL)" \
  "terraform apply in infra/terraform/accounts/${ENVIRONMENT}"

# ── 2. ECR image exists ───────────────────────────────────────────────────────
LATEST_IMAGE=$(aws_ ecr describe-images \
  --repository-name "${NAME_PREFIX}-warehouse" \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageTags[0]" \
  --output text 2>/dev/null || echo "")
check "ECR warehouse image exists (latest: ${LATEST_IMAGE:-none})" \
  "$([[ -n "$LATEST_IMAGE" && "$LATEST_IMAGE" != "None" ]] && echo PASS || echo FAIL)" \
  "bash infra/scripts/publish-warehouse-image.sh --env ${ENVIRONMENT} ..."

# ── 3. Task definitions current ───────────────────────────────────────────────
SMALL_DEF=$(aws_ ecs describe-task-definition \
  --task-definition "${NAME_PREFIX}-small" \
  --query 'taskDefinition.status' --output text 2>/dev/null || echo "NOT_FOUND")
check "ECS task definitions registered" \
  "$([[ "$SMALL_DEF" == "ACTIVE" ]] && echo PASS || echo FAIL)" \
  "bash infra/scripts/deploy-aws-application.sh --env ${ENVIRONMENT} ..."

# ── 4. State machines exist ───────────────────────────────────────────────────
for sm in "load-history" "gold-refresh" "silver-mdm-gold" "mdm-gold"; do
  SM_ARN="arn:aws:states:${AWS_REGION}:${ACCOUNT_ID}:stateMachine:${NAME_PREFIX}-${sm}"
  SM_STATUS=$(aws_ stepfunctions describe-state-machine \
    --state-machine-arn "$SM_ARN" \
    --query 'status' --output text 2>/dev/null || echo "NOT_FOUND")
  check "State machine ${sm}" \
    "$([[ "$SM_STATUS" == "ACTIVE" ]] && echo PASS || echo FAIL)" \
    "bash infra/scripts/deploy-aws-application.sh --env ${ENVIRONMENT} --enable-mdm --mdm-database-source snowflake-postgres ..."
done

# ── 5. S3 buckets exist ───────────────────────────────────────────────────────
echo ""
echo "S3 BUCKETS"
for bucket in \
  "${NAME_PREFIX}-bronze-${ACCOUNT_ID}" \
  "${NAME_PREFIX}-warehouse-${ACCOUNT_ID}" \
  "${NAME_PREFIX}-snowflake-export-${ACCOUNT_ID}"; do
  EXISTS=$(aws_ s3api head-bucket --bucket "$bucket" >/dev/null 2>&1 && echo "PASS" || echo "FAIL")
  check "s3://${bucket}" "$EXISTS" \
    "terraform apply in infra/terraform/accounts/${ENVIRONMENT}"
done

# ── 6. S3 → SNS bucket notification ─────────────────────────────────────────
echo ""
echo "SNOWFLAKE PIPELINE"
EXPORT_BUCKET="${NAME_PREFIX}-snowflake-export-${ACCOUNT_ID}"
SNS_ARN="arn:aws:sns:${AWS_REGION}:${ACCOUNT_ID}:${NAME_PREFIX}-snowflake-manifest-events"

NOTIF_SNS=$(aws_ s3api get-bucket-notification-configuration \
  --bucket "$EXPORT_BUCKET" \
  --query 'TopicConfigurations[0].TopicArn' \
  --output text 2>/dev/null || echo "")
NOTIF_OK="$([[ "$NOTIF_SNS" == "$SNS_ARN" ]] && echo PASS || echo FAIL)"
if [[ "$NOTIF_OK" == "FAIL" && "$AUTO_FIX" == "true" ]]; then
  bash "$(dirname "${BASH_SOURCE[0]}")/../../infra/scripts/deploy-aws-application.sh" \
    --env "$ENVIRONMENT" --skip-build \
    --image-ref "dummy" --skip-mdm 2>/dev/null || true
  NOTIF_SNS=$(aws_ s3api get-bucket-notification-configuration \
    --bucket "$EXPORT_BUCKET" \
    --query 'TopicConfigurations[0].TopicArn' \
    --output text 2>/dev/null || echo "")
  NOTIF_OK="$([[ "$NOTIF_SNS" == "$SNS_ARN" ]] && echo PASS || echo FAIL)"
fi
check "S3 → SNS bucket notification configured" "$NOTIF_OK" \
  "bash infra/scripts/deploy-aws-application.sh --env ${ENVIRONMENT} --skip-build --image-ref ... --enable-mdm --mdm-database-source snowflake-postgres"

# ── 7. SNS topic + Snowpipe SQS subscription ─────────────────────────────────
SNS_EXISTS=$(aws_ sns get-topic-attributes \
  --topic-arn "$SNS_ARN" \
  --query 'Attributes.TopicArn' --output text 2>/dev/null || echo "")
check "SNS topic ${NAME_PREFIX}-snowflake-manifest-events" \
  "$([[ -n "$SNS_EXISTS" ]] && echo PASS || echo FAIL)" \
  "terraform apply in infra/terraform/accounts/${ENVIRONMENT}"

if [[ -n "$SNS_EXISTS" ]]; then
  SUB_COUNT=$(aws_ sns list-subscriptions-by-topic \
    --topic-arn "$SNS_ARN" \
    --query 'length(Subscriptions)' --output text 2>/dev/null || echo "0")
  check "SNS → Snowpipe SQS subscription exists (${SUB_COUNT} subs)" \
    "$([[ "$SUB_COUNT" -gt 0 ]] && echo PASS || echo FAIL)" \
    "Re-run deploy-snowflake-stack.sh to recreate the Snowpipe subscription"
fi

# ── 8. Snowflake-side checks ──────────────────────────────────────────────────
if [[ "$SKIP_SNOWFLAKE" == "true" ]]; then
  check "Snowflake checks (skipped with --skip-snowflake)" "WARN"
else
  if ! command -v snow &>/dev/null; then
    check "SnowCLI (snow) installed" "FAIL" "pip install snowflake-cli-labs"
  else
    DB="EDGARTOOLS_$(echo "$ENVIRONMENT" | tr '[:lower:]' '[:upper:]')"

    # Task started
    TASK_STATE=$(snow sql --connection "$SNOW_CONN" \
      -q "SELECT STATE FROM ${DB}.EDGARTOOLS_GOLD.SNOWFLAKE_RUN_MANIFEST_TASK LIMIT 1" \
      --format json 2>/dev/null | python3 -c "
import json,sys
rows=json.load(sys.stdin)
print(rows[0].get('STATE','') if rows else 'NOT_FOUND')
" 2>/dev/null || \
      snow sql --connection "$SNOW_CONN" \
        -q "SHOW TASKS LIKE 'SNOWFLAKE_RUN_MANIFEST_TASK' IN SCHEMA ${DB}.EDGARTOOLS_GOLD" \
        --format json 2>/dev/null | python3 -c "
import json,sys
rows=json.load(sys.stdin)
print(rows[0].get('state','NOT_FOUND') if rows else 'NOT_FOUND')
" 2>/dev/null || echo "NOT_FOUND")
    check "SNOWFLAKE_RUN_MANIFEST_TASK state=started" \
      "$([[ "$(echo "$TASK_STATE" | tr '[:upper:]' '[:lower:]')" == "started" ]] && echo PASS || echo FAIL)" \
      "snow sql --connection ${SNOW_CONN} -q \"ALTER TASK ${DB}.EDGARTOOLS_GOLD.SNOWFLAKE_RUN_MANIFEST_TASK RESUME\""

    # Pipe exists and has a valid notification channel
    PIPE_CHANNEL=$(snow sql --connection "$SNOW_CONN" \
      -q "SHOW PIPES LIKE 'SNOWFLAKE_RUN_MANIFEST_PIPE' IN SCHEMA ${DB}.EDGARTOOLS_SOURCE" \
      --format json 2>/dev/null | python3 -c "
import json,sys
rows=json.load(sys.stdin)
print(rows[0].get('notification_channel','') if rows else '')
" 2>/dev/null || echo "")
    check "SNOWFLAKE_RUN_MANIFEST_PIPE exists (channel: ${PIPE_CHANNEL:-none})" \
      "$([[ -n "$PIPE_CHANNEL" ]] && echo PASS || echo FAIL)" \
      "Re-deploy Snowflake stack: bash infra/scripts/deploy-snowflake-stack.sh --env ${ENVIRONMENT}"

    # Source COMPANY count
    COMPANY_COUNT=$(snow sql --connection "$SNOW_CONN" \
      -q "SELECT count(*) AS n FROM ${DB}.EDGARTOOLS_SOURCE.COMPANY" \
      --format json 2>/dev/null | python3 -c "
import json,sys
rows=json.load(sys.stdin)
print(rows[0].get('N',0) if rows else 0)
" 2>/dev/null || echo "0")
    check "EDGARTOOLS_SOURCE.COMPANY rows=${COMPANY_COUNT}" \
      "$([[ "$COMPANY_COUNT" -gt 100 ]] && echo PASS || echo WARN)" \
      "Trigger gold-refresh: ./scripts/ops/trigger.sh gold"

    # Dynamic tables exist (use SHOW DYNAMIC TABLES, not INFORMATION_SCHEMA)
    DT_COUNT=$(snow sql --connection "$SNOW_CONN" \
      -q "SHOW DYNAMIC TABLES IN SCHEMA ${DB}.EDGARTOOLS_GOLD" \
      --format json 2>/dev/null | python3 -c "
import json,sys
rows=json.load(sys.stdin)
print(len(rows))
" 2>/dev/null || echo "0")
    check "EDGARTOOLS_GOLD dynamic tables exist (${DT_COUNT})" \
      "$([[ "$DT_COUNT" -ge 8 ]] && echo PASS || echo FAIL)" \
      "uv run --with dbt-snowflake dbt run --profiles-dir ... in infra/snowflake/dbt/edgartools_gold"
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
hr
TOTAL=$(( PASS + FAIL + WARN ))
echo "  ${PASS}/${TOTAL} passed  |  ${FAIL} failed  |  ${WARN} warnings"
hr
echo ""

if [[ "$FAIL" -gt 0 ]]; then
  echo "  Fix the failed checks before triggering bootstrap."
  echo "  Re-run: ./scripts/ops/preflight.sh [--fix]"
  echo ""
  exit 1
fi
