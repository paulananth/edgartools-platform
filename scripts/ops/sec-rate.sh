#!/usr/bin/env bash
# Analyse SEC request rates across all running batch tasks.
# Shows per-task req/min, aggregate req/sec, and 503 breakdown.
#
# Usage:
#   ./scripts/ops/sec-rate.sh
#   ./scripts/ops/sec-rate.sh --env dev --last-minutes 30

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARG=""
LAST_MINUTES=60

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)           ENVIRONMENT="${2:?}"; shift 2 ;;
    --region)        AWS_REGION="${2:?}"; shift 2 ;;
    --profile)       AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    --last-minutes)  LAST_MINUTES="${2:?}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

NAME_PREFIX="edgartools-${ENVIRONMENT}"
CLUSTER="${NAME_PREFIX}-warehouse"
LOG_GROUP="/aws/ecs/${NAME_PREFIX}-warehouse"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYSER="${SCRIPT_DIR}/analyse_sec_rate.py"

aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }
hr()   { printf '%.0s─' $(seq 1 65); echo; }

START_MS=$(( ($(date -u +%s) - LAST_MINUTES * 60) * 1000 ))

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

echo ""
hr
echo "  SEC REQUEST RATE  ·  ${ENVIRONMENT}  ·  last ${LAST_MINUTES}min"
hr

if [[ ${#TASK_IDS[@]} -eq 0 ]]; then
  echo "  No running tasks."
  echo ""
  hr
  exit 0
fi

for TASK_ID in "${TASK_IDS[@]}"; do
  echo ""
  echo "── Task ${TASK_ID:0:20}"

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
    echo "  (stream not found)"
    continue
  fi

  aws_ logs get-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$FULL_STREAM" \
    --start-time "$START_MS" \
    --output json 2>/dev/null | python3 "$ANALYSER"
done

echo ""
echo "  SEC limit : 10 req/sec per IP  (per EDGAR policy)"
echo "  Target    : ≤3 req/sec total  (concurrency 3 × 1s sleep)"
echo ""
hr
