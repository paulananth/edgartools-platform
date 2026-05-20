#!/usr/bin/env bash
# Diagnose a failed pipeline execution: stage, exit code, CloudWatch logs.
# Auto-finds the most-recently-failed execution if no args are given.
#
# Usage:
#   ./scripts/ops/diagnose-execution.sh               # latest failure, any pipeline
#   ./scripts/ops/diagnose-execution.sh silver         # latest silver-mdm-gold run
#   ./scripts/ops/diagnose-execution.sh bootstrap      # latest load-history run
#   ./scripts/ops/diagnose-execution.sh gold
#   ./scripts/ops/diagnose-execution.sh mdm-gold
#   ./scripts/ops/diagnose-execution.sh --exec <arn>  # specific execution

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARG=""
SHORT_NAME=""
EXEC_ARN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)     ENVIRONMENT="${2:?}"; shift 2 ;;
    --region)  AWS_REGION="${2:?}"; shift 2 ;;
    --profile) AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    --exec)    EXEC_ARN="${2:?}"; shift 2 ;;
    -*)        echo "Unknown flag: $1" >&2; exit 2 ;;
    *)         SHORT_NAME="$1"; shift ;;
  esac
done

NAME_PREFIX="edgartools-${ENVIRONMENT}"
CLUSTER="${NAME_PREFIX}-warehouse"
LOG_GROUP="/aws/ecs/${NAME_PREFIX}-warehouse"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }
hr()   { printf '%.0s─' $(seq 1 68); echo; }

ACCOUNT=$(aws_ sts get-caller-identity --query Account --output text 2>/dev/null)
BASE="arn:aws:states:${AWS_REGION}:${ACCOUNT}:stateMachine"

# Short name → SM suffix mapping (same as trigger.sh)
sm_suffix_for() {
  case "$1" in
    bootstrap)  echo "load-history" ;;
    silver)     echo "silver-mdm-gold" ;;
    gold)       echo "gold-refresh" ;;
    mdm-gold)   echo "mdm-gold" ;;
    ownership)  echo "ownership-mdm-gold" ;;
    *)          echo "$1" ;;
  esac
}

