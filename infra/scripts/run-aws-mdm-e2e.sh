#!/usr/bin/env bash
# AWS-only MDM hosted graph e2e and Step Functions status check.
#
# Usage:
#   bash infra/scripts/run-aws-mdm-e2e.sh --env dev
#   bash infra/scripts/run-aws-mdm-e2e.sh --env dev --status-only

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  run-aws-mdm-e2e.sh --env <dev|prod> [options]

Checks every state machine listed in infra/aws-<env>-application.json, then
runs the AWS-only MDM hosted graph e2e chain unless --status-only is provided.

Options:
  --env <dev|prod>            Environment. Required.
  --aws-profile <profile>     AWS CLI profile. Default: AWS_PROFILE or normal AWS CLI resolution.
  --aws-region <region>       AWS region. Default: us-east-1.
  --application-file <path>   Deployment summary JSON. Default: infra/aws-<env>-application.json.
  --mdm-run-limit <n>         Limit for mdm run. Default: 5.
  --graph-limit <n>           Limit for backfill/sync graph. Default: 100.
  --status-only               Only report Step Functions status; do not start executions.
  -h, --help                  Show this help.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

ENVIRONMENT=""
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
APPLICATION_FILE=""
MDM_RUN_LIMIT=5
GRAPH_LIMIT=100
RUN_E2E=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --application-file) APPLICATION_FILE="${2:?}"; shift 2 ;;
    --mdm-run-limit) MDM_RUN_LIMIT="${2:?}"; shift 2 ;;
    --graph-limit) GRAPH_LIMIT="${2:?}"; shift 2 ;;
    --status-only) RUN_E2E=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$ENVIRONMENT" == "dev" || "$ENVIRONMENT" == "prod" ]] || { usage >&2; exit 2; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPLICATION_FILE="${APPLICATION_FILE:-${REPO_ROOT}/infra/aws-${ENVIRONMENT}-application.json}"
[[ -f "$APPLICATION_FILE" ]] || fail "deployment summary not found: $APPLICATION_FILE"

aws_cli() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" "$@"
  else
    aws --region "$AWS_REGION_NAME" "$@"
  fi
}

state_machine_lines() {
  sed -n -E 's/^[[:space:]]*"([^"]+)": "(arn:aws:states:[^"]+)".*/\1 \2/p' "$APPLICATION_FILE"
}

state_machine_arn() {
  local key="$1"
  state_machine_lines | awk -v wanted="$key" '$1 == wanted { print $2; exit }'
}

print_state_machine_status() {
  echo "==> Step Functions in ${APPLICATION_FILE}"
  state_machine_lines | while read -r key arn; do
    if ! latest="$(aws_cli stepfunctions list-executions \
      --state-machine-arn "$arn" \
      --max-results 1 \
      --query 'executions[0].[name,status,startDate,stopDate]' \
      --output text 2>/dev/null)"; then
      latest=""
    fi
    if [[ -z "$latest" || "$latest" == "None" ]]; then
      printf "  %-34s %-10s %s\n" "$key" "NO_RUNS" "$arn"
    else
      printf "  %-34s %s\n" "$key" "$latest"
    fi
  done
}

warn_lingering_neo4j_references() {
  local warned=false

  if grep -Eiq 'NEO4J_|"neo4j"|--neo4j' "$APPLICATION_FILE"; then
    echo "WARNING: deployment summary still contains lingering NEO4J_* or Neo4j references." >&2
    warned=true
  fi

  if grep -Eiq 'NEO4J_|--neo4j|mdm_check_connectivity' "${REPO_ROOT}/infra/scripts/deploy-aws-application.sh"; then
    echo "WARNING: deploy script still contains legacy Neo4j task-definition/script references." >&2
    warned=true
  fi

  if [[ "$warned" == "true" ]]; then
    echo "WARNING: Snowflake-hosted graph validation treats those references as warning-only unless they block mdm_sync_graph or mdm_verify_graph." >&2
  fi
}

wait_for_execution() {
  local execution_arn="$1" label="$2" status
  while true; do
    status="$(aws_cli stepfunctions describe-execution \
      --execution-arn "$execution_arn" \
      --query status \
      --output text)"
    echo "  ${label}: ${status}"
    [[ "$status" == "RUNNING" ]] || break
    sleep 20
  done
  if [[ "$status" != "SUCCEEDED" ]]; then
    aws_cli stepfunctions describe-execution \
      --execution-arn "$execution_arn" \
      --query '{status:status,error:error,cause:cause}' \
      --output json || true
    return 1
  fi
}

start_and_wait() {
  local key="$1" input="$2" suffix="$3" arn execution_arn name
  arn="$(state_machine_arn "$key")"
  [[ -n "$arn" ]] || fail "state machine key not found in deployment summary: $key"
  name="${RUN_PREFIX}-${suffix}"
  execution_arn="$(aws_cli stepfunctions start-execution \
    --state-machine-arn "$arn" \
    --name "$name" \
    --input "$input" \
    --query executionArn \
    --output text)"
  echo "  started ${key}: ${execution_arn}"
  wait_for_execution "$execution_arn" "$key"
}

print_state_machine_status
warn_lingering_neo4j_references

if [[ "$RUN_E2E" != "true" ]]; then
  exit 0
fi

RUN_PREFIX="aws-mdm-e2e-$(date +%s)"

echo ""
echo "==> Running AWS-only MDM hosted graph e2e"
echo "  Snowflake-hosted graph validation uses mdm_sync_graph plus strict mdm_verify_graph."
start_and_wait "mdm_migrate" "{}" "migrate"
start_and_wait "mdm_run" "{\"limit\":${MDM_RUN_LIMIT}}" "run"
start_and_wait "mdm_backfill_relationships" "{\"limit\":${GRAPH_LIMIT}}" "backfill"
start_and_wait "mdm_sync_graph" "{\"limit\":${GRAPH_LIMIT}}" "sync"
start_and_wait "mdm_verify_graph" "{}" "verify"
start_and_wait "mdm_counts" "{}" "counts"

echo ""
echo "AWS MDM hosted graph e2e succeeded."
