#!/usr/bin/env bash
# Launch a bounded warehouse ECS task with the active task definition.
#
# This is the operator entry point for CIK-scoped repair and validation work.
# It deliberately exposes a small allowlist of commands instead of accepting
# arbitrary shell fragments, derives the task/container/network configuration
# from AWS, and emits the task ARN for scripts/ops/tail-task.sh.
#
# Usage:
#   bash scripts/ops/run-ecs-task.sh <profile> --env <dev|prod> \
#     --aws-profile <profile> --aws-account-id <12-digit-id> --cik-list <ciks> [options]
#
# Profiles:
#   artifact-registration  bootstrap-batch with the selected artifact policy
#   per-filing             bootstrap-fundamentals --mode per-filing
#   entity-facts           bootstrap-fundamentals --mode entity-facts
#   thirteenf              bootstrap-fundamentals --mode thirteenf
#
# Examples:
#   bash scripts/ops/run-ecs-task.sh artifact-registration --env prod \
#     --aws-profile sec_platform_deployer --aws-account-id 690839588395 \
#     --cik-list 320193 --artifact-policy all_attachments --wait
#   bash scripts/ops/run-ecs-task.sh per-filing --env prod \
#     --aws-profile sec_platform_deployer --aws-account-id 690839588395 \
#     --cik-list 320193 --wait

set -euo pipefail

usage() {
  sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'
}

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

[[ $# -gt 0 ]] || { usage >&2; exit 2; }
if [[ "$1" == -h || "$1" == --help ]]; then
  usage
  exit 0
fi
PROFILE="$1"
shift

ENVIRONMENT=""
AWS_PROFILE_NAME=""
AWS_ACCOUNT_ID=""
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
CIK_LIST=""
TASK_SIZE="medium"
ARTIFACT_POLICY="all_attachments"
RUN_ID=""
WAIT=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?--env requires a value}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?--aws-profile requires a value}"; shift 2 ;;
    --aws-account-id) AWS_ACCOUNT_ID="${2:?--aws-account-id requires a value}"; shift 2 ;;
    --aws-region) AWS_REGION="${2:?--aws-region requires a value}"; shift 2 ;;
    --cik-list) CIK_LIST="${2:?--cik-list requires a value}"; shift 2 ;;
    --task-size) TASK_SIZE="${2:?--task-size requires a value}"; shift 2 ;;
    --artifact-policy) ARTIFACT_POLICY="${2:?--artifact-policy requires a value}"; shift 2 ;;
    --run-id) RUN_ID="${2:?--run-id requires a value}"; shift 2 ;;
    --wait) WAIT=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done

case "$PROFILE" in
  artifact-registration|per-filing|entity-facts|thirteenf) ;;
  *) fail "profile must be artifact-registration, per-filing, entity-facts, or thirteenf" ;;
esac
[[ "$ENVIRONMENT" == dev || "$ENVIRONMENT" == prod ]] || fail "--env must be dev or prod"
[[ "$AWS_ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || fail "--aws-account-id must be a 12-digit account ID"
[[ -n "$CIK_LIST" ]] || fail "--cik-list is required; unbounded task launches are not supported"
[[ "$CIK_LIST" =~ ^[0-9]+(,[0-9]+)*$ ]] || fail "--cik-list must be comma-separated numeric CIKs"
case "$TASK_SIZE" in small|medium|large) ;; *) fail "--task-size must be small, medium, or large" ;; esac

aws_cli() {
  aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION" "$@"
}

[[ -n "$AWS_PROFILE_NAME" ]] || fail "--aws-profile is required"
command -v aws >/dev/null || fail "aws CLI is required"
command -v jq >/dev/null || fail "jq is required"

actual_account="$(aws_cli sts get-caller-identity --query Account --output text)"
[[ "$actual_account" == "$AWS_ACCOUNT_ID" ]] || fail "profile resolves to account $actual_account, expected $AWS_ACCOUNT_ID"

