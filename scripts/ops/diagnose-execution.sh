#!/usr/bin/env bash
# Diagnose a failed Step Functions execution: failure stage, exit code, CloudWatch logs.
# Replaces the 5-step manual pattern: list-executions → get-history → describe-tasks → logs.
#
# Usage:
#   ./scripts/ops/diagnose-execution.sh                          # latest bootstrap_phased
#   ./scripts/ops/diagnose-execution.sh --sm gold_refresh        # latest gold-refresh
#   ./scripts/ops/diagnose-execution.sh --sm silver_mdm_gold
#   ./scripts/ops/diagnose-execution.sh --exec <execution-arn>   # specific execution
#   ./scripts/ops/diagnose-execution.sh --task <ecs-task-id>     # skip to task logs only

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARG=""
SM_NAME="bootstrap_phased"
EXEC_ARN=""
TASK_ID_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)     ENVIRONMENT="${2:?}"; shift 2 ;;
    --region)  AWS_REGION="${2:?}"; shift 2 ;;
    --profile) AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    --sm)      SM_NAME="${2:?}"; shift 2 ;;
    --exec)    EXEC_ARN="${2:?}"; shift 2 ;;
    --task)    TASK_ID_ARG="${2:?}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

NAME_PREFIX="edgartools-${ENVIRONMENT}"
CLUSTER="${NAME_PREFIX}-warehouse"
LOG_GROUP="/aws/ecs/${NAME_PREFIX}-warehouse"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }
hr()   { printf '%.0s─' $(seq 1 70); echo; }

# ── Find execution ARN ────────────────────────────────────────────────────────
if [[ -z "$TASK_ID_ARG" && -z "$EXEC_ARN" ]]; then
  SM_SLUG="${SM_NAME//_/-}"
  ACCOUNT=$(aws_ sts get-caller-identity --query Account --output text 2>/dev/null)
  SM_ARN="arn:aws:states:${AWS_REGION}:${ACCOUNT}:stateMachine:${NAME_PREFIX}-${SM_SLUG}"
  EXEC_ARN=$(aws_ stepfunctions list-executions \
    --state-machine-arn "$SM_ARN" \
    --max-results 1 \
    --query 'executions[0].executionArn' \
    --output text 2>/dev/null || true)
  [[ -z "$EXEC_ARN" || "$EXEC_ARN" == "None" ]] && {
    echo "No executions found for ${SM_NAME} in ${ENVIRONMENT}"
    exit 1
  }
fi

echo ""
hr
echo "  DIAGNOSE EXECUTION  ·  ${ENVIRONMENT}"
hr

# ── Parse execution history ───────────────────────────────────────────────────
TASK_ID="$TASK_ID_ARG"

if [[ -n "$EXEC_ARN" ]]; then
  echo "  ARN: ${EXEC_ARN##*:}"
  echo ""

  HISTORY_OUT=$(aws_ stepfunctions get-execution-history \
    --execution-arn "$EXEC_ARN" \
    --output json 2>/dev/null)

  echo "$HISTORY_OUT" | python3 "${SCRIPT_DIR}/parse_execution_history.py"

  # Extract latest task ID for log fetching
  TASK_ID=$(echo "$HISTORY_OUT" | python3 "${SCRIPT_DIR}/parse_execution_history.py" 2>/dev/null \
    | grep "^LATEST_TASK_ID=" | cut -d= -f2 || true)
fi

if [[ -z "$TASK_ID" ]]; then
  echo ""
  echo "  No failed ECS task found in history."
  hr
  exit 0
fi

# ── ECS task metadata ─────────────────────────────────────────────────────────
echo ""
echo "FAILED TASK: ${TASK_ID}"

aws_ ecs describe-tasks \
  --cluster "$CLUSTER" \
  --tasks "$TASK_ID" \
  --output json 2>/dev/null | python3 "${SCRIPT_DIR}/describe_tasks.py" | while IFS=$'\t' read -r tid td elapsed cmd; do
  echo "  TaskDef: ${td}"
  echo "  Elapsed: ${elapsed}"
  echo "  Command: ${cmd}"
done

# Get exit code
aws_ ecs describe-tasks \
  --cluster "$CLUSTER" \
  --tasks "$TASK_ID" \
  --output json 2>/dev/null | python3 -c "
import json, sys
tasks = json.load(sys.stdin).get('tasks',[])
if not tasks:
    print('  (task not in ECS history — may have expired)')
    sys.exit()
t = tasks[0]
print('  StopCode:', t.get('stopCode','?'))
for c in t.get('containers',[]):
    ec = c.get('exitCode','?')
    reason = c.get('reason','') or ''
    print(f'  Exit={ec}  {reason}')
"

# ── CloudWatch logs ───────────────────────────────────────────────────────────
echo ""
echo "CLOUDWATCH LOGS:"

FULL_STREAM=""
for PREFIX in "warehouse-large" "warehouse-medium" "warehouse-small" "mdm-medium" "mdm-small"; do
  FULL_STREAM=$(aws_ logs describe-log-streams \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name-prefix "${PREFIX}/edgar-warehouse/${TASK_ID}" \
    --query 'logStreams[0].logStreamName' \
    --output text 2>/dev/null || true)
  [[ -n "$FULL_STREAM" && "$FULL_STREAM" != "None" ]] && break
  FULL_STREAM=""
done

if [[ -z "$FULL_STREAM" ]]; then
  echo "  (no log stream found for task ${TASK_ID})"
  hr
  exit 0
fi

echo "  Stream: $FULL_STREAM"
STREAM_META=$(aws_ logs describe-log-streams \
  --log-group-name "$LOG_GROUP" \
  --log-stream-name-prefix "$FULL_STREAM" \
  --query 'logStreams[0].{first:firstEventTimestamp,last:lastEventTimestamp}' \
  --output json 2>/dev/null)
FIRST_TS=$(echo "$STREAM_META" | python3 -c "import json,sys; print(json.load(sys.stdin).get('first',0))" 2>/dev/null || echo "0")
LAST_TS=$(echo  "$STREAM_META" | python3 -c "import json,sys; print(json.load(sys.stdin).get('last',9999999999999))" 2>/dev/null || echo "9999999999999")

aws_ logs filter-log-events \
  --log-group-name "$LOG_GROUP" \
  --log-stream-names "$FULL_STREAM" \
  --start-time "$FIRST_TS" \
  --end-time "$LAST_TS" \
  --output json 2>/dev/null | python3 -c "
import json, sys
evts = json.load(sys.stdin).get('events',[])
print(f'  Events: {len(evts)}')
KEY_EVENTS = {
    'silver_database_hydrated', 'gold_refresh_started', 'gold_publish_started',
    'gold_publish_completed', 'silver_publish_started', 'silver_publish_completed',
    'pipeline_failed', 'filing_artifact_pipeline_started', 'filing_artifact_pipeline_completed',
    'filing_artifact_circuit_open', 'seed_silver_batches_started', 'seed_silver_batches_completed',
}
for e in evts:
    msg = e.get('message','')
    try:
        d = json.loads(msg)
        evt = d.get('event','')
        if evt in KEY_EVENTS:
            extra = {k:v for k,v in d.items() if k not in ('emitted_at','event','run_id','command')}
            icon = '✗' if 'fail' in evt else '✓'
            print(f'  {icon} {evt}')
            for k, v in extra.items():
                val = str(v)[:120]
                print(f'      {k}: {val}')
    except:
        if msg.strip() and not msg.startswith('{'):
            print(f'  ! {msg[:200]}')
"

echo ""
hr
