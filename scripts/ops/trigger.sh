#!/usr/bin/env bash
# Trigger a state machine by short name. Replaces looking up ARNs every time.
#
# Available pipelines:
#   recent             edgartools-dev-daily-incremental  (index-driven incremental load;
#                        formerly targeted edgartools-dev-bootstrap, retired by
#                        state-machine-consolidation ticket 06 -- zero schedule, one
#                        execution ever)
#   load-history       load_history  (EXPLICIT ONLY: seed new companies → batches → MDM → gold)
#   silver             silver_mdm_gold   (re-process already-loaded bronze)
#   silver-active      silver_mdm_gold with tracking_status_filter=active
#   silver-pending     silver_mdm_gold with tracking_status_filter=bootstrap_pending
#   gold               gold_refresh      (rebuild gold from current silver, aka
#                        FactPublishtoGold at every MDM Pipeline Machine's own
#                        tail -- see state-machine-consolidation ticket 07)
#   mdm                mdm  (state-machine-consolidation ticket 07: the single MDM
#                        machine -- Mastering..Reconcile, ends before gold-refresh;
#                        replaces mdm-gold, which had no head of its own and was
#                        deleted outright as a 100% redundant duplicate of this)
#   mdm-run            mdm_utility mode=mdm_run
#   mdm-verify         mdm_utility mode=mdm_verify_graph
#   mdm-sync           mdm_utility mode=mdm_sync_graph
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

[[ -z "$PIPELINE" ]] && { echo "Usage: $0 [--env dev] <pipeline>"; echo "Pipelines: recent load-history silver silver-active silver-pending gold mdm mdm-run mdm-verify mdm-sync"; exit 2; }

NAME_PREFIX="edgartools-${ENVIRONMENT}"
ACCOUNT=$(aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" sts get-caller-identity --query Account --output text 2>/dev/null)
BASE="arn:aws:states:${AWS_REGION}:${ACCOUNT}:stateMachine"

aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }

case "$PIPELINE" in
  recent)
    SM="${BASE}:${NAME_PREFIX}-daily-incremental"
    INPUT='{"refresh_mode": "daily"}'
    LABEL="daily_incremental (index-driven incremental load)"
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
    SM="${BASE}:${NAME_PREFIX}-mdm-utility"
    INPUT='{"mode": "mdm_run"}'
    LABEL="mdm_run (mdm_utility mode=mdm_run)"
    ;;
  mdm)
    SM="${BASE}:${NAME_PREFIX}-mdm"
    INPUT='{}'
    LABEL="mdm (Mastering → BackpropagateIdsToSilver → Infer Relationships → Publish → Publish Relationships → Reconcile; no gold-refresh -- chain 'gold' afterward if needed)"
    ;;
  mdm-verify)
    SM="${BASE}:${NAME_PREFIX}-mdm-utility"
    INPUT='{"mode": "mdm_verify_graph"}'
    LABEL="mdm_verify_graph (mdm_utility mode=mdm_verify_graph)"
    ;;
  mdm-sync)
    SM="${BASE}:${NAME_PREFIX}-mdm-utility"
    INPUT='{"mode": "mdm_sync_graph"}'
    LABEL="mdm_sync_graph (mdm_utility mode=mdm_sync_graph)"
    ;;
  *)
    echo "Unknown pipeline: $PIPELINE" >&2
    echo "Valid: recent load-history silver silver-active silver-pending gold mdm mdm-run mdm-verify mdm-sync" >&2
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
