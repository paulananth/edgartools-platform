#!/usr/bin/env bash
# Run a load on AWS: the loader image CI built for the newest main commit, on one large Fargate task, driven by
# AWS Step Functions. It copies the image to ECR, the captures to the bronze bucket and the logins to Secrets Manager,
# applies infra/terraform/load-machine, starts the task and one execution, and stops the task when it ends. The task
# also stops itself after the root's max_hours, should this script or its machine be gone. While it runs, the Mac's load
# monitor (skills/load-monitoring, Grafana) reads the task's exporter, whose port is open to this Mac's address only.
#
#   RUN=<label> infra/load-pipeline/aws-load.sh                      every lane at once, then the finish, then the mirror's refresh
#   RUN=<label> infra/load-pipeline/aws-load.sh [--finish] <step>... only those steps, in order
#   RUN=<label> infra/load-pipeline/aws-load.sh --prepare            everything up to the apply: no task, no load
#   RUN=<label> infra/load-pipeline/aws-load.sh --plan <step>...     readiness, then those steps planned, read only: for a changed pipeline
#
# RUN is required: a store that was cleared takes a label never used before. One load at a time. The load reads captured
# files only: the task holds no provider identity. The run's state file and logs are in s3://<bronze>/load/runs/<RUN>/.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
terraform_root="$here/../terraform/load-machine"
prepare=false finish=false plan=false
while [ "${1:-}" = "--prepare" ] || [ "${1:-}" = "--finish" ] || [ "${1:-}" = "--plan" ]; do
  case "$1" in --prepare) prepare=true ;; --finish) finish=true ;; --plan) plan=true ;; esac
  shift
done
for argument; do case "$argument" in -*) echo "unknown option $argument" >&2; exit 2 ;; esac; done
[ "$plan" = false ] || [ "$finish" = false ] || { echo "--finish writes the links tables: it has no plan" >&2; exit 2; }
if [ "$#" -eq 0 ] && [ "$plan" = false ]; then finish=true; fi  # a load of every lane ends with the finish
: "${RUN:?set RUN to the run label}"

export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
account=690839588395
[ "$(aws sts get-caller-identity --query Account --output text)" = "$account" ] || { echo "not the platform's AWS account" >&2; exit 2; }
registry="$account.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com"
bucket="edgartools-prod-bronze-$account"
cluster=edgartools-prod-warehouse
name=edgartools-prod-load
config="${CONFIG_HOME:-$HOME/.config/edgartools}"
data="${DATA_HOME:-$HOME/.local/share/edgartools/mdm}"

[ "$(aws ecs list-tasks --cluster "$cluster" --family "$name" --query 'length(taskArns)' --output text)" = 0 ] || {
  echo "a load task is still running: one load at a time" >&2; exit 2; }

caffeinate -dimsu -w $$ 2>/dev/null &

# The image: main's newest commit, copied from ghcr.io to ECR once.
commit="$(git ls-remote https://github.com/paulananth/edgartools-platform.git refs/heads/main | cut -f1)"
source_image="ghcr.io/paulananth/edgartools-platform:loader-sha-${commit}"
image="$registry/edgartools-prod-images:loader-sha-${commit}"
docker pull -q --platform linux/arm64 "$source_image" >/dev/null || {
  echo "no loader image for main's commit ${commit:0:8} yet: wait for CI and the Loader image workflow on it" >&2; exit 2; }
if ! aws ecr describe-images --repository-name edgartools-prod-images --image-ids "imageTag=loader-sha-${commit}" >/dev/null 2>&1; then
  aws ecr get-login-password | docker login --username AWS --password-stdin "$registry" >/dev/null
  docker tag "$source_image" "$image"
  docker push -q "$image" >/dev/null
  docker logout "$registry" >/dev/null
fi
echo "image: commit ${commit:0:8} is in ECR"

in_image() { docker run --rm --network none --entrypoint python "$source_image" "$@"; }
jobs=/app/skills/data-operations/scripts/load_jobs.py
lanes="$(in_image "$jobs" --lane-count)"
names="$(in_image "$jobs" --list | awk '{print $3}')"
for step; do  # a name the image does not know is refused before anything is copied or billed
  printf '%s\n' "$names" | grep -qx -- "$step" || { echo "no step named $step in the loader image" >&2; exit 2; }
done

