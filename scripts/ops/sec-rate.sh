#!/usr/bin/env bash
# Analyse SEC request rates across all running batch tasks.
# Shows per-task req/min, aggregate req/sec, and 503 breakdown.
#
# Usage:
#   ./scripts/ops/sec-rate.sh
#   ./scripts/ops/sec-rate.sh --env dev --last-minutes 30

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARG=""
LAST_MINUTES=60

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)           ENVIRONMENT="${2:?}"; shift 2 ;;
    --region)        AWS_REGION="${2:?}"; shift 2 ;;
    --profile)       AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    --last-minutes)  LAST_MINUTES="${2:?}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

NAME_PREFIX="edgartools-${ENVIRONMENT}"
CLUSTER="${NAME_PREFIX}-warehouse"
LOG_GROUP="/aws/ecs/${NAME_PREFIX}-warehouse"

aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }
hr() { printf '%.0s─' $(seq 1 65); echo; }

START_MS=$(( ($(date -u +%s) - LAST_MINUTES * 60) * 1000 ))

# Collect running task IDs
mapfile -t TASK_IDS < <(aws_ ecs list-tasks \
  --cluster "$CLUSTER" \
  --desired-status RUNNING \
  --query 'taskArns' \
  --output json 2>/dev/null | python3 -c "
import json, sys
for a in json.load(sys.stdin):
    print(a.split('/')[-1])
")

echo ""
hr
echo "  SEC REQUEST RATE  ·  ${ENVIRONMENT}  ·  last ${LAST_MINUTES}min"
hr

if [[ ${#TASK_IDS[@]} -eq 0 ]]; then
  echo "  No running tasks."
  exit 0
fi

RATE_PY="
import json, sys
from datetime import datetime, timezone
from collections import defaultdict

data = json.load(sys.stdin)
msgs = []
for e in data.get('events', []):
    try:
        d = json.loads(e['message'])
        d['_ts'] = e['timestamp'] / 1000
        msgs.append(d)
    except:
        pass

if not msgs:
    print('  (no events)')
    sys.exit()

sec_msgs = [m for m in msgs if m.get('event','').startswith('sec_pull')]
if not sec_msgs:
    print('  (no SEC pull events yet)')
    sys.exit()

# Time range
first = min(m['_ts'] for m in sec_msgs)
last  = max(m['_ts'] for m in sec_msgs)
span_min = max((last - first) / 60, 0.017)  # min 1 second

# Per-host counts
by_host = defaultdict(lambda: defaultdict(int))
for m in sec_msgs:
    host = m.get('host', 'unknown')
    evt  = m.get('event','')
    by_host[host][evt] += 1

total_started = sum(v.get('sec_pull_started',0) for v in by_host.values())
total_failed  = sum(v.get('sec_pull_failed',0)  for v in by_host.values())
total_ok      = sum(v.get('sec_pull_completed',0) for v in by_host.values())
req_per_min   = total_started / span_min
req_per_sec   = req_per_min / 60

fail_pct = 100 * total_failed / total_started if total_started else 0

print(f'  Span         : {span_min:.1f} min  ({len(sec_msgs)} events)')
print(f'  Rate         : {req_per_min:.1f} req/min  =  {req_per_sec:.2f} req/sec')
print(f'  Outcomes     : {total_ok} ok / {total_failed} failed ({fail_pct:.0f}%)')
print()
print('  By host:')
for host, counts in sorted(by_host.items()):
    s = counts.get('sec_pull_started',0)
    ok = counts.get('sec_pull_completed',0)
    f = counts.get('sec_pull_failed',0)
    r = counts.get('sec_pull_retry',0)
    rpm = s / span_min
    print(f'    {host:<22s}  {s:5d} started  {ok:5d} ok  {f:5d} failed  {rpm:.1f} req/min')

# 503 vs other failures
status_counts = defaultdict(int)
for m in sec_msgs:
    if m.get('event') == 'sec_pull_failed':
        sc = m.get('status_code', m.get('error', 'unknown'))
        status_counts[str(sc)] += 1
if status_counts:
    print()
    print('  Failure breakdown:')
    for sc, n in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f'    {sc}: {n}')
"

echo ""
GRAND_STARTED=0
GRAND_FAILED=0
GRAND_SPAN=0

for TASK_ID in "${TASK_IDS[@]}"; do
  echo "── Task ${TASK_ID:0:20}"

  FULL_STREAM=$(aws_ logs describe-log-streams \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name-prefix "warehouse-medium/edgar-warehouse/${TASK_ID}" \
    --query 'logStreams[0].logStreamName' \
    --output text 2>/dev/null || true)

  if [[ -z "$FULL_STREAM" || "$FULL_STREAM" == "None" ]]; then
    FULL_STREAM=$(aws_ logs describe-log-streams \
      --log-group-name "$LOG_GROUP" \
      --log-stream-name-prefix "warehouse-small/edgar-warehouse/${TASK_ID}" \
      --query 'logStreams[0].logStreamName' \
      --output text 2>/dev/null || true)
  fi

  if [[ -z "$FULL_STREAM" || "$FULL_STREAM" == "None" ]]; then
    echo "  (stream not found)"
    echo ""
    continue
  fi

  aws_ logs get-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$FULL_STREAM" \
    --start-time "$START_MS" \
    --output json 2>/dev/null | python3 -c "$RATE_PY"
  echo ""
done

echo "SEC limit: 10 req/sec per IP  (per EDGAR policy)"
echo "Target  : ≤3 req/sec total  (concurrency 3 × 1s sleep × ~2 req/accession)"
hr
