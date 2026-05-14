#!/usr/bin/env bash
# Batch task log analyser: stage, SEC 503s, circuit breaker, rate.
# Checks all currently running ECS tasks in one pass.
#
# Usage:
#   ./scripts/ops/batch-logs.sh
#   ./scripts/ops/batch-logs.sh --env dev
#   ./scripts/ops/batch-logs.sh --task-id <ecs-task-id>

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARG=""
SINGLE_TASK=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)      ENVIRONMENT="${2:?}"; shift 2 ;;
    --region)   AWS_REGION="${2:?}"; shift 2 ;;
    --profile)  AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    --task-id)  SINGLE_TASK="${2:?}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

NAME_PREFIX="edgartools-${ENVIRONMENT}"
CLUSTER="${NAME_PREFIX}-warehouse"
LOG_GROUP="/aws/ecs/${NAME_PREFIX}-warehouse"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYSER="${SCRIPT_DIR}/analyse_batch_logs.py"

aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }
hr()   { printf '%.0s─' $(seq 1 70); echo; }

# Collect running task IDs
if [[ -n "$SINGLE_TASK" ]]; then
  TASK_IDS=("$SINGLE_TASK")
else
  TASK_IDS=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && TASK_IDS+=("$line")
  done < <(aws_ ecs list-tasks \
    --cluster "$CLUSTER" \
    --desired-status RUNNING \
    --query 'taskArns' \
    --output json 2>/dev/null | python3 -c "
import json, sys
for a in json.load(sys.stdin):
    print(a.split('/')[-1])
")
fi

if [[ ${#TASK_IDS[@]} -eq 0 ]]; then
  echo "No running tasks on cluster ${CLUSTER}"
  exit 0
fi

# Fetch task metadata as TSV: task_id <TAB> def <TAB> elapsed <TAB> cmd
TASK_ARN_LIST=$(aws_ ecs list-tasks \
  --cluster "$CLUSTER" \
  --desired-status RUNNING \
  --query 'taskArns' \
  --output json 2>/dev/null | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin)))" || true)

TASK_META_FILE=$(mktemp "${TMPDIR:-/tmp}/task-meta-XXXXXX.tsv")
trap 'rm -f "$TASK_META_FILE"' EXIT

if [[ -n "$TASK_ARN_LIST" ]]; then
  aws_ ecs describe-tasks \
    --cluster "$CLUSTER" \
    --tasks $TASK_ARN_LIST \
    --output json 2>/dev/null | python3 "${SCRIPT_DIR}/describe_tasks.py" > "$TASK_META_FILE" 2>/dev/null || true
fi

echo ""
hr
echo "  BATCH TASK LOGS  ·  ${ENVIRONMENT}  ·  cluster: ${CLUSTER}"
hr

for TASK_ID in "${TASK_IDS[@]}"; do
  SHORT="${TASK_ID:0:20}"
  META=$(grep "^${TASK_ID}" "$TASK_META_FILE" 2>/dev/null | head -1 || true)
  DEF=$(     echo "$META" | cut -f2); DEF="${DEF:-?}"
  ELAPSED=$( echo "$META" | cut -f3); ELAPSED="${ELAPSED:-?}"
  CMD=$(     echo "$META" | cut -f4); CMD="${CMD:-?}"

  echo ""
  echo "TASK ${SHORT}  [${DEF}  ${ELAPSED}]"
  echo "  cmd: ${CMD}"

  # Find log stream (try medium then small prefix)
  FULL_STREAM=""
  for PREFIX in "warehouse-medium/edgar-warehouse/${TASK_ID}" "warehouse-small/edgar-warehouse/${TASK_ID}"; do
    FULL_STREAM=$(aws_ logs describe-log-streams \
      --log-group-name "$LOG_GROUP" \
      --log-stream-name-prefix "$PREFIX" \
      --query 'logStreams[0].logStreamName' \
      --output text 2>/dev/null || true)
    [[ -n "$FULL_STREAM" && "$FULL_STREAM" != "None" ]] && break
    FULL_STREAM=""
  done

  if [[ -z "$FULL_STREAM" ]]; then
    echo "  (log stream not found yet)"
    continue
  fi

  aws_ logs get-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$FULL_STREAM" \
    --output json 2>/dev/null | python3 "$ANALYSER"
done

echo ""
hr