# The captures the load jobs file reads, each under the root its source names, and no other folder. A folder already copied costs one listing.
folders="$(in_image -c 'import sys; sys.path.insert(0, "/app/skills/data-operations/scripts"); import load_jobs as L
print("\n".join(sorted({d.get("capture_root", "captures") + " " + d["capture"] for s in L.load_jobs() for d in s.get("deliveries", ())})))')"
while read -r root folder; do
  aws s3 sync --only-show-errors --exclude '.DS_Store' --exclude '*/.DS_Store' "$data/$root/$folder" "s3://$bucket/load/$root/$folder"
done <<< "$folders"
echo "captures: in s3://$bucket/load"

[ -f "$terraform_root/backend.hcl" ] || cp "$terraform_root/backend.hcl.example" "$terraform_root/backend.hcl"
tf() { terraform -chdir="$terraform_root" "$@"; }
tf init -input=false -backend-config=backend.hcl >/dev/null
ipv4='^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'
mac="$(curl -fsS --max-time 20 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || true)"  # the address AWS sees this Mac at
opening=()
if [[ "$mac" =~ $ipv4 ]]; then opening=(-var "metrics_cidr=$mac/32")
else echo "monitor: this Mac's public address could not be read, so the task's exporter is open to no one" >&2; fi
tf apply -input=false -auto-approve -var "image=$image" -var "run=$RUN" -var "lanes=$lanes" ${opening[@]+"${opening[@]}"} >/dev/null
machine="$(tf output -raw state_machine_arn)"
task_definition="$(tf output -raw task_definition_arn)"
secret="$(tf output -raw secret_arn)"
metrics_group="$(tf output -raw metrics_security_group_id)"
exporter_port="$(tf output -raw exporter_port)"
echo "terraform: applied"

# The logins, each file in base64 under its key. The two settings that name a path on this machine name the task's.
private="$(mktemp -d)"; trap 'rm -rf "$private"' EXIT
CONFIG="$config" python3 - "$private/logins.json" <<'PY'
import base64, json, os, re, sys
from pathlib import Path

config, task = Path(os.environ["CONFIG"]), "/data/home/.config/edgartools"
paths = {"WORKER_ENV": ("BOOKKEEPING_MANIFEST_ROOT", "file:///data/manifests"),
         "MIRROR_ENV": ("MIRROR_SNOWFLAKE_PRIVATE_KEY_PATH", f"{task}/mirror-operator/mirror-operator.p8")}
files = {"OWNER_ENV": "hosted/owner.env", "WORKER_ENV": "hosted/worker.env", "GOVERNANCE_ENV": "hosted/governance.env",
         "READER_ENV": "hosted/reader.env", "MIRROR_ENV": "mirror-operator/mirror-operator.env",
         "MIRROR_KEY": "mirror-operator/mirror-operator.p8"}
held = {}
for key, file in files.items():
    body = (config / file).read_bytes()
    if key in paths:
        setting, value = paths[key]
        text, found = re.subn(rf"(?m)^(export\s+)?{setting}=.*$", lambda m: f"{m.group(1) or ''}{setting}={value}", body.decode())
        if not found:
            raise SystemExit(f"{file} sets no {setting}")
        body = text.encode()
    held[key] = base64.b64encode(body).decode()
Path(sys.argv[1]).write_text(json.dumps(held))
PY
aws secretsmanager put-secret-value --secret-id "$secret" --secret-string "file://$private/logins.json" >/dev/null
rm -rf "$private"
echo "logins: in Secrets Manager"
[ "$prepare" = false ] || { echo "prepared: no task started"; exit 0; }

running="$(aws stepfunctions list-executions --state-machine-arn "$machine" --status-filter RUNNING --query 'length(executions)' --output text)"
[ "$running" = 0 ] || { echo "an execution is still running: one load at a time" >&2; exit 2; }

network="$(aws ec2 describe-subnets --filters 'Name=tag:Name,Values=edgartools-prod-public-*' --query 'join(`,`, Subnets[].SubnetId)' --output text)"
group="$(aws ec2 describe-security-groups --filters Name=group-name,Values=edgartools-prod-ecs-public --query 'SecurityGroups[0].GroupId' --output text)"
task="$(aws ecs run-task --cluster "$cluster" --task-definition "$task_definition" --launch-type FARGATE --count 1 \
  --network-configuration "awsvpcConfiguration={subnets=[$network],securityGroups=[$group,$metrics_group],assignPublicIp=ENABLED}" \
  --query 'tasks[0].taskArn' --output text)"
