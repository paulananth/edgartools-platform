#!/usr/bin/env bash
# Pipeline status: latest bootstrap_phased execution + batch progress + running tasks.
#
# Usage:
#   ./scripts/ops/status.sh
#   ./scripts/ops/status.sh --env prod
#   ./scripts/ops/status.sh --env dev --region us-west-2

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)      ENVIRONMENT="${2:?}"; shift 2 ;;
    --region)   AWS_REGION="${2:?}"; shift 2 ;;
    --profile)  AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

NAME_PREFIX="edgartools-${ENVIRONMENT}"
CLUSTER="${NAME_PREFIX}-warehouse"
SM_ARN="arn:aws:states:${AWS_REGION}:$(aws ${AWS_PROFILE_ARG} sts get-caller-identity \
  --query Account --output text 2>/dev/null):stateMachine:${NAME_PREFIX}-bootstrap-phased"

aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }

hr() { printf '%.0s─' $(seq 1 60); echo; }

echo ""
hr
echo "  BOOTSTRAP-PHASED  ·  ${ENVIRONMENT}  ·  ${AWS_REGION}"
hr

# ── Latest executions ─────────────────────────────────────────────────────────
echo ""
echo "RECENT EXECUTIONS"
aws_ stepfunctions list-executions \
  --state-machine-arn "$SM_ARN" \
  --max-results 4 \
  --output json 2>/dev/null | python3 -c "
import json, sys
from datetime import datetime, timezone

execs = json.load(sys.stdin).get('executions', [])
for e in execs:
    name  = e['name'][-28:]
    status = e['status']
    start  = e['startDate'][-14:-5]
    stop   = e.get('stopDate', '')
    stop_s = stop[-14:-5] if stop else '(running)'
    icon = {'RUNNING':'▶','SUCCEEDED':'✓','FAILED':'✗','ABORTED':'⊘'}.get(status, '?')
    print(f'  {icon} {status:10s}  {name}  {start} → {stop_s}')
"

# ── Latest running execution ─────────────────────────────────────────────────
LATEST=$(aws_ stepfunctions list-executions \
  --state-machine-arn "$SM_ARN" \
  --max-results 1 \
  --query 'executions[0]' \
  --output json 2>/dev/null)

STATUS=$(echo "$LATEST" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))")
EXEC_ARN=$(echo "$LATEST" | python3 -c "import json,sys; print(json.load(sys.stdin).get('executionArn',''))")

if [[ -z "$EXEC_ARN" ]]; then
  echo "  (no executions found)"
  exit 0
fi

# ── Step-by-step stage progress ──────────────────────────────────────────────
echo ""
echo "STAGE PROGRESS  ($STATUS)"
aws_ stepfunctions get-execution-history \
  --execution-arn "$EXEC_ARN" \
  --output json 2>/dev/null | python3 -c "
import json, sys

events = json.load(sys.stdin)['events']
stages = ['SeedUniverse','BatchBootstrap','MdmRun','MdmBackfill','MdmSync','MdmVerify','GoldRefresh']
entered  = set()
exited   = set()
failed   = set()

for e in events:
    s = (e.get('stateEnteredEventDetails') or {}).get('name','')
    x = (e.get('stateExitedEventDetails')  or {}).get('name','')
    if s: entered.add(s)
    if x: exited.add(x)
    if e['type'] in ('TaskFailed','MapStateFailed','ExecutionFailed'):
        for s in entered - exited:
            failed.add(s)

for stage in stages:
    if stage in exited:
        icon = '✓'
    elif stage in failed:
        icon = '✗'
    elif stage in entered:
        icon = '▶'
    else:
        icon = '·'
    print(f'  {icon}  {stage}')
"

# ── Batch map run progress ────────────────────────────────────────────────────
MAP_ARN=$(aws_ stepfunctions get-execution-history \
  --execution-arn "$EXEC_ARN" \
  --output json 2>/dev/null | python3 -c "
import json, sys
for e in json.load(sys.stdin)['events']:
    if e['type'] == 'MapRunStarted':
        print(e.get('mapRunStartedEventDetails',{}).get('mapRunArn',''))
        break
" 2>/dev/null || true)

if [[ -n "$MAP_ARN" ]]; then
  echo ""
  echo "BATCH MAP RUN"
  aws_ stepfunctions describe-map-run \
    --map-run-arn "$MAP_ARN" \
    --output json 2>/dev/null | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
ic = d.get('itemCounts', {})
total     = ic.get('total', 0)
running   = ic.get('running', 0)
pending   = ic.get('pending', 0)
succeeded = ic.get('resultsWritten', 0)
failed    = ic.get('failed', 0)
pct  = 100 * succeeded / total if total else 0
bar  = '█' * int(pct / 4) + '░' * (25 - int(pct / 4))
print(f'  [{bar}] {pct:.0f}%')
print(f'  done={succeeded}/{total}  running={running}  pending={pending}  failed={failed}')
print(f'  status={d[\"status\"]}  tolerance=10%')
"
fi

# ── Running ECS tasks ──────────────────────────────────────────────────────────
echo ""
echo "RUNNING ECS TASKS  (cluster: ${CLUSTER})"
TASK_ARNS=$(aws_ ecs list-tasks \
  --cluster "$CLUSTER" \
  --desired-status RUNNING \
  --query 'taskArns' \
  --output json 2>/dev/null | python3 -c "
import json, sys
arns = json.load(sys.stdin)
print(' '.join(arns) if arns else '')
")

if [[ -z "$TASK_ARNS" ]]; then
  echo "  (none running)"
else
  aws_ ecs describe-tasks \
    --cluster "$CLUSTER" \
    --tasks $TASK_ARNS \
    --output json 2>/dev/null | python3 -c "
import json, sys
from datetime import datetime, timezone

tasks = json.load(sys.stdin)['tasks']
for t in tasks:
    td  = t.get('taskDefinitionArn','').split('/')[-1]
    cmd = ' '.join((t.get('overrides',{}).get('containerOverrides') or [{}])[0].get('command',[]))
    started = t.get('startedAt','')
    elapsed = ''
    if started:
        dt = datetime.fromisoformat(started.replace('Z','+00:00'))
        mins = (datetime.now(timezone.utc) - dt).total_seconds() / 60
        elapsed = f'{mins:.0f}m'
    cpu = t.get('cpu','?')
    mem_mb = int(cpu) * 2 if cpu and str(cpu).isdigit() else '?'
    print(f'  {td}  {elapsed:>6}  {cmd[:55]}')
"
fi

# ── Last failure cause ────────────────────────────────────────────────────────
EXEC_STATUS=$(echo "$LATEST" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))")
if [[ "$EXEC_STATUS" == "FAILED" ]]; then
  echo ""
  echo "FAILURE CAUSE"
  aws_ stepfunctions get-execution-history \
    --execution-arn "$EXEC_ARN" \
    --output json 2>/dev/null | python3 -c "
import json, sys
events = json.load(sys.stdin)['events']
for e in reversed(events):
    fd = e.get('taskFailedEventDetails') or e.get('executionFailedEventDetails') or e.get('mapRunFailedEventDetails') or {}
    cause = fd.get('cause','')
    err   = fd.get('error','')
    if err or cause:
        print(f'  error: {err}')
        try:
            c = json.loads(cause)
            for cont in c.get('Containers',[]):
                ec = cont.get('ExitCode','?')
                reason = cont.get('Reason','')
                print(f'  exit={ec}  {reason}')
        except:
            if cause:
                print(f'  {cause[:120]}')
        break
"
fi

echo ""
hr
