#!/usr/bin/env bash
# Run the full phased bootstrap pipeline for the next batch of companies.
#
# Usage:
#   bash scripts/run-bootstrap.sh
#   bash scripts/run-bootstrap.sh --watch          # stream status until done
#   bash scripts/run-bootstrap.sh --no-wait        # fire and forget
#
# What it does (4 stages, ~15 min for 100 companies):
#   1. seed-universe  — enrols bootstrap_pending CIKs into MDM
#   2. bootstrap-batch x10 concurrent — fetch SEC filings → bronze + silver
#   3. mdm run → backfill-relationships (200) → sync-graph (200) → verify-graph
#   4. gold-refresh   — builds all gold tables + Snowflake export manifest

set -euo pipefail

REGION="us-east-1"
STATE_MACHINE_ARN="arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-bootstrap-phased"
WATCH=false
NO_WAIT=false

for arg in "$@"; do
  case "$arg" in
    --watch)   WATCH=true ;;
    --no-wait) NO_WAIT=true ;;
    -h|--help)
      sed -n '2,12p' "$0" | sed 's/^# \?//'
      exit 0 ;;
  esac
done

RUN_NAME="bootstrap-phased-$(date +%s)"

echo "Starting bootstrap-phased: $RUN_NAME"
EXEC_ARN=$(aws stepfunctions start-execution \
  --region "$REGION" \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --name "$RUN_NAME" \
  --input '{}' \
  --query 'executionArn' --output text)

echo "Execution ARN: $EXEC_ARN"
echo ""
echo "Monitor in AWS console:"
echo "  https://us-east-1.console.aws.amazon.com/states/home?region=us-east-1#/executions/details/$EXEC_ARN"
echo ""

if $NO_WAIT; then
  echo "Fired. Check status with:"
  echo "  aws stepfunctions describe-execution --region $REGION --execution-arn '$EXEC_ARN' --query status --output text"
  exit 0
fi

echo "Waiting for completion (Ctrl-C to stop watching, pipeline continues in AWS)..."
echo ""

SPINNER=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
i=0
START=$(date +%s)

while true; do
  STATUS=$(aws stepfunctions describe-execution \
    --region "$REGION" \
    --execution-arn "$EXEC_ARN" \
    --query 'status' --output text 2>/dev/null || echo "UNKNOWN")

  ELAPSED=$(( $(date +%s) - START ))
  MINS=$(( ELAPSED / 60 ))
  SECS=$(( ELAPSED % 60 ))

  if $WATCH; then
    printf "\r${SPINNER[$i]} %s  elapsed: %dm%02ds  " "$STATUS" "$MINS" "$SECS"
    i=$(( (i+1) % ${#SPINNER[@]} ))
  fi

  case "$STATUS" in
    SUCCEEDED)
      echo ""
      echo "SUCCEEDED in ${MINS}m${SECS}s"
      echo "Snowflake gold tables will refresh within 1 minute."
      exit 0
      ;;
    FAILED|TIMED_OUT|ABORTED)
      echo ""
      echo "Pipeline $STATUS after ${MINS}m${SECS}s"
      echo ""
      CAUSE=$(aws stepfunctions describe-execution \
        --region "$REGION" \
        --execution-arn "$EXEC_ARN" \
        --query 'cause' --output text 2>/dev/null || true)
      [[ -n "$CAUSE" ]] && echo "Cause: $CAUSE"
      echo ""
      echo "Get full history:"
      echo "  aws stepfunctions get-execution-history --region $REGION --execution-arn '$EXEC_ARN' --query 'events[-20:]'"
      exit 1
      ;;
    RUNNING)
      if ! $WATCH; then
        echo "  [$STATUS]  ${MINS}m${SECS}s elapsed"
      fi
      ;;
  esac

  sleep 30
done