# ── Find execution ARN ────────────────────────────────────────────────────────
if [[ -z "$EXEC_ARN" ]]; then
  if [[ -n "$SHORT_NAME" ]]; then
    SM_ARN="${BASE}:${NAME_PREFIX}-$(sm_suffix_for "$SHORT_NAME")"
    EXEC_ARN=$(aws_ stepfunctions list-executions \
      --state-machine-arn "$SM_ARN" \
      --max-results 1 \
      --query 'executions[0].executionArn' \
      --output text 2>/dev/null || true)
    [[ -z "$EXEC_ARN" || "$EXEC_ARN" == "None" ]] && {
      echo "No executions found for ${SHORT_NAME}"
      exit 1
    }
  else
    # Auto-find: scan all pipelines, pick the most recently failed
    echo "Scanning all pipelines for the latest failure…"
    LATEST_FAIL_TIME=0
    for suffix in load-history silver-mdm-gold gold-refresh mdm-gold; do
      sm="${BASE}:${NAME_PREFIX}-${suffix}"
      row=$(aws_ stepfunctions list-executions \
        --state-machine-arn "$sm" \
        --status-filter FAILED \
        --max-results 1 \
        --query 'executions[0].{arn:executionArn,stop:stopDate}' \
        --output json 2>/dev/null || echo '{}')
      arn=$(echo "$row" | python3 -c "import json,sys; print(json.load(sys.stdin).get('arn',''))" 2>/dev/null || true)
      stop=$(echo "$row" | python3 -c "import json,sys; print(json.load(sys.stdin).get('stop',''))" 2>/dev/null || true)
      [[ -z "$arn" || "$arn" == "None" ]] && continue
      t=$(echo "$stop" | python3 -c "
import sys
from datetime import datetime, timezone
s = sys.stdin.read().strip()
if not s: sys.exit()
try:
    dt = datetime.fromisoformat(s.replace('Z','+00:00'))
    print(int(dt.timestamp()))
except: print(0)
" 2>/dev/null || echo 0)
      if [[ "$t" -gt "$LATEST_FAIL_TIME" ]]; then
        LATEST_FAIL_TIME="$t"
        EXEC_ARN="$arn"
      fi
    done
    [[ -z "$EXEC_ARN" ]] && { echo "No recent failures found across all pipelines."; exit 0; }
  fi
fi

echo ""
hr
echo "  DIAGNOSE  ·  ${ENVIRONMENT}  ·  ${AWS_REGION}"
hr
echo "  ${EXEC_ARN##*:}"
echo ""

# ── Execution history summary ─────────────────────────────────────────────────
HISTORY=$(aws_ stepfunctions get-execution-history \
  --execution-arn "$EXEC_ARN" \
  --output json 2>/dev/null || echo '{"events":[]}')

echo "STAGE TRACE"
echo "$HISTORY" | python3 -c "
import json, sys
events = json.load(sys.stdin)['events']
entered, exited, failed = set(), set(), set()
for e in events:
    s = (e.get('stateEnteredEventDetails') or {}).get('name','')
    x = (e.get('stateExitedEventDetails')  or {}).get('name','')
    if s: entered.add(s)
    if x: exited.add(x)
    if e['type'] in ('TaskFailed','MapStateFailed','ExecutionFailed'):
        for n in list(entered - exited): failed.add(n)
for stage in sorted(exited | entered | failed, key=lambda s: next(
        (i for i,e in enumerate(events)
         if (e.get('stateEnteredEventDetails') or {}).get('name') == s), 9999)):
    if stage in exited:    icon = chr(10003)
    elif stage in failed:  icon = chr(10007)
    elif stage in entered: icon = '▶'
    else:                  icon = chr(183)
    print(f'  {icon}  {stage}')
"

# ── Extract failed task info ──────────────────────────────────────────────────
echo ""
echo "FAILED ECS TASK"
TASK_INFO=$(echo "$HISTORY" | python3 -c "
import json, sys
events = json.load(sys.stdin)['events']
for e in reversed(events):
    fd = e.get('taskFailedEventDetails',{})
    if fd and fd.get('cause'):
        try:
            c = json.loads(fd['cause'])
            task_arn = c.get('TaskArn','')
            task_id  = task_arn.split('/')[-1] if task_arn else ''
            task_def = c.get('TaskDefinitionArn','').split('/')[-1]
            for cont in c.get('Containers',[]):
                log_stream = cont.get('LogStreamName','')
                exit_code  = cont.get('ExitCode','?')
                name       = cont.get('Name','')
                overrides  = (c.get('Overrides',{}).get('ContainerOverrides') or [{}])
                cmd        = ' '.join(overrides[0].get('Command',[]) if overrides else [])
                print(task_id)
                print(log_stream)
                print(exit_code)
                print(task_def)
                print(cmd[:100])
            break
        except Exception as ex:
            print('','','?','','')
            break
" 2>/dev/null || true)

TASK_ID=$(echo "$TASK_INFO" | sed -n '1p')
LOG_STREAM=$(echo "$TASK_INFO" | sed -n '2p')
EXIT_CODE=$(echo "$TASK_INFO" | sed -n '3p')
TASK_DEF=$(echo "$TASK_INFO" | sed -n '4p')
CMD=$(echo "$TASK_INFO" | sed -n '5p')

[[ -n "$TASK_DEF" ]] && echo "  TaskDef : ${TASK_DEF}"
[[ -n "$TASK_ID"  ]] && echo "  TaskID  : ${TASK_ID}"
[[ -n "$EXIT_CODE" ]] && echo "  ExitCode: ${EXIT_CODE}"
[[ -n "$CMD"      ]] && echo "  Command : ${CMD}"

# ── Find log stream (fall back to describe-log-streams if not in cause) ───────
if [[ -z "$LOG_STREAM" || "$LOG_STREAM" == "None" ]] && [[ -n "$TASK_ID" ]]; then
  for PREFIX in "warehouse-large" "warehouse-medium" "warehouse-small" "mdm-medium" "mdm-small"; do
    LOG_STREAM=$(aws_ logs describe-log-streams \
      --log-group-name "$LOG_GROUP" \
      --log-stream-name-prefix "${PREFIX}/edgar-warehouse/${TASK_ID}" \
      --query 'logStreams[0].logStreamName' \
      --output text 2>/dev/null || true)
    [[ -n "$LOG_STREAM" && "$LOG_STREAM" != "None" ]] && break
    LOG_STREAM=""
  done
fi

# ── CloudWatch logs ───────────────────────────────────────────────────────────
echo ""
echo "CLOUDWATCH LOGS"
if [[ -z "$LOG_STREAM" ]]; then
  echo "  (no log stream found — task may still be starting or logs may have expired)"
  echo "  Log group: ${LOG_GROUP}"
  [[ -n "$TASK_ID" ]] && echo "  Task ID:   ${TASK_ID}"
else
  echo "  Stream: ${LOG_STREAM}"
  echo ""
  raw_log=$(aws_ logs filter-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-names "$LOG_STREAM" \
    --output json 2>/dev/null || echo '{"events":[]}')
  echo "$raw_log" | python3 -c "
import json, sys
evts = json.load(sys.stdin).get('events',[])
print(f'  Total log events: {len(evts)}')
print()

# Structured events we care about
KEY_EVENTS = {
    'silver_database_hydrated','gold_refresh_started','gold_publish_started',
    'gold_publish_completed','silver_publish_started','silver_publish_completed',
    'pipeline_failed','filing_artifact_pipeline_started',
    'filing_artifact_pipeline_completed','filing_artifact_circuit_open',
    'seed_silver_batches_started','seed_silver_batches_completed',
    'bootstrap_next_started','bootstrap_next_completed','bootstrap_batch_started',
    'bootstrap_batch_completed','error',
}

structured = []
unstructured_tail = []

for e in evts:
    msg = e.get('message','').strip()
    try:
        d = json.loads(msg)
        evt = d.get('event','') or d.get('level','')
        structured.append((evt, d))
    except:
        if msg:
            unstructured_tail.append(msg)

# Show structured key events
if structured:
    print('  KEY EVENTS:')
    for evt, d in structured:
        if evt in KEY_EVENTS or d.get('level') in ('ERROR','CRITICAL','error','critical'):
            icon = chr(10007) if ('fail' in evt.lower() or d.get('level','').lower() in ('error','critical')) else chr(10003)
            extra = {k:v for k,v in d.items()
                     if k not in ('emitted_at','event','run_id','command','level','timestamp')}
            print(f'    {icon} {evt}')
            for k,v in list(extra.items())[:6]:
                print(f'        {k}: {str(v)[:120]}')

# Always show last 30 raw lines (catches tracebacks)
print()
print('  LAST 30 LOG LINES:')
for msg in unstructured_tail[-30:]:
    print(f'  | {msg[:200]}')
# Also show last 30 structured as raw
for evt, d in structured[-30:]:
    pass  # already shown above; show raw json for final few
raw_tail = evts[-15:]
if raw_tail and not unstructured_tail:
    for e in raw_tail:
        print(f'  | {e.get(\"message\",\"\")[:200]}')
"
fi

echo ""
hr