[ "$task" != None ] || { echo "the load task did not start" >&2; exit 1; }
echo "task ${task##*/}: starting"
execution='' result=''
# The load monitor runs in the repository's environment (`uv run`), as its skill does: the system python3 can be too old for it.
monitor() { (cd "$here/../.." && uv run --no-sync python skills/load-monitoring/scripts/monitoring.py target "$@") >/dev/null 2>&1; }
stop() {  # whatever ends this script: no execution is left waiting, and the task is gone, its record copied, before it returns
  monitor || echo "monitor: could not point Grafana back at this Mac's exporter: monitoring.py target" >&2
  [ -z "$execution" ] || [ "$result" != RUNNING ] ||
    aws stepfunctions stop-execution --execution-arn "$execution" --cause "the launch script ended" >/dev/null || true
  aws ecs stop-task --cluster "$cluster" --task "$task" --reason "the load ended" >/dev/null &&
    aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task" && echo "task ${task##*/}: stopped"
}
trap stop EXIT

status() { aws ecs describe-tasks --cluster "$cluster" --tasks "$task" --query 'tasks[0].lastStatus' --output text; }
worker() { aws ecs describe-tasks --cluster "$cluster" --tasks "$task" --query 'tasks[0].containers[?name==`worker`].lastStatus | [0]' --output text; }
polling=PENDING
for _ in $(seq 180); do  # half an hour for the images and the captures: an execution starts only once the worker polls
  polling="$(worker)"
  [ "$polling" = RUNNING ] || [ "$(status)" = STOPPED ] && break
  sleep 10
done
[ "$polling" = RUNNING ] || {
  aws ecs describe-tasks --cluster "$cluster" --tasks "$task" --query 'tasks[0].[stoppedReason, containers[].[name, exitCode, reason]]' >&2
  exit 1; }
echo "task ${task##*/}: running"
# The monitor is never a reason to stop the load: a lookup that fails leaves Grafana reading this Mac's exporter.
eni="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task" --query \
  'tasks[0].attachments[?type==`ElasticNetworkInterface`] | [0].details[?name==`networkInterfaceId`].value | [0]' --output text || true)"
address="$(aws ec2 describe-network-interfaces --network-interface-ids "$eni" \
  --query 'NetworkInterfaces[0].Association.PublicIp' --output text 2>/dev/null || true)"
if [ "${#opening[@]}" -gt 0 ] && [[ "$address" =~ $ipv4 ]] && monitor "$address:$exporter_port"; then
  echo "monitor: Grafana on this Mac reads the task's exporter (http://127.0.0.1:3001)"
else
  echo "monitor: not running on this Mac (skills/load-monitoring/scripts/monitoring.py up), so nothing reads the task's exporter"
fi

if [ "$#" -gt 0 ]; then
  steps="$(printf '%s\n' "$@" | jq -R 'select(length > 0)' | jq -sc .)"
  input="{\"steps\": ${steps}, \"plan\": ${plan}, \"force\": false, \"finish\": ${finish}}"
else
  steps="every lane"
  input="{\"plan\": ${plan}, \"force\": false, \"finish\": ${finish}}"
fi
execution="$(aws stepfunctions start-execution --state-machine-arn "$machine" --input "$input" --query executionArn --output text)"
echo "started ${execution##*:} on commit ${commit:0:8}: ${lanes} lanes at once, steps ${steps}, plan ${plan}, finish ${finish}, run ${RUN}"

result=RUNNING unread=0
while [ "$result" = RUNNING ]; do
  sleep 60
  if result="$(aws stepfunctions describe-execution --execution-arn "$execution" --query status --output text)"; then
    unread=0
  else
    result=RUNNING unread=$((unread + 1))
    [ "$unread" -lt 30 ] || { echo "the execution could not be read for half an hour: stopping the task" >&2; exit 1; }
  fi
  if [ "$result" = RUNNING ] && [ "$(status || echo UNKNOWN)" = STOPPED ]; then
    aws stepfunctions stop-execution --execution-arn "$execution" --cause "the load task stopped" >/dev/null
    result=TASK_STOPPED
  fi
done
echo "execution ${execution##*:} ${result}; record: $(tf output -raw record)"
[ "$result" = SUCCEEDED ] || {
  aws stepfunctions get-execution-history --execution-arn "$execution" --reverse-order --max-results 20 | jq -r '.events[]
    | (.taskFailedEventDetails // .taskTimedOutEventDetails // .executionFailedEventDetails
       // .executionTimedOutEventDetails // .executionAbortedEventDetails // empty) | "\(.error // "-"): \(.cause // "-")"' | head -3
  exit 1; }

# The mirror applies the load's writes now, not at its next interval, and Gold reads them once it returns. A refresh that
# fails leaves the load done: the mirror applies them at its interval.
[ "$plan" = false ] || exit 0
(cd "$here/../.." && uv run --no-sync python skills/data-platform/scripts/exposure/mirror_refresh.py) || true
