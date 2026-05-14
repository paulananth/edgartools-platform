#!/usr/bin/env bash
# Batch task log analyser: stage, SEC 503s, circuit breaker, rate.
# Checks all currently running ECS tasks in one pass.
#
# Usage:
#   ./scripts/ops/batch-logs.sh
#   ./scripts/ops/batch-logs.sh --env dev
#   ./scripts/ops/batch-logs.sh --task-id <ecs-task-id>   # single task

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

aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }

hr() { printf '%.0s─' $(seq 1 70); echo; }

ANALYSE_PY='
import json, sys, math
from datetime import datetime, timezone

raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception:
    print("  (no logs yet)")
    sys.exit()

msgs = []
for e in data.get("events", []):
    try:
        msgs.append(json.loads(e["message"]))
    except:
        pass

if not msgs:
    print("  (no structured events yet)")
    sys.exit()

counts = {}
for m in msgs:
    k = m.get("event","")
    counts[k] = counts.get(k, 0) + 1

# Current stage
STAGES = [
    "silver_database_hydrated",
    "bronze_capture_started",
    "bronze_capture_completed",
    "silver_apply_started",
    "silver_apply_completed",
    "filing_artifact_pipeline_started",
    "filing_artifact_circuit_open",
    "filing_artifact_pipeline_completed",
    "silver_publish_completed",
    "pipeline_failed",
]
stage = next((s for s in reversed(STAGES) if counts.get(s, 0) > 0), "initialising")
print(f"  Stage        : {stage}")

# Bronze/silver progress
bc = next((m for m in msgs if m.get("event") == "bronze_capture_completed"), None)
sa = next((m for m in reversed(msgs) if m.get("event") == "silver_apply_progress"), None)
if bc:
    print(f"  Bronze CIKs  : {bc.get('cik_count','')}  ({bc.get('raw_object_count','')} raw objects, {bc.get('duration_seconds',0):.0f}s)")
if sa:
    done = sa.get("ciks_processed",0)
    total = sa.get("ciks_total",0)
    print(f"  Silver apply : {done}/{total} CIKs")

# Artifact pipeline
ap = next((m for m in msgs if m.get("event") == "filing_artifact_pipeline_started"), None)
apc = next((m for m in reversed(msgs) if m.get("event") == "filing_artifact_pipeline_completed"), None)
co = next((m for m in msgs if m.get("event") == "filing_artifact_circuit_open"), None)
if ap:
    acc = ap.get("accession_count", "?")
    print(f"  Artifact acc : {acc} to process")
if apc:
    print(f"  Artifact done: {apc.get('rows_written',0)} rows, {apc.get('errors',0)} errors")
if co:
    print(f"  Circuit open : {co.get('consecutive_errors','?')} consecutive failures triggered breaker")

# SEC pull stats
started = counts.get("sec_pull_started", 0)
retried = counts.get("sec_pull_retry", 0)
failed_pulls = counts.get("sec_pull_failed", 0)
art_failed = counts.get("filing_artifact_failed", 0)
if started:
    ok = counts.get("sec_pull_completed", 0)
    fail_pct = 100 * failed_pulls / started if started else 0
    print(f"  SEC pulls    : {ok} ok / {retried} retried / {failed_pulls} failed  ({fail_pct:.0f}% fail rate)")
    if art_failed:
        print(f"  Art failures : {art_failed}  (logged & skipped)")

# Max consecutive artifact failures
consec = 0
max_c = 0
for m in msgs:
    if m.get("event") == "filing_artifact_failed":
        consec += 1
        max_c = max(max_c, consec)
    elif m.get("event") == "sec_pull_completed":
        consec = 0
if max_c:
    pct = 100 * max_c / 20
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
    print(f"  Circuit brk  : [{bar}] {max_c}/20 max consecutive")

# Elapsed
first_ts = data["events"][0]["timestamp"] / 1000 if data.get("events") else None
last_ts  = data["events"][-1]["timestamp"] / 1000 if data.get("events") else None
if first_ts and last_ts:
    elapsed_min = (last_ts - first_ts) / 60
    print(f"  Log span     : {elapsed_min:.0f} min  ({len(data.get(\"events\",[]))} lines)")

