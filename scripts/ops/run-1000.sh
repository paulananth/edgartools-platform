#!/usr/bin/env bash
# Run bootstrap-phased (load_history) 10 times sequentially to load ~1000 companies.
# Each run picks up the next batch of bootstrap_pending CIKs via seed-universe.
#
# Usage: bash scripts/ops/run-1000.sh [--aws-profile <profile>]
#
# Logs: /tmp/run-1000-<timestamp>/run-<N>.log

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNS=10
AWS_PROFILE_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --aws-profile) AWS_PROFILE_ARG="--aws-profile ${2:?}"; shift 2 ;;
    *) shift ;;
  esac
done

LOG_DIR="/tmp/run-1000-$(date -u +%Y%m%d-%H%M%S)"
mkdir -p "$LOG_DIR"

echo "━━━ 1000-company sequential bootstrap ━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Runs : $RUNS × 100 companies"
echo "  Logs : $LOG_DIR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

SUCCEEDED=0
for i in $(seq 1 $RUNS); do
  LOG="$LOG_DIR/run-${i}.log"
  echo "[$(date -u '+%H:%M:%S UTC')] Starting run $i / $RUNS  (log: $LOG)"

  if bash "$REPO_ROOT/scripts/run-bootstrap.sh" $AWS_PROFILE_ARG 2>&1 | tee "$LOG"; then
    SUCCEEDED=$(( SUCCEEDED + 1 ))
    echo "[$(date -u '+%H:%M:%S UTC')] Run $i SUCCEEDED  ($SUCCEEDED / $RUNS done)"
  else
    echo "[$(date -u '+%H:%M:%S UTC')] Run $i FAILED — stopping." >&2
    echo "  Tail of log:"
    tail -20 "$LOG" >&2
    exit 1
  fi

  echo ""
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "All $RUNS runs SUCCEEDED. ~1000 companies loaded."
echo "Gold tables will refresh in Snowflake within 1 minute of the last run."
echo "Logs: $LOG_DIR"
