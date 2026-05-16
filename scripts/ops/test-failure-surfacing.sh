#!/usr/bin/env bash
# Failure-injection regression test for bootstrap_phased.
# Confirms that ToleratedFailurePercentage: 0 causes the execution to reach
# FAILED state when a batch fails, never SUCCEEDED.
#
# Strategy: start bootstrap_phased, wait for SeedUniverse to complete, then
# overwrite the cik_batches.jsonl S3 file with a single invalid CIK (9999999).
# The ECS bootstrap-batch task will fetch SEC EDGAR for CIK 9999999, get a 404,
# raise WarehouseRuntimeError, and exit non-zero. After 3 SFN-level retries the
# child execution fails. With ToleratedFailurePercentage: 0 the parent reaches FAILED.
#
# Usage:
#   BRONZE_BUCKET=<bucket-name> ./scripts/ops/test-failure-surfacing.sh
#   BRONZE_BUCKET=<bucket-name> ./scripts/ops/test-failure-surfacing.sh --env dev
#
# Runtime: ~25-35 minutes (SeedUniverse 5-10 min + 3 retries with backoff ~17 min)
# Timeout:  45 minutes (MAX_WAIT_SECONDS=2700)

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARG=""
MAX_WAIT_SECONDS=2700

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)     ENVIRONMENT="${2:?}"; shift 2 ;;
    --region)  AWS_REGION="${2:?}"; shift 2 ;;
    --profile) AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    -*)        echo "Unknown flag: $1" >&2; exit 2 ;;
    *)         echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -z "${BRONZE_BUCKET:-}" ]] && { echo "ERROR: BRONZE_BUCKET env var is required"; echo "  export BRONZE_BUCKET=<dev-bronze-bucket-name>"; exit 1; }

NAME_PREFIX="edgartools-${ENVIRONMENT}"
ACCOUNT=$(aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" sts get-caller-identity --query Account --output text)
SM_ARN="arn:aws:states:${AWS_REGION}:${ACCOUNT}:stateMachine:${NAME_PREFIX}-bootstrap-phased"
aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }

RUN_NAME="test-failure-surfacing-$(date -u +%Y%m%d-%H%M%S)"

# ── Step 1: Start execution ────────────────────────────────────────────────────
echo "[1/5] Starting bootstrap_phased execution: ${RUN_NAME}"
RESULT=$(aws_ stepfunctions start-execution \
  --state-machine-arn "$SM_ARN" \
  --name "$RUN_NAME" \
  --input '{}' \
  --output json)
EXEC_ARN=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['executionArn'])")
echo "    Execution ARN: ${EXEC_ARN}"

# ── Step 2: Poll for SeedUniverse to exit ─────────────────────────────────────
echo "[2/5] Waiting for SeedUniverse to complete..."
SEED_WAIT=0
SEED_TIMEOUT=900
while true; do
  EXITED=$(aws_ stepfunctions get-execution-history \
    --execution-arn "$EXEC_ARN" --output json \
    | python3 -c "
import json,sys
for e in json.load(sys.stdin)['events']:
    if e.get('stateExitedEventDetails',{}).get('name','') == 'SeedUniverse':
        print('yes'); break
")
  [[ "$EXITED" == "yes" ]] && break
  SEED_WAIT=$((SEED_WAIT + 15))
  [[ $SEED_WAIT -ge $SEED_TIMEOUT ]] && { echo "ERROR: SeedUniverse did not complete within 15 minutes"; exit 1; }
  sleep 15
done
echo "    SeedUniverse completed."

# ── Step 3: Sleep 3s to allow SFN scheduling lag, then overwrite S3 ──────────
echo "[3/5] Overwriting cik_batches.jsonl with invalid CIK 9999999..."
sleep 3
S3_KEY="warehouse/bronze/reference/cik_universe/runs/${RUN_NAME}/cik_batches.jsonl"
echo '{"cik_list": "9999999"}' | aws_ s3 cp - "s3://${BRONZE_BUCKET}/${S3_KEY}"
echo "    Wrote s3://${BRONZE_BUCKET}/${S3_KEY}"

# ── Step 4: Poll describe-execution until terminal state ──────────────────────
echo "[4/5] Polling for terminal state (timeout: 45 min)..."
ELAPSED=0
while true; do
  STATUS=$(aws_ stepfunctions describe-execution \
    --execution-arn "$EXEC_ARN" \
    --query 'status' --output text)
  [[ "$STATUS" != "RUNNING" ]] && break
  ELAPSED=$((ELAPSED + 30))
  [[ $ELAPSED -ge $MAX_WAIT_SECONDS ]] && {
    echo "ERROR: Execution still RUNNING after ${MAX_WAIT_SECONDS}s. ARN: ${EXEC_ARN}"
    exit 1
  }
  echo "    ${ELAPSED}s elapsed — status: ${STATUS}"
  sleep 30
done

# ── Step 5: Assert FAILED ─────────────────────────────────────────────────────
echo "[5/5] Asserting execution reached FAILED state..."
if [[ "$STATUS" == "FAILED" ]]; then
  echo "PASS: execution reached FAILED state as expected"
  echo "      Execution ARN: ${EXEC_ARN}"
  echo "      Inspect in console: https://console.aws.amazon.com/states/home#/executions/details/${EXEC_ARN}"
  exit 0
else
  echo "ASSERTION FAILED: expected FAILED, got ${STATUS}"
  echo "      Execution ARN: ${EXEC_ARN}"
  exit 1
fi
