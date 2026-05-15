#!/usr/bin/env bash
# Pipeline status: all state machines + running ECS tasks.
#
# Usage:
#   ./scripts/ops/status.sh                  # all pipelines
#   ./scripts/ops/status.sh bootstrap        # one pipeline only
#   ./scripts/ops/status.sh --env dev        # environment override

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARG=""
FILTER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)     ENVIRONMENT="${2:?}"; shift 2 ;;
    --region)  AWS_REGION="${2:?}"; shift 2 ;;
    --profile) AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    -*)        echo "Unknown flag: $1" >&2; exit 2 ;;
    *)         FILTER="$1"; shift ;;
  esac
done

NAME_PREFIX="edgartools-${ENVIRONMENT}"
CLUSTER="${NAME_PREFIX}-warehouse"
aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }
hr()   { printf '%.0s─' $(seq 1 62); echo; }
ACCOUNT=$(aws_ sts get-caller-identity --query Account --output text 2>/dev/null)
BASE="arn:aws:states:${AWS_REGION}:${ACCOUNT}:stateMachine"

# ── State machines to show ────────────────────────────────────────────────────
# Format: "short-name|display-label|sm-suffix|stages..."
declare -a MACHINES=(
  "bootstrap|BOOTSTRAP-PHASED|bootstrap-phased|SeedUniverse BatchBootstrap MdmRun MdmBackfill MdmSync MdmVerify GoldRefresh"
  "silver|SILVER-MDM-GOLD|silver-mdm-gold|SeedSilverBatches SilverBatch MdmRun MdmBackfill MdmSync MdmVerify GoldRefresh"
  "gold|GOLD-REFRESH|gold-refresh|GoldRefresh"
  "mdm-gold|MDM-GOLD|mdm-gold|MdmRun MdmBackfill MdmSync MdmVerify GoldRefresh"
)

