#!/usr/bin/env bash
# Trigger a state machine by short name. Replaces looking up ARNs every time.
#
# Available pipelines:
#   recent             edgartools-dev-bootstrap  (DEFAULT: recent filings for active universe)
#   load-history       load_history  (EXPLICIT ONLY: seed new companies → batches → MDM → gold)
#   silver             silver_mdm_gold   (re-process already-loaded bronze)
#   silver-active      silver_mdm_gold with tracking_status_filter=active
#   silver-pending     silver_mdm_gold with tracking_status_filter=bootstrap_pending
#   gold               gold_refresh      (rebuild gold from current silver)
#   mdm-run            standalone mdm_run
#   mdm-verify         standalone mdm_verify_graph
#   mdm-sync           standalone mdm_sync_graph
#
# Usage:
#   ./scripts/ops/trigger.sh recent
#   ./scripts/ops/trigger.sh load-history   # explicit only
#   ./scripts/ops/trigger.sh silver-active
#   ./scripts/ops/trigger.sh gold
#   ./scripts/ops/trigger.sh --env dev recent

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARG=""
PIPELINE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)    ENVIRONMENT="${2:?}"; shift 2 ;;
    --region) AWS_REGION="${2:?}"; shift 2 ;;
    --profile) AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    -*) echo "Unknown flag: $1" >&2; exit 2 ;;
    *)  PIPELINE="$1"; shift ;;
  esac
done

[[ -z "$PIPELINE" ]] && { echo "Usage: $0 [--env dev] <pipeline>"; echo "Pipelines: recent load-history silver silver-active silver-pending gold mdm-gold mdm-run mdm-verify mdm-sync"; exit 2; }

NAME_PREFIX="edgartools-${ENVIRONMENT}"
ACCOUNT=$(aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" sts get-caller-identity --query Account --output text 2>/dev/null)
BASE="arn:aws:states:${AWS_REGION}:${ACCOUNT}:stateMachine"

aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }

case "$PIPELINE" in
  recent)
    SM="${BASE}:${NAME_PREFIX}-bootstrap"
    INPUT='{}'
    LABEL="bootstrap (recent filings, active universe)"
    ;;
  load-history)
    SM="${BASE}:${NAME_PREFIX}-load-history"
    INPUT='{"universe_limit": "100"}'
    LABEL="load_history (seed new companies → batches → MDM → gold)"
    ;;
  silver)
    SM="${BASE}:${NAME_PREFIX}-silver-mdm-gold"
    INPUT='{"tracking_status_filter": "all"}'
    LABEL="silver_mdm_gold (all)"
    ;;
  silver-active)
    SM="${BASE}:${NAME_PREFIX}-silver-mdm-gold"
    INPUT='{"tracking_status_filter": "active"}'
    LABEL="silver_mdm_gold (active only)"
    ;;
  silver-pending)
    SM="${BASE}:${NAME_PREFIX}-silver-mdm-gold"
    INPUT='{"tracking_status_filter": "bootstrap_pending"}'
    LABEL="silver_mdm_gold (bootstrap_pending only)"
    ;;
  gold)
    SM="${BASE}:${NAME_PREFIX}-gold-refresh"
    INPUT='{}'
    LABEL="gold_refresh"
    ;;
  mdm-run)
    SM="${BASE}:${NAME_PREFIX}-mdm-run"
    INPUT='{}'
    LABEL="mdm_run"
    ;;
  mdm-gold)
    SM="${BASE}:${NAME_PREFIX}-mdm-gold"
    INPUT='{}'
    LABEL="mdm_gold (MDM chain → Neo4j sync → gold-refresh, no silver batch)"
    ;;
  ownership)
    SM="${BASE}:${NAME_PREFIX}-ownership-mdm-gold"
    INPUT='{}'
    LABEL="ownership_mdm_gold (parse bronze XMLs → MDM persons → Neo4j → gold)"
    ;;
  mdm-verify)
    SM="${BASE}:${NAME_PREFIX}-mdm-verify-graph"
    INPUT='{}'
    LABEL="mdm_verify_graph"
    ;;
  mdm-sync)
    SM="${BASE}:${NAME_PREFIX}-mdm-sync-graph"
    INPUT='{}'
    LABEL="mdm_sync_graph"
    ;;
  *)
    echo "Unknown pipeline: $PIPELINE" >&2
    echo "Valid: recent load-history silver silver-active silver-pending gold mdm-run mdm-verify mdm-sync" >&2
    exit 2
    ;;
esac

RUN_NAME="${PIPELINE//-/_}-$(date -u +%Y%m%d-%H%M%S)"
echo "Triggering: ${LABEL}"
echo "  SM : ${SM##*:stateMachine:}"
echo "  Run: ${RUN_NAME}"
echo "  In : ${INPUT}"
echo ""

RESULT=$(aws_ stepfunctions start-execution \
  --state-machine-arn "$SM" \
  --name "$RUN_NAME" \
  --input "$INPUT" \
  --output json 2>&1)

EXEC_ARN=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('executionArn',''))" 2>/dev/null || true)

if [[ -n "$EXEC_ARN" ]]; then
  echo "Started: ${EXEC_ARN##*:}"
  echo ""
  echo "Monitor with:"
  echo "  ./scripts/ops/status.sh"
  echo "  ./scripts/ops/diagnose-execution.sh --exec ${EXEC_ARN}"
else
  echo "$RESULT"
  exit 1
fi