name_prefix="edgartools-${ENVIRONMENT}"
cluster="${name_prefix}-warehouse"
family="${name_prefix}-${TASK_SIZE}"
task_definition="$(aws_cli ecs list-task-definitions --family-prefix "$family" --status ACTIVE --sort DESC --max-results 1 --query 'taskDefinitionArns[0]' --output text)"
[[ -n "$task_definition" && "$task_definition" != None ]] || fail "no active task definition for $family"
container_name="$(aws_cli ecs describe-task-definition --task-definition "$task_definition" --query 'taskDefinition.containerDefinitions[0].name' --output text)"
[[ -n "$container_name" && "$container_name" != None ]] || fail "could not resolve the task container name"

subnets="$(aws_cli ec2 describe-subnets \
  --filters "Name=tag:Project,Values=edgartools" "Name=tag:Environment,Values=$ENVIRONMENT" "Name=tag:Name,Values=${name_prefix}-public-*" \
  --query 'sort_by(Subnets,&AvailabilityZone)[].SubnetId' --output json)"
security_groups="$(aws_cli ec2 describe-security-groups \
  --filters "Name=group-name,Values=${name_prefix}-ecs-public" "Name=tag:Project,Values=edgartools" "Name=tag:Environment,Values=$ENVIRONMENT" \
  --query 'SecurityGroups[].GroupId' --output json)"
[[ "$(jq 'length' <<<"$subnets")" -gt 0 ]] || fail "no public subnets found for $name_prefix"
[[ "$(jq 'length' <<<"$security_groups")" -gt 0 ]] || fail "no ECS security group found for $name_prefix"
network_configuration="$(jq -cn --argjson subnets "$subnets" --argjson groups "$security_groups" \
  '{awsvpcConfiguration:{subnets:$subnets,securityGroups:$groups,assignPublicIp:"ENABLED"}}')"

if [[ -z "$RUN_ID" ]]; then
  RUN_ID="operator-${PROFILE}-$(date -u +%Y%m%d%H%M%S)"
fi
case "$PROFILE" in
  artifact-registration)
    command=(bootstrap-batch --cik-list "$CIK_LIST" --artifact-policy "$ARTIFACT_POLICY" --run-id "$RUN_ID")
    ;;
  per-filing|entity-facts|thirteenf)
    command=(bootstrap-fundamentals --mode "$PROFILE" --cik-list "$CIK_LIST" --run-id "$RUN_ID")
    ;;
esac
overrides="$(jq -cn --arg name "$container_name" --argjson command "$(printf '%s\n' "${command[@]}" | jq -R . | jq -sc .)" \
  '{containerOverrides:[{name:$name,command:$command}]}')"

echo "profile=$PROFILE"
echo "account=$actual_account"
echo "cluster=$cluster"
echo "task_definition=$task_definition"
echo "container=$container_name"
echo "run_id=$RUN_ID"
echo "command=${command[*]}"
if "$DRY_RUN"; then
  echo "dry_run=true"
  exit 0
fi

task_arn="$(aws_cli ecs run-task \
  --cluster "$cluster" \
  --launch-type FARGATE \
  --task-definition "$task_definition" \
  --network-configuration "$network_configuration" \
  --overrides "$overrides" \
  --query 'tasks[0].taskArn' --output text)"
[[ -n "$task_arn" && "$task_arn" != None ]] || fail "ECS did not return a task ARN"
echo "task_arn=$task_arn"
echo "tail=bash scripts/ops/tail-task.sh --env $ENVIRONMENT --profile $AWS_PROFILE_NAME ${task_arn##*/}"

if "$WAIT"; then
  aws_cli ecs wait tasks-stopped --cluster "$cluster" --tasks "$task_arn"
  aws_cli ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" \
    --query 'tasks[0].{lastStatus:lastStatus,stoppedReason:stoppedReason,exitCode:containers[0].exitCode}' --output json
fi