show_machine() {
  local short="$1" label="$2" suffix="$3" stages_str="$4"
  local sm_arn="${BASE}:${NAME_PREFIX}-${suffix}"

  echo ""
  hr
  printf "  %-36s· %s · %s\n" "${label}" "${ENVIRONMENT}" "${AWS_REGION}"
  hr

  # Recent executions
  local execs_json
  execs_json=$(aws_ stepfunctions list-executions \
    --state-machine-arn "$sm_arn" \
    --max-results 3 \
    --output json 2>/dev/null || echo '{"executions":[]}')

  echo ""
  echo "RECENT EXECUTIONS"
  echo "$execs_json" | python3 -c "
import json, sys
from datetime import datetime, timezone

execs = json.load(sys.stdin).get('executions', [])
if not execs:
    print('  (none)')
    sys.exit()
for e in execs:
    name   = e['name'][-32:]
    status = e['status']
    start  = e.get('startDate','')
    stop   = e.get('stopDate','')
    def fmt(ts):
        if not ts: return '…'
        try:
            dt = datetime.fromisoformat(ts.replace('Z','+00:00'))
            ago = (datetime.now(timezone.utc) - dt).total_seconds()
            if ago < 3600: return f'{ago/60:.0f}m ago'
            return f'{ago/3600:.1f}h ago'
        except: return ts[-14:-5]
    icon = {'RUNNING':'▶','SUCCEEDED':'✓','FAILED':'✗','ABORTED':'⊘','TIMED_OUT':'⏱'}.get(status,'?')
    print(f'  {icon} {status:10s}  {name:32s}  started {fmt(start)}')
"

  # Latest execution detail
  local latest exec_arn exec_status
  latest=$(echo "$execs_json" | python3 -c "
import json,sys
execs=json.load(sys.stdin).get('executions',[])
if execs: print(json.dumps(execs[0]))
else: print('{}')
")
  exec_arn=$(echo "$latest" | python3 -c "import json,sys; print(json.load(sys.stdin).get('executionArn',''))")
  exec_status=$(echo "$latest" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))")
  [[ -z "$exec_arn" ]] && return

  # Stage progress
  local history
  history=$(aws_ stepfunctions get-execution-history \
    --execution-arn "$exec_arn" \
    --output json 2>/dev/null || echo '{"events":[]}')

  echo ""
  echo "STAGE PROGRESS  (${exec_status})"
  echo "$history" | STAGES="$stages_str" python3 -c "
import json, sys, os
events = json.load(sys.stdin)['events']
stages = os.environ.get('STAGES','').split()
entered, exited, failed = set(), set(), set()
for e in events:
    s = (e.get('stateEnteredEventDetails') or {}).get('name','')
    x = (e.get('stateExitedEventDetails')  or {}).get('name','')
    if s: entered.add(s)
    if x: exited.add(x)
    if e['type'] in ('TaskFailed','MapStateFailed','ExecutionFailed'):
        for n in list(entered - exited): failed.add(n)
for stage in stages:
    if stage in exited:    icon = chr(10003)
    elif stage in failed:  icon = chr(10007)
    elif stage in entered: icon = chr(9654)
    else:                  icon = chr(183)
    print(f'  {icon}  {stage}')
"

  # Batch map progress (if any)
  local map_arn
  map_arn=$(echo "$history" | python3 -c "
import json,sys
for e in json.load(sys.stdin)['events']:
    if e['type']=='MapRunStarted':
        print(e.get('mapRunStartedEventDetails',{}).get('mapRunArn',''))
        break
" 2>/dev/null || true)

  if [[ -n "$map_arn" ]]; then
    echo ""
    echo "BATCH MAP RUN"
    aws_ stepfunctions describe-map-run \
      --map-run-arn "$map_arn" \
      --output json 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
ic=d.get('itemCounts',{})
total=ic.get('total',0); running=ic.get('running',0)
pending=ic.get('pending',0); done=ic.get('resultsWritten',0); failed=ic.get('failed',0)
pct=100*done/total if total else 0
bar='█'*int(pct/4)+'░'*(25-int(pct/4))
print(f'  [{bar}] {pct:.0f}%  done={done}/{total}  running={running}  pending={pending}  failed={failed}')
print(f'  status={d[\"status\"]}')
"
  fi

  # Failure cause
  if [[ "$exec_status" == "FAILED" ]]; then
    echo ""
    echo "FAILURE CAUSE"
    echo "$history" | python3 -c "
import json,sys
events=json.load(sys.stdin)['events']
for e in reversed(events):
    fd=(e.get('taskFailedEventDetails') or e.get('executionFailedEventDetails')
        or e.get('mapRunFailedEventDetails') or {})
    err=fd.get('error',''); cause=fd.get('cause','')
    if err or cause:
        if err: print(f'  error: {err}')
        try:
            c=json.loads(cause)
            for cont in c.get('Containers',[]):
                ec=cont.get('ExitCode','?'); reason=cont.get('Reason','')
                print(f'  exit={ec}  {reason}')
        except:
            if cause: print(f'  {cause[:140]}')
        break
"
  fi
}

# ── Running ECS tasks ─────────────────────────────────────────────────────────
show_ecs_tasks() {
  echo ""
  hr
  echo "  RUNNING ECS TASKS  ·  cluster: ${CLUSTER}"
  hr
  echo ""
  local task_arns
  task_arns=$(aws_ ecs list-tasks \
    --cluster "$CLUSTER" \
    --desired-status RUNNING \
    --query 'taskArns' --output json 2>/dev/null \
    | python3 -c "import json,sys; arns=json.load(sys.stdin); print(' '.join(arns) if arns else '')")

  if [[ -z "$task_arns" ]]; then
    echo "  (none running)"
  else
    aws_ ecs describe-tasks \
      --cluster "$CLUSTER" \
      --tasks $task_arns \
      --output json 2>/dev/null | python3 -c "
import json,sys
from datetime import datetime,timezone
tasks=json.load(sys.stdin)['tasks']
for t in tasks:
    td=t.get('taskDefinitionArn','').split('/')[-1]
    overrides = (t.get('overrides',{}).get('containerOverrides') or [{}])[0]
    cmd_parts = overrides.get('command',[])
    # Derive a human label: first token + key flags (--artifact-policy, --tracking-status-filter)
    label = cmd_parts[0] if cmd_parts else '?'
    for i, part in enumerate(cmd_parts):
        if part == '--artifact-policy' and i+1 < len(cmd_parts):
            label += f' [artifact={cmd_parts[i+1]}]'
        if part == '--tracking-status-filter' and i+1 < len(cmd_parts):
            label += f' [{cmd_parts[i+1]}]'
    started=t.get('startedAt','')
    elapsed=''
    if started:
        dt=datetime.fromisoformat(started.replace('Z','+00:00'))
        mins=(datetime.now(timezone.utc)-dt).total_seconds()/60
        elapsed=f'{mins:.0f}m'
    # Identify owning pipeline from started-by tag if present
    tags = {tag['key']:tag['value'] for tag in t.get('tags',[])}
    pipeline = tags.get('aws:states:stateMachineArn','').split(':stateMachine:')[-1] or ''
    pipeline_hint = f'  via {pipeline}' if pipeline else ''
    print(f'  {td:<38} {elapsed:>5}  {label}{pipeline_hint}')
"
  fi
  echo ""
  hr
  echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
echo ""
hr
printf "  PIPELINE STATUS  ·  %s  ·  %s\n" "${ENVIRONMENT}" "${AWS_REGION}"
hr

FAILED_PIPELINES=()

for entry in "${MACHINES[@]}"; do
  IFS='|' read -r short label suffix stages <<< "$entry"
  if [[ -z "$FILTER" || "$FILTER" == "$short" ]]; then
    show_machine "$short" "$label" "$suffix" "$stages"
    # Track failures for the hint at the bottom — only if failure is recent (< 6h)
    sm_arn="${BASE}:${NAME_PREFIX}-${suffix}"
    latest_exec=$(aws_ stepfunctions list-executions \
      --state-machine-arn "$sm_arn" \
      --max-results 1 \
      --query 'executions[0].{status:status,stop:stopDate}' \
      --output json 2>/dev/null || echo '{}')
    latest_status=$(echo "$latest_exec" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)
    if [[ "$latest_status" == "FAILED" ]]; then
      stop_ts=$(echo "$latest_exec" | python3 -c "
import json,sys
from datetime import datetime,timezone
s=json.load(sys.stdin).get('stop','')
if not s: print(0); exit()
try:
    dt=datetime.fromisoformat(s.replace('Z','+00:00'))
    print(int((datetime.now(timezone.utc)-dt).total_seconds()))
except: print(99999)
" 2>/dev/null || echo "99999")
      # Only flag as active failure if stopped within last 6 hours
      [[ "$stop_ts" -lt 21600 ]] && FAILED_PIPELINES+=("$short")
    fi
  fi
done

show_ecs_tasks

if [[ ${#FAILED_PIPELINES[@]} -gt 0 ]]; then
  echo "  FAILURES DETECTED — to diagnose:"
  for p in "${FAILED_PIPELINES[@]}"; do
    echo "    ./scripts/ops/diagnose-execution.sh ${p}"
  done
  echo "    ./scripts/ops/diagnose-execution.sh        # auto-find latest"
  echo ""
  hr
  echo ""
fi
