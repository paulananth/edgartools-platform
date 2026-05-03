#!/usr/bin/env bash
set -euo pipefail

# Creates a fallback IAM user named sec_platform_deployer for application
# rollout. Prefer IAM Identity Center permission sets or CI OIDC roles with this
# name; use this script only when a long-lived IAM user is unavoidable.

detect_platform() {
  local uname_out
  uname_out="$(uname -s 2>/dev/null || echo unknown)"
  case "$uname_out" in
    Darwin*) PLATFORM="macos" ;;
    Linux*) PLATFORM="linux" ;;
    MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
    *) PLATFORM="unknown" ;;
  esac
  readonly PLATFORM
}

detect_platform

if [[ "$PLATFORM" == "windows" ]]; then
  export MSYS_NO_PATHCONV=1
fi

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME
readonly PROJECT="edgartools"
readonly IAM_PATH="/${PROJECT}/"
readonly DEFAULT_REGION="us-east-1"
readonly DEPLOYER_NAME="sec_platform_deployer"
readonly RUNNER_EXECUTION_ROLE_NAME="sec_platform_runner_execution"
readonly RUNNER_TASK_ROLE_NAME="sec_platform_runner_task"
readonly RUNNER_STEP_FUNCTIONS_ROLE_NAME="sec_platform_runner_step_functions"

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME <env> [region] [--no-key]

  env       : dev | prod
  region    : AWS region (default: $DEFAULT_REGION)
  --no-key  : Skip access key creation

Creates or updates the fallback IAM user $DEPLOYER_NAME with application rollout
permissions only. AWS infrastructure and access Terraform should be applied by
an admin profile, IAM Identity Center permission set, or CI OIDC admin role.

Examples:
  $SCRIPT_NAME dev --no-key
  $SCRIPT_NAME prod us-east-1

Platform: $PLATFORM
EOF
  exit "${1:-1}"
}

log() { echo "[INFO]  $(date -u +%H:%M:%S) $*"; }
warn() { echo "[WARN]  $(date -u +%H:%M:%S) $*" >&2; }
fail() { echo "[ERROR] $(date -u +%H:%M:%S) $*" >&2; exit 1; }

jq_install_hint() {
  case "$PLATFORM" in
    macos) echo "brew install jq" ;;
    linux) echo "sudo apt install jq OR sudo yum install jq" ;;
    windows) echo "winget install jqlang.jq" ;;
    *) echo "See https://stedolan.github.io/jq/download/" ;;
  esac
}

aws_install_hint() {
  case "$PLATFORM" in
    macos) echo "brew install awscli" ;;
    linux) echo "See https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2-linux.html" ;;
    windows) echo "winget install Amazon.AWSCLI" ;;
    *) echo "See https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html" ;;
  esac
}

