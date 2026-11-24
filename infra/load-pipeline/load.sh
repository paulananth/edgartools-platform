#!/usr/bin/env bash
# Start a load on the pipeline: the loader image CI built for the newest main commit runs readiness, then the load.
#
#   infra/load-pipeline/load.sh [--plan|--force]                every lane of the load jobs file at once, then the finish
#   --force: force publish: each load ignores the Change Journal and processes every document of its source again (use a new RUN)
#   infra/load-pipeline/load.sh [--plan] [--finish] <step>...   only those steps, in order
#
# The lanes, their steps, order and waits come from the load jobs file in the image: every lane runs at once, and each step
# with the workers the load jobs file gives it.
# Runs on this machine's AWS Step Functions Local. It refuses when main's newest commit has no loader image yet (CI has not
# passed on it, or the image is still building), and while another execution runs (one load at a time). It waits, up to
# LOAD_DEADLINE_HOURS (default 2: the operator's window; a miss is reported once and the load goes on), and exits 0 only when the execution succeeded.
# RUN, STORES, CAPTURES, PROVING and LOGS pass through to the worker, with load_jobs.py's defaults.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
plan=false finish=false force=false
while [ "${1:-}" = "--plan" ] || [ "${1:-}" = "--finish" ] || [ "${1:-}" = "--force" ]; do
  case "$1" in --plan) plan=true ;; --finish) finish=true ;; --force) force=true ;; esac
  shift
done
[ "$force" = false ] || [ "$plan" = false ] || { echo "--force makes a publication again: a plan has none to make" >&2; exit 2; }
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
# The lanes the compute carries at once (load_jobs.py owns the number, in no platform's terms; this script only applies it to the
# state machine): its vCPUs over the widest first step's workers, read from the load jobs file in the image
# (the emulator takes no computed value, and a lane queued in the worker times out on its heartbeat).
at_once="$(docker run --rm --network none --entrypoint python "$image" /app/skills/data-operations/scripts/load_jobs.py --lanes-at-once --capacity "${CAPACITY:-local}")"
definition="$(sed "s|\${activity}|${ACTIVITY_ARN}|g" "$here/state-machine.asl.json" | jq -c --argjson n "$at_once" '.States["Run lanes"].MaxConcurrency = $n')"
if [ -n "$machine" ]; then
  sfn update-state-machine --state-machine-arn "$machine" --definition "$definition" >/dev/null
else
  machine="$(sfn create-state-machine --name edgartools-load --definition "$definition" \
    --role-arn arn:aws:iam::123456789012:role/edgartools-load | jq -r .stateMachineArn)"
fi
"${compose[@]}" up -d worker exporter >/dev/null

if [ "$#" -gt 0 ]; then
  steps="$(printf '%s\n' "$@" | jq -R 'select(length > 0)' | jq -sc .)"
  input="{\"steps\": ${steps}, \"plan\": ${plan}, \"force\": ${force}, \"finish\": ${finish}}"
else
  steps="every lane"
  input="{\"plan\": ${plan}, \"force\": ${force}, \"finish\": ${finish}}"
fi
execution="$(sfn start-execution --state-machine-arn "$machine" --input "$input" | jq -r .executionArn)"
echo "started ${execution##*:} on commit ${commit:0:8}: ${at_once} lanes at once, steps ${steps}, plan ${plan}, force ${force}, finish ${finish}, run ${RUN}"

caffeinate -dimsu -w $$ 2>/dev/null &
deadline=$(( $(date +%s) + ${LOAD_DEADLINE_HOURS:-2} * 3600 )) missed=false  # the operator's window: a miss is reported, never a stop
status=RUNNING
while [ "$status" = RUNNING ]; do
  if [ "$missed" = false ] && [ "$(date +%s)" -ge "$deadline" ]; then
    missed=true
    echo "DEADLINE MISSED: execution ${execution##*:} still runs after ${LOAD_DEADLINE_HOURS:-2} h; it goes on (read each job's time in the state file)" >&2
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
