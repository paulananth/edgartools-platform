#!/usr/bin/env bash
# Start a load on the pipeline: the loader image CI built for the newest main commit runs readiness, then each step.
#
#   infra/load-pipeline/load.sh [--plan] <step> [<step> ...]
#
# Runs on this machine's AWS Step Functions Local. It refuses when main's newest commit has no loader image yet (CI has not
# passed on it, or the image is still building). It waits for the execution and exits 0 only when it succeeded.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
plan=false
if [ "${1:-}" = "--plan" ]; then plan=true; shift; fi
[ "$#" -gt 0 ] || { echo "name at least one step" >&2; exit 2; }

commit="$(git ls-remote https://github.com/paulananth/edgartools-platform.git refs/heads/main | cut -f1)"
image="ghcr.io/paulananth/edgartools-platform:loader-sha-${commit}"
docker pull -q "$image" >/dev/null || {
  echo "no loader image for main's commit ${commit:0:8} yet: wait for CI and the Loader image workflow on it" >&2; exit 2; }
export COMMIT="$commit"

endpoint=http://localhost:8083
sfn() { AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local aws stepfunctions --region us-east-1 --endpoint-url "$endpoint" --output json "$@"; }
compose=(docker compose -f "$here/compose.yml")

"${compose[@]}" up -d stepfunctions >/dev/null
for _ in $(seq 30); do sfn list-activities >/dev/null 2>&1 && break; sleep 1; done
activity="$(sfn create-activity --name edgartools-load | jq -r .activityArn)"
definition="$(sed "s|\${activity}|${activity}|g" "$here/state-machine.asl.json")"
machine="arn:aws:states:us-east-1:123456789012:stateMachine:edgartools-load"
if sfn describe-state-machine --state-machine-arn "$machine" >/dev/null 2>&1; then
  sfn update-state-machine --state-machine-arn "$machine" --definition "$definition" >/dev/null
else
  sfn create-state-machine --name edgartools-load --definition "$definition" \
    --role-arn arn:aws:iam::123456789012:role/edgartools-load >/dev/null
fi
"${compose[@]}" up -d worker >/dev/null

steps="$(printf '%s\n' "$@" | jq -R . | jq -sc .)"
execution="$(sfn start-execution --state-machine-arn "$machine" --input "{\"steps\": ${steps}, \"plan\": ${plan}}" | jq -r .executionArn)"
echo "started ${execution##*:} on commit ${commit:0:8}: steps ${steps}, plan ${plan}"

caffeinate -dimsu -w $$ 2>/dev/null &
while :; do
  status="$(sfn describe-execution --execution-arn "$execution" | jq -r .status)"
  [ "$status" = RUNNING ] || break
  sleep 60
done
echo "execution ${status}"
[ "$status" = SUCCEEDED ] || {
  sfn get-execution-history --execution-arn "$execution" --reverse-order --max-results 10 \
    | jq -r '.events[] | (.taskFailedEventDetails // .executionFailedEventDetails // empty) | "\(.error): \(.cause)"' | head -3
  exit 1; }
