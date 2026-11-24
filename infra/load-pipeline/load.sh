#!/usr/bin/env bash
# Start a load on the pipeline: the loader image CI built for the newest main commit runs readiness, then the load.
#
#   infra/load-pipeline/load.sh [--plan]                        every lane of the chain file at once, then the finish
#   infra/load-pipeline/load.sh [--plan] [--finish] <step>...   only those steps, in order
#
# The lanes, their steps, order and waits come from the chain file in the image: every lane runs at once, and each step
# with the workers the chain file gives it.
# Runs on this machine's AWS Step Functions Local. It refuses when main's newest commit has no loader image yet (CI has not
# passed on it, or the image is still building), and while another execution runs (one load at a time). It waits, up to
# LOAD_DEADLINE_HOURS (default 72; then it stops the execution), and exits 0 only when the execution succeeded.
# RUN, STORES, CAPTURES, PROVING and LOGS pass through to the worker, with load_chain.py's defaults.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
plan=false finish=false
while [ "${1:-}" = "--plan" ] || [ "${1:-}" = "--finish" ]; do
  if [ "$1" = "--plan" ]; then plan=true; else finish=true; fi
  shift
done
[ "$plan" = false ] || [ "$finish" = false ] || { echo "--finish writes the links tables: it has no plan" >&2; exit 2; }
if [ "$#" -eq 0 ] && [ "$plan" = false ]; then finish=true; fi  # a load of every lane ends with the finish

commit="$(git ls-remote https://github.com/paulananth/edgartools-platform.git refs/heads/main | cut -f1)"
image="ghcr.io/paulananth/edgartools-platform:loader-sha-${commit}"
docker pull -q "$image" >/dev/null || {
  echo "no loader image for main's commit ${commit:0:8} yet: wait for CI and the Loader image workflow on it" >&2; exit 2; }

export COMMIT="$commit" RUN="${RUN:-fresh-v1}"
export STORES="${STORES:-$HOME/.config/edgartools/hosted}"
export CAPTURES="${CAPTURES:-$HOME/.local/share/edgartools/mdm/captures}"
export PROVING="${PROVING:-$HOME/.local/share/edgartools/mdm/proving}"
export LOGS="${LOGS:-$HOME/.local/share/edgartools/load-logs}"
mkdir -p "$LOGS"
lock="$LOGS/load.sh.lock"  # one load.sh at a time: the running check and the activity's replacement must not interleave
mkdir "$lock" 2>/dev/null || { echo "another load.sh holds $lock (remove it if none runs)" >&2; exit 2; }
trap 'rmdir "$lock"' EXIT

endpoint=http://localhost:8083
sfn() { AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local aws stepfunctions --region us-east-1 --endpoint-url "$endpoint" --output json "$@"; }
compose=(docker compose -f "$here/compose.yml")

export ACTIVITY_ARN=pending  # compose reads the worker's variables on any `up`; the real one is set once the emulator answers
"${compose[@]}" up -d stepfunctions >/dev/null
for _ in $(seq 30); do sfn list-activities >/dev/null 2>&1 && break; sleep 1; done
machine="$(sfn list-state-machines | jq -r '.stateMachines[] | select(.name == "edgartools-load") | .stateMachineArn')"
if [ -n "$machine" ]; then
  running="$(sfn list-executions --state-machine-arn "$machine" --status-filter RUNNING | jq -r '.executions | length')"
  [ "$running" = 0 ] || { echo "an execution is still running: one load at a time" >&2; exit 2; }
fi
# A new activity per load: a long poll an older worker still holds would take the task and lose it.
while IFS= read -r old; do
  sfn delete-activity --activity-arn "$old" >/dev/null
done < <(sfn list-activities | jq -r '.activities[] | select(.name | startswith("edgartools-load")) | .activityArn')
ACTIVITY_ARN="$(sfn create-activity --name "edgartools-load-$(date +%Y%m%d%H%M%S)-$$" | jq -r .activityArn)"
export ACTIVITY_ARN
definition="$(sed "s|\${activity}|${ACTIVITY_ARN}|g" "$here/state-machine.asl.json")"
if [ -n "$machine" ]; then
  sfn update-state-machine --state-machine-arn "$machine" --definition "$definition" >/dev/null
else
  machine="$(sfn create-state-machine --name edgartools-load --definition "$definition" \
    --role-arn arn:aws:iam::123456789012:role/edgartools-load | jq -r .stateMachineArn)"
fi
"${compose[@]}" up -d worker >/dev/null

if [ "$#" -gt 0 ]; then
  steps="$(printf '%s\n' "$@" | jq -R 'select(length > 0)' | jq -sc .)"
  input="{\"steps\": ${steps}, \"plan\": ${plan}, \"finish\": ${finish}}"
else
  steps="every lane"
  input="{\"plan\": ${plan}, \"finish\": ${finish}}"
fi
execution="$(sfn start-execution --state-machine-arn "$machine" --input "$input" | jq -r .executionArn)"
echo "started ${execution##*:} on commit ${commit:0:8}: steps ${steps}, plan ${plan}, finish ${finish}, run ${RUN}"

caffeinate -dimsu -w $$ 2>/dev/null &
deadline=$(( $(date +%s) + ${LOAD_DEADLINE_HOURS:-72} * 3600 ))
status=RUNNING
while [ "$status" = RUNNING ]; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    sfn stop-execution --execution-arn "$execution" --error Deadline --cause "load.sh waited ${LOAD_DEADLINE_HOURS:-72} h" >/dev/null
    echo "execution ${execution##*:} stopped at the deadline" >&2; exit 1
  fi
  sleep 60
  status="$(sfn describe-execution --execution-arn "$execution" | jq -r .status)" || status=RUNNING  # a missed reading waits a minute
done
echo "execution ${execution##*:} ${status}"
[ "$status" = SUCCEEDED ] || {
  sfn get-execution-history --execution-arn "$execution" --reverse-order --max-results 20 | jq -r '.events[]
    | (.taskFailedEventDetails // .taskTimedOutEventDetails // .executionFailedEventDetails
       // .executionTimedOutEventDetails // .executionAbortedEventDetails // empty) | "\(.error // "-"): \(.cause // "-")"' | head -3
  exit 1; }
