#!/usr/bin/env bash
# Show recent CloudWatch logs for running (or recently stopped) ECS tasks.
# No manual ARN hunting — finds tasks and their log streams automatically.
#
# Usage:
#   ./scripts/ops/tail-task.sh                # all currently running tasks
#   ./scripts/ops/tail-task.sh <task-id>      # one specific task
#   ./scripts/ops/tail-task.sh --lines 50     # more lines per task

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARG=""
TASK_ID_ARG=""
LINES=30

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)     ENVIRONMENT="${2:?}"; shift 2 ;;
    --region)  AWS_REGION="${2:?}"; shift 2 ;;
    --profile) AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    --lines)   LINES="${2:?}"; shift 2 ;;
    -*)        echo "Unknown flag: $1" >&2; exit 2 ;;
    *)         TASK_ID_ARG="$1"; shift ;;
  esac
done

NAME_PREFIX="edgartools-${ENVIRONMENT}"
CLUSTER="${NAME_PREFIX}-warehouse"
LOG_GROUP="/aws/ecs/${NAME_PREFIX}-warehouse"
aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }
hr()   { printf '%.0s─' $(seq 1 66); echo; }

# ── Get task IDs ──────────────────────────────────────────────────────────────
if [[ -n "$TASK_ID_ARG" ]]; then
  TASK_IDS=("$TASK_ID_ARG")
else
  mapfile_compat() {
    TASK_IDS=()
    while IFS= read -r line; do
      [[ -n "$line" ]] && TASK_IDS+=("$line")
    done
  }
  mapfile_compat < <(
    aws_ ecs list-tasks --cluster "$CLUSTER" --desired-status RUNNING \
      --query 'taskArns[*]' --output text 2>/dev/null \
    | tr '\t' '\n' \
    | sed 's|.*/||'
  )
fi

if [[ ${#TASK_IDS[@]} -eq 0 ]]; then
  echo "No running tasks in cluster ${CLUSTER}"
  exit 0
fi

echo ""
hr
printf "  TASK LOGS  ·  %s  ·  last %s lines each\n" "$ENVIRONMENT" "$LINES"
hr

# ── Show one task ─────────────────────────────────────────────────────────────
show_task() {
  local task_id="$1"
  echo ""
  hr
  echo "  TASK: ${task_id}"
  hr

  # Task metadata via --output text to avoid json parsing in shell
  local td elapsed status cmd
  td=$(aws_ ecs describe-tasks --cluster "$CLUSTER" --tasks "$task_id" \
    --query 'tasks[0].taskDefinitionArn' --output text 2>/dev/null | sed 's|.*/||' || echo "?")
  status=$(aws_ ecs describe-tasks --cluster "$CLUSTER" --tasks "$task_id" \
    --query 'tasks[0].lastStatus' --output text 2>/dev/null || echo "?")
  local started
  started=$(aws_ ecs describe-tasks --cluster "$CLUSTER" --tasks "$task_id" \
    --query 'tasks[0].startedAt' --output text 2>/dev/null || echo "")
  elapsed=$(python3 -c "
from datetime import datetime, timezone
s='${started}'
if not s or s=='None': print('?m'); exit()
dt=datetime.fromisoformat(s.replace('Z','+00:00'))
print(f'{(datetime.now(timezone.utc)-dt).total_seconds()/60:.0f}m')
" 2>/dev/null || echo "?m")
  cmd=$(aws_ ecs describe-tasks --cluster "$CLUSTER" --tasks "$task_id" \
    --query 'tasks[0].overrides.containerOverrides[0].command' --output text 2>/dev/null \
    | tr '\t' ' ' | cut -c1-90 || echo "?")

  echo "  Def    : ${td}"
  echo "  Status : ${status}  elapsed: ${elapsed}"
  echo "  Cmd    : ${cmd}"

  # Find log stream
  local stream=""
  for prefix in "warehouse-large" "warehouse-medium" "warehouse-small" "mdm-medium" "mdm-small"; do
    stream=$(aws_ logs describe-log-streams \
      --log-group-name "$LOG_GROUP" \
      --log-stream-name-prefix "${prefix}/edgar-warehouse/${task_id}" \
      --query 'logStreams[0].logStreamName' \
      --output text 2>/dev/null || true)
    [[ -n "$stream" && "$stream" != "None" ]] && break
    stream=""
  done

  if [[ -z "$stream" ]]; then
    echo "  Log    : (stream not found yet — task may still be initializing)"
    return
  fi
  echo "  Log    : ${stream}"
  echo ""

  # Fetch and parse log events (filter-log-events is more reliable than get-log-events)
  local raw_events
  raw_events=$(aws_ logs filter-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-names "$stream" \
    --output json 2>/dev/null || echo '{"events":[]}')

  echo "$raw_events" | LINES="$LINES" python3 -c "
import json, sys, os
lines = int(os.environ.get('LINES','30'))
data = json.load(sys.stdin)
evts = data.get('events', [])[-lines:]

if not evts:
    print('  (no log events yet)')
    sys.exit(0)

print(f'  ({len(data.get(\"events\",[]))} total events, showing last {len(evts)})')
print()

KEY = {
    'silver_database_hydrated','silver_database_hydrate_started',
    'bootstrap_batch_started','bootstrap_batch_completed',
    'filing_artifact_pipeline_started','filing_artifact_pipeline_completed',
    'filing_artifact_circuit_open',
    'silver_publish_started','silver_publish_completed',
    'gold_refresh_started','gold_refresh_completed','gold_publish_completed',
    'pipeline_failed','error',
}
for e in evts:
    msg = e.get('message','').strip()
    try:
        d = json.loads(msg)
        evt  = d.get('event','') or d.get('level','') or d.get('message','')
        lvl  = d.get('level','').lower()
        is_key = evt in KEY or lvl in ('error','critical','warning')
        icon = '!' if lvl in ('error','critical') else ('>' if is_key else ' ')
        print(f'  {icon} {evt}')
        if is_key:
            skip = {'emitted_at','event','run_id','command','level','timestamp','logger'}
            for k,v in list(d.items())[:6]:
                if k not in skip:
                    print(f'      {k}: {str(v)[:110]}')
    except Exception:
        if msg:
            print(f'  | {msg[:160]}')
" 2>/dev/null || echo "  (could not parse log events)"
}

for task_id in "${TASK_IDS[@]}"; do
  show_task "$task_id"
done

echo ""
hr