# Failure summary
pf = next((m for m in reversed(msgs) if m.get("event") == "pipeline_failed"), None)
if pf:
    print(f"  FAILED       : {pf.get('error_message','?')[:80]}")
'

if [[ -n "$SINGLE_TASK" ]]; then
  TASK_IDS=("$SINGLE_TASK")
else
  mapfile -t TASK_IDS < <(aws_ ecs list-tasks \
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

# Fetch task metadata once for all tasks
TASK_ARN_LIST=$(aws_ ecs list-tasks \
  --cluster "$CLUSTER" \
  --desired-status RUNNING \
  --query 'taskArns' \
  --output json 2>/dev/null | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin)))")

declare -A TASK_CMD
declare -A TASK_ELAPSED
declare -A TASK_DEF
if [[ -n "$TASK_ARN_LIST" ]]; then
  while IFS= read -r line; do
    eval "$line"
  done < <(aws_ ecs describe-tasks \
    --cluster "$CLUSTER" \
    --tasks $TASK_ARN_LIST \
    --output json 2>/dev/null | python3 -c "
import json, sys
from datetime import datetime, timezone
tasks = json.load(sys.stdin)['tasks']
for t in tasks:
    tid = t['taskArn'].split('/')[-1]
    td  = t.get('taskDefinitionArn','').split('/')[-1]
    cmd = ' '.join((t.get('overrides',{}).get('containerOverrides') or [{}])[0].get('command',[]))
    started = t.get('startedAt','')
    elapsed = ''
    if started:
        dt = datetime.fromisoformat(started.replace('Z','+00:00'))
        elapsed = str(int((datetime.now(timezone.utc)-dt).total_seconds()/60)) + 'm'
    # Emit as shell assignments
    print(f'TASK_CMD[\"{tid}\"]=\$(printf \"%s\" \"{cmd[:50]}\")' )
    print(f'TASK_ELAPSED[\"{tid}\"]=\"{elapsed}\"')
    print(f'TASK_DEF[\"{tid}\"]=\"{td}\"')
")
fi

echo ""
hr
echo "  BATCH TASK LOGS  ·  ${ENVIRONMENT}  ·  cluster: ${CLUSTER}"
hr

for TASK_ID in "${TASK_IDS[@]}"; do
  SHORT="${TASK_ID:0:20}"
  DEF="${TASK_DEF[$TASK_ID]:-?}"
  CMD="${TASK_CMD[$TASK_ID]:-?}"
  ELAPSED="${TASK_ELAPSED[$TASK_ID]:-?}"

  echo ""
  echo "TASK ${SHORT}  [${DEF}  ${ELAPSED}]"
  echo "  cmd: ${CMD}"

  # Determine log stream prefix (medium or small)
  LOG_PREFIX="warehouse-medium/edgar-warehouse/${TASK_ID}"
  STREAM_CHECK=$(aws_ logs describe-log-streams \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name-prefix "$LOG_PREFIX" \
    --query 'length(logStreams)' \
    --output text 2>/dev/null || echo "0")

  if [[ "$STREAM_CHECK" == "0" ]]; then
    # Try small prefix
    LOG_PREFIX="warehouse-small/edgar-warehouse/${TASK_ID}"
    STREAM_CHECK=$(aws_ logs describe-log-streams \
      --log-group-name "$LOG_GROUP" \
      --log-stream-name-prefix "$LOG_PREFIX" \
      --query 'length(logStreams)' \
      --output text 2>/dev/null || echo "0")
  fi

  if [[ "$STREAM_CHECK" == "0" ]]; then
    echo "  (log stream not found yet)"
    continue
  fi

  # Full log stream name (append task ID if needed)
  FULL_STREAM=$(aws_ logs describe-log-streams \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name-prefix "$LOG_PREFIX" \
    --query 'logStreams[0].logStreamName' \
    --output text 2>/dev/null || echo "")

  if [[ -z "$FULL_STREAM" || "$FULL_STREAM" == "None" ]]; then
    echo "  (no log stream)"
    continue
  fi

  aws_ logs get-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$FULL_STREAM" \
    --output json 2>/dev/null | python3 -c "$ANALYSE_PY"
done

echo ""
hr