if [[ $# -lt 1 ]]; then
  usage
fi
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage 0
fi

ENV="$1"
REGION="${2:-$DEFAULT_REGION}"
CREATE_KEY=true

for arg in "$@"; do
  [[ "$arg" == "--no-key" ]] && CREATE_KEY=false
done

if [[ $# -ge 2 && "$2" == --* ]]; then
  REGION="$DEFAULT_REGION"
fi

[[ "$ENV" == "dev" || "$ENV" == "prod" ]] || fail "env must be 'dev' or 'prod', got: $ENV"

readonly ENV
readonly REGION
readonly CREATE_KEY
readonly NAME_PREFIX="${PROJECT}-${ENV}"
readonly TFSTATE_BUCKET="${PROJECT}-${ENV}-tfstate"

check_prereqs() {
  log "Checking prerequisites (platform: $PLATFORM)"

  command -v aws >/dev/null 2>&1 || fail "aws CLI not found. Install: $(aws_install_hint)"
  command -v jq >/dev/null 2>&1 || fail "jq not found. Install: $(jq_install_hint)"

  local ver
  ver="$(aws --version 2>&1 | awk '{print $1}' | cut -d/ -f2)"
  log "AWS CLI version: $ver"
  [[ "${ver%%.*}" -ge 2 ]] || fail "AWS CLI v2 required. Found v${ver}. $(aws_install_hint)"

  aws sts get-caller-identity >/dev/null 2>&1 || fail "No active AWS credentials. Use an admin profile to run this fallback setup."

  ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
  readonly ACCOUNT_ID
  log "Account ID: $ACCOUNT_ID"
}

runner_role_arn() {
  printf 'arn:aws:iam::%s:role/%s\n' "$ACCOUNT_ID" "$1"
}

create_user() {
  if aws iam get-user --user-name "$DEPLOYER_NAME" >/dev/null 2>&1; then
    warn "User '$DEPLOYER_NAME' already exists. Reusing it."
  else
    log "Creating user: $DEPLOYER_NAME"
    aws iam create-user \
      --user-name "$DEPLOYER_NAME" \
      --path "$IAM_PATH" \
      --tags \
        "Key=Project,Value=${PROJECT}" \
        "Key=Environment,Value=${ENV}" \
        "Key=ManagedBy,Value=create-deployer-script" \
      >/dev/null
  fi
}

create_and_attach_policy() {
  local policy_name="$1" policy_doc="$2" policy_arn

  echo "$policy_doc" | jq . >/dev/null || fail "Invalid JSON in policy: $policy_name"
  policy_arn="arn:aws:iam::${ACCOUNT_ID}:policy${IAM_PATH}${policy_name}"

  if aws iam get-policy --policy-arn "$policy_arn" >/dev/null 2>&1; then
    warn "Policy '$policy_name' exists. Replacing it."
    aws iam detach-user-policy --user-name "$DEPLOYER_NAME" --policy-arn "$policy_arn" 2>/dev/null || true

    local versions
    # shellcheck disable=SC2016
    versions="$(aws iam list-policy-versions \
      --policy-arn "$policy_arn" \
      --query 'Versions[?IsDefaultVersion==`false`].VersionId' \
      --output text)"
    for version in $versions; do
      aws iam delete-policy-version --policy-arn "$policy_arn" --version-id "$version"
    done
    aws iam delete-policy --policy-arn "$policy_arn"
  fi

  log "Creating policy: $policy_name"
  aws iam create-policy \
    --policy-name "$policy_name" \
    --path "$IAM_PATH" \
    --policy-document "$policy_doc" \
    --tags "Key=Project,Value=${PROJECT}" "Key=Environment,Value=${ENV}" \
    >/dev/null

  log "Attaching $policy_name to $DEPLOYER_NAME"
  aws iam attach-user-policy --user-name "$DEPLOYER_NAME" --policy-arn "$policy_arn"
}

policy_rollout() {
  local repo_arn task_definition_arn state_machine_arn execution_arn ecs_log_group_arn ecs_log_group_wildcard_arn states_log_group_arn states_log_group_wildcard_arn

  repo_arn="arn:aws:ecr:${REGION}:${ACCOUNT_ID}:repository/${NAME_PREFIX}-warehouse"
  task_definition_arn="arn:aws:ecs:${REGION}:${ACCOUNT_ID}:task-definition/${NAME_PREFIX}-*:*"
  state_machine_arn="arn:aws:states:${REGION}:${ACCOUNT_ID}:stateMachine:${NAME_PREFIX}-*"
  execution_arn="arn:aws:states:${REGION}:${ACCOUNT_ID}:execution:${NAME_PREFIX}-*:*"
  ecs_log_group_arn="arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:/aws/ecs/${NAME_PREFIX}-warehouse"
  ecs_log_group_wildcard_arn="${ecs_log_group_arn}:*"
  states_log_group_arn="arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:/aws/states/${NAME_PREFIX}-warehouse"
  states_log_group_wildcard_arn="${states_log_group_arn}:*"

  jq -n \
    --arg repo_arn "$repo_arn" \
    --arg task_definition_arn "$task_definition_arn" \
    --arg state_machine_arn "$state_machine_arn" \
    --arg execution_arn "$execution_arn" \
    --arg ecs_log_group_arn "$ecs_log_group_arn" \
    --arg ecs_log_group_wildcard_arn "$ecs_log_group_wildcard_arn" \
    --arg states_log_group_arn "$states_log_group_arn" \
    --arg states_log_group_wildcard_arn "$states_log_group_wildcard_arn" \
    '{
      Version: "2012-10-17",
      Statement: [
        {
          Sid: "IdentityLookup",
          Effect: "Allow",
          Action: ["sts:GetCallerIdentity"],
          Resource: "*"
        },
        {
          Sid: "ECRAuth",
          Effect: "Allow",
          Action: ["ecr:GetAuthorizationToken"],
          Resource: "*"
        },
        {
          Sid: "ECRImagePublish",
          Effect: "Allow",
          Action: [
            "ecr:BatchCheckLayerAvailability",
            "ecr:CompleteLayerUpload",
            "ecr:DescribeImages",
            "ecr:DescribeRepositories",
            "ecr:GetDownloadUrlForLayer",
            "ecr:InitiateLayerUpload",
            "ecr:ListImages",
            "ecr:PutImage",
            "ecr:UploadLayerPart"
          ],
          Resource: $repo_arn
        },
        {
          Sid: "DiscoverNetworkAndCluster",
          Effect: "Allow",
          Action: [
            "ec2:DescribeSecurityGroups",
            "ec2:DescribeSubnets",
            "ecs:DescribeClusters"
          ],
          Resource: "*"
        },
        {
          Sid: "RegisterWarehouseTaskDefinitions",
          Effect: "Allow",
          Action: [
            "ecs:RegisterTaskDefinition",
            "ecs:DescribeTaskDefinition",
            "ecs:TagResource"
          ],
          Resource: "*"
        },
        {
          Sid: "ReadWarehouseTaskDefinitions",
          Effect: "Allow",
          Action: [
            "ecs:ListTaskDefinitions",
            "ecs:DescribeTaskDefinition"
          ],
          Resource: $task_definition_arn
        },
        {
          Sid: "DescribeApplicationLogGroups",
          Effect: "Allow",
          Action: ["logs:DescribeLogGroups"],
          Resource: "*"
        },
        {
          Sid: "ManageApplicationLogGroups",
          Effect: "Allow",
          Action: [
            "logs:CreateLogGroup",
            "logs:PutRetentionPolicy",
            "logs:TagLogGroup",
            "logs:TagResource",
            "logs:ListTagsForResource"
          ],
          Resource: [
            $ecs_log_group_arn,
            $ecs_log_group_wildcard_arn,
            $states_log_group_arn,
            $states_log_group_wildcard_arn
          ]
        },
        {
          Sid: "StepFunctionsRollout",
          Effect: "Allow",
          Action: [
            "states:CreateStateMachine",
            "states:DescribeStateMachine",
            "states:ListTagsForResource",
            "states:TagResource",
            "states:UpdateStateMachine"
          ],
          Resource: $state_machine_arn
        },
        {
          Sid: "StepFunctionsExecution",
          Effect: "Allow",
          Action: [
            "states:DescribeExecution",
            "states:StartExecution",
            "states:StopExecution"
          ],
          Resource: [$state_machine_arn, $execution_arn]
        }
      ]
    }'
}

policy_state_read() {
  jq -n \
    --arg bucket_arn "arn:aws:s3:::${TFSTATE_BUCKET}" \
    --arg provisioning_key "accounts/${ENV}/terraform.tfstate" \
    --arg access_key "access/aws/${ENV}/terraform.tfstate" \
    --arg provisioning_object "arn:aws:s3:::${TFSTATE_BUCKET}/accounts/${ENV}/terraform.tfstate" \
    --arg access_object "arn:aws:s3:::${TFSTATE_BUCKET}/access/aws/${ENV}/terraform.tfstate" \
    '{
      Version: "2012-10-17",
      Statement: [
        {
          Sid: "ListTerraformStateKeys",
          Effect: "Allow",
          Action: ["s3:ListBucket"],
          Resource: $bucket_arn,
          Condition: {
            StringLike: {
              "s3:prefix": [$provisioning_key, $access_key]
            }
          }
        },
        {
          Sid: "ReadTerraformStateOutputs",
          Effect: "Allow",
          Action: ["s3:GetObject"],
          Resource: [$provisioning_object, $access_object]
        }
      ]
    }'
}

policy_pass_runner_roles() {
  local execution_role_arn task_role_arn step_functions_role_arn

  execution_role_arn="$(runner_role_arn "$RUNNER_EXECUTION_ROLE_NAME")"
  task_role_arn="$(runner_role_arn "$RUNNER_TASK_ROLE_NAME")"
  step_functions_role_arn="$(runner_role_arn "$RUNNER_STEP_FUNCTIONS_ROLE_NAME")"

  jq -n \
    --arg execution_role_arn "$execution_role_arn" \
    --arg task_role_arn "$task_role_arn" \
    --arg step_functions_role_arn "$step_functions_role_arn" \
    '{
      Version: "2012-10-17",
      Statement: [
        {
          Sid: "ReadRunnerRoles",
          Effect: "Allow",
          Action: ["iam:GetRole"],
          Resource: [$execution_role_arn, $task_role_arn, $step_functions_role_arn]
        },
        {
          Sid: "PassRunnerRolesToEcsTasks",
          Effect: "Allow",
          Action: ["iam:PassRole"],
          Resource: [$execution_role_arn, $task_role_arn],
          Condition: {
            StringEquals: {
              "iam:PassedToService": "ecs-tasks.amazonaws.com"
            }
          }
        },
        {
          Sid: "PassRunnerRoleToStepFunctions",
          Effect: "Allow",
          Action: ["iam:PassRole"],
          Resource: $step_functions_role_arn,
          Condition: {
            StringEquals: {
              "iam:PassedToService": "states.amazonaws.com"
            }
          }
        }
      ]
    }'
}

attach_policies() {
  create_and_attach_policy "${DEPLOYER_NAME}-${ENV}-rollout" "$(policy_rollout)"
  create_and_attach_policy "${DEPLOYER_NAME}-${ENV}-state-read" "$(policy_state_read)"
  create_and_attach_policy "${DEPLOYER_NAME}-${ENV}-pass-runner-roles" "$(policy_pass_runner_roles)"
}

create_access_key() {
  if [[ "$CREATE_KEY" == false ]]; then
    log "Skipping access key creation (--no-key flag set)"
    return 0
  fi

  local key_count key_json key_id secret_key
  key_count="$(aws iam list-access-keys --user-name "$DEPLOYER_NAME" --query 'length(AccessKeyMetadata)' --output text)"
  if [[ "$key_count" -ge 2 ]]; then
    fail "User '$DEPLOYER_NAME' already has $key_count access key(s). Delete or rotate an existing key before creating another."
  fi

  warn "Creating a long-lived IAM user access key. Store it in a secret manager or CI secret store and rotate it regularly."
  key_json="$(aws iam create-access-key --user-name "$DEPLOYER_NAME")"
  key_id="$(echo "$key_json" | jq -r '.AccessKey.AccessKeyId')"
  secret_key="$(echo "$key_json" | jq -r '.AccessKey.SecretAccessKey')"

  cat <<EOF

=================================================================
CREDENTIALS FOR: $DEPLOYER_NAME
=================================================================
Named profile:

  [${DEPLOYER_NAME}]
  aws_access_key_id     = $key_id
  aws_secret_access_key = $secret_key
  region                = $REGION

Use for application rollout only:

  bash infra/scripts/deploy-aws-application.sh --env $ENV --aws-profile ${DEPLOYER_NAME}

Do not use this key for Terraform admin applies. Store it immediately and rotate
or delete it when you move to IAM Identity Center or CI OIDC.
=================================================================
EOF
}

print_summary() {
  log "Attached policies for $DEPLOYER_NAME:"
  aws iam list-attached-user-policies \
    --user-name "$DEPLOYER_NAME" \
    --query 'AttachedPolicies[].{Name: PolicyName, ARN: PolicyArn}' \
    --output table
}

main() {
  log "=== EdgarTools application deployer fallback setup ==="
  log "    env    : $ENV"
  log "    region : $REGION"
  log "    user   : $DEPLOYER_NAME"
  log "    key    : $CREATE_KEY"

  check_prereqs
  create_user
  attach_policies
  create_access_key
  print_summary

  log "=== Done ==="
}

main "$@"
