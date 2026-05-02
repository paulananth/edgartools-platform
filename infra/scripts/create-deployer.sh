#!/usr/bin/env bash
# =============================================================================
# create-deployer.sh
# =============================================================================
#
# Creates an AWS IAM user with the permissions required to deploy the
# EdgarTools warehouse Terraform infrastructure.
#
# Supported platforms:
#   - macOS  (Intel and Apple Silicon)
#   - Linux  (Debian/Ubuntu, RHEL/Amazon Linux)
#   - Windows via Git Bash or WSL
#
# Two deployment tiers are supported:
#
#   dev   Attaches AWS-managed AdministratorAccess. Broad access is
#         acceptable for a non-production throwaway account. Do not
#         use in shared or production accounts.
#
#   prod  Creates and attaches five scoped customer-managed policies
#         (S3/KMS, Compute, IAM, Support, VPC/RDS). Each policy is
#         kept under the 6,144-character AWS limit. Together they
#         cover the passive AWS infrastructure surface area Terraform
#         needs and nothing more.
#
# Usage:
#   ./create-deployer.sh <env> [region] [--no-key]
#
#   env       : dev | prod
#   region    : AWS region (default: us-east-1)
#   --no-key  : Skip access key creation (useful in CI with OIDC)
#
# Examples:
#   ./create-deployer.sh dev
#   ./create-deployer.sh prod us-west-2
#   ./create-deployer.sh prod us-east-1 --no-key
#
# Prerequisites:
#   - AWS CLI v2 with admin-level credentials
#   - bash 3.2 or later
#   - jq (see install instructions printed by the script if missing)
#
# Linting:
#   Run: shellcheck create-deployer.sh
#   Install shellcheck:
#     brew install shellcheck    (macOS)
#     apt install shellcheck     (Debian/Ubuntu)
#     winget install shellcheck  (Windows)
#
# Notes:
#   - All IAM resources use path /edgartools/ for easy scoping.
#   - Re-running is safe: existing users and policies are detected
#     and reused. Existing policies are deleted and recreated on
#     re-run so that permission changes are applied cleanly.
#   - Access keys are printed once to stdout. Store them immediately
#     in a secrets manager or CI secret store.
#   - AWS IAM managed policy document size limit: 6,144 characters.
#     Each prod policy in this script is well under that limit.
#
# =============================================================================

set -euo pipefail

# =============================================================================
# Platform detection
#
# Sets PLATFORM to one of: macos | linux | windows | unknown
# Used throughout the script for OS-specific messages and behaviour.
# =============================================================================

detect_platform() {
    local uname_out
    uname_out="$(uname -s 2>/dev/null || echo "unknown")"

    case "$uname_out" in
        Darwin*)          PLATFORM="macos"   ;;
        Linux*)           PLATFORM="linux"   ;;
        MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
        *)                PLATFORM="unknown" ;;
    esac

    readonly PLATFORM
}

detect_platform

# On Windows (Git Bash / MSYS), bash rewrites any argument that looks like
# a Unix path (starts with /) into a Windows path before passing it to
# external programs. This converts IAM paths like /edgartools/ into
# C:/Program Files/Git/edgartools/ and AWS rejects them.
# Setting MSYS_NO_PATHCONV=1 disables that conversion for all commands
# in this script. This variable is ignored on macOS and Linux.
if [[ "$PLATFORM" == "windows" ]]; then
    export MSYS_NO_PATHCONV=1
fi

# =============================================================================
# Constants
# =============================================================================

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME
readonly PROJECT="edgartools"
readonly IAM_PATH="/${PROJECT}/"
readonly DEFAULT_REGION="us-east-1"
readonly ADMIN_POLICY_ARN="arn:aws:iam::aws:policy/AdministratorAccess"

# =============================================================================
# Usage
# =============================================================================

usage() {
    cat <<EOF
Usage: $SCRIPT_NAME <env> [region] [--no-key]

  env       : dev | prod
  region    : AWS region (default: $DEFAULT_REGION)
  --no-key  : Skip access key creation

Examples:
  $SCRIPT_NAME dev
  $SCRIPT_NAME prod us-west-2
  $SCRIPT_NAME prod us-east-1 --no-key

Platform: $PLATFORM
EOF
    exit 1
}

# =============================================================================
# Logging helpers
# =============================================================================

log()  { echo "[INFO]  $(date -u +%H:%M:%S) $*"; }
warn() { echo "[WARN]  $(date -u +%H:%M:%S) $*" >&2; }
fail() { echo "[ERROR] $(date -u +%H:%M:%S) $*" >&2; exit 1; }

# =============================================================================
# Argument parsing
# =============================================================================

[[ $# -lt 1 ]] && usage

ENV="$1"
REGION="${2:-$DEFAULT_REGION}"
CREATE_KEY=true

for arg in "$@"; do
    [[ "$arg" == "--no-key" ]] && CREATE_KEY=false
done

# Treat the second positional arg as region only if it does not start with --
if [[ $# -ge 2 && "$2" == --* ]]; then
    REGION="$DEFAULT_REGION"
fi

[[ "$ENV" == "dev" || "$ENV" == "prod" ]] \
    || fail "env must be 'dev' or 'prod', got: $ENV"

readonly USER_NAME="${PROJECT}-${ENV}-deployer"

# =============================================================================
# Install hint helpers
#
# Returns a platform-appropriate install command for a given tool.
# Used in prerequisite error messages so the user knows exactly
# what to run on their OS.
# =============================================================================

jq_install_hint() {
    case "$PLATFORM" in
        macos)
            echo "brew install jq"
            ;;
        linux)
            echo "sudo apt install jq   (Debian/Ubuntu)" \
                 " OR  sudo yum install jq  (RHEL/Amazon Linux)"
            ;;
        windows)
            # Drop the jq binary directly into Git Bash's usr/bin so
            # it is on PATH without any additional configuration.
            echo "In Git Bash run:" \
                 "curl -L -o /usr/bin/jq.exe" \
                 "https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-windows-amd64.exe"
            ;;
        *)
            echo "See https://stedolan.github.io/jq/download/"
            ;;
    esac
}

aws_install_hint() {
    case "$PLATFORM" in
        macos)
            echo "brew install awscli  OR download from" \
                 "https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2-mac.html"
            ;;
        linux)
            echo "See https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2-linux.html"
            ;;
        windows)
            echo "winget install Amazon.AWSCLI  OR download the MSI from" \
                 "https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2-windows.html"
            ;;
        *)
            echo "See https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
            ;;
    esac
}

# =============================================================================
# Prerequisite checks
# =============================================================================

check_prereqs() {
    log "Checking prerequisites (platform: $PLATFORM)"

    # AWS CLI
    if ! command -v aws >/dev/null 2>&1; then
        fail "aws CLI not found. Install: $(aws_install_hint)"
    fi

    # jq
    if ! command -v jq >/dev/null 2>&1; then
        fail "jq not found. Install: $(jq_install_hint)"
    fi

    # Require AWS CLI v2 (v1 lacks some flags used here)
    local ver
    ver=$(aws --version 2>&1 | awk '{print $1}' | cut -d/ -f2)
    log "AWS CLI version: $ver"
    [[ "${ver%%.*}" -ge 2 ]] \
        || fail "AWS CLI v2 required. Found v${ver}. $(aws_install_hint)"

    # Confirm credentials are active
    aws sts get-caller-identity >/dev/null 2>&1 \
        || fail "No active AWS credentials. Run: aws configure"

    local caller_arn
    caller_arn=$(aws sts get-caller-identity \
        --query 'Arn' --output text)
    log "Caller identity: $caller_arn"

    # Capture account ID for constructing policy ARNs later
    ACCOUNT_ID=$(aws sts get-caller-identity \
        --query 'Account' --output text)
    readonly ACCOUNT_ID
    log "Account ID: $ACCOUNT_ID"
}

# =============================================================================
# IAM user creation
# =============================================================================

create_user() {
    log "Checking for existing user: $USER_NAME"

    if aws iam get-user \
            --user-name "$USER_NAME" \
            >/dev/null 2>&1; then
        warn "User '$USER_NAME' already exists. Skipping creation."
        return 0
    fi

    log "Creating user: $USER_NAME"
    aws iam create-user \
        --user-name "$USER_NAME" \
        --path "$IAM_PATH" \
        --tags \
            "Key=Project,Value=${PROJECT}" \
            "Key=Environment,Value=${ENV}" \
            "Key=ManagedBy,Value=create-deployer-script" \
        >/dev/null

    log "User created: $USER_NAME"
}

# =============================================================================
# Policy helper: create-or-replace and attach
#
# Constructs the policy ARN from the account ID and IAM path rather than
# calling list-policies (which is slow on accounts with many policies).
# Deletes and recreates if the policy already exists so that changes
# to this script are applied cleanly on re-run.
#
# Args:
#   $1  policy_name   -- short name, e.g. edgartools-prod-tf-s3
#   $2  policy_doc    -- JSON string (must be valid IAM policy JSON)
# =============================================================================

create_and_attach_policy() {
    local policy_name="$1"
    local policy_doc="$2"

    # Validate JSON before sending to AWS
    echo "$policy_doc" | jq . >/dev/null \
        || fail "Invalid JSON in policy: $policy_name"

    local policy_arn
    policy_arn="arn:aws:iam::${ACCOUNT_ID}:policy${IAM_PATH}${policy_name}"

    # Detach and delete the existing version so permission changes take effect
    if aws iam get-policy \
            --policy-arn "$policy_arn" \
            >/dev/null 2>&1; then
        warn "Policy '$policy_name' exists. Replacing."

        aws iam detach-user-policy \
            --user-name "$USER_NAME" \
            --policy-arn "$policy_arn" \
            2>/dev/null || true

        # Non-default versions must be deleted before the policy itself
        local versions
        # SC2016: backticks here are JMESPath literals inside single quotes,
        # not shell command substitution. Single quotes are intentional.
        # shellcheck disable=SC2016
        versions=$(aws iam list-policy-versions \
            --policy-arn "$policy_arn" \
            --query \
                'Versions[?IsDefaultVersion==`false`].VersionId' \
            --output text)

        for ver in $versions; do
            aws iam delete-policy-version \
                --policy-arn "$policy_arn" \
                --version-id "$ver"
        done

        aws iam delete-policy --policy-arn "$policy_arn"
    fi

    log "Creating policy: $policy_name"
    aws iam create-policy \
        --policy-name "$policy_name" \
        --path "$IAM_PATH" \
        --policy-document "$policy_doc" \
        --tags \
            "Key=Project,Value=${PROJECT}" \
            "Key=Environment,Value=${ENV}" \
        --query 'Policy.Arn' \
        --output text \
        >/dev/null

    log "Attaching $policy_name to $USER_NAME"
    aws iam attach-user-policy \
        --user-name "$USER_NAME" \
        --policy-arn "$policy_arn"
}

# =============================================================================
# Dev setup: attach AWS-managed AdministratorAccess
# =============================================================================

setup_dev() {
    log "Attaching AdministratorAccess (dev only)"

    aws iam attach-user-policy \
        --user-name "$USER_NAME" \
        --policy-arn "$ADMIN_POLICY_ARN"

    log "AdministratorAccess attached"
    warn "Dev user has full admin access. Do not use in shared accounts."
}

# =============================================================================
# Prod setup: five scoped customer-managed policies
#
# Policy split:
#   tf-s3           : S3 bucket lifecycle plus Snowflake export KMS keys
#   tf-compute      : ECR repository and ECS cluster shell management
#   tf-iam          : IAM role and policy management for Terraform-created
#                     passive identities
#   tf-support      : SNS, Secrets Manager, CloudWatch Logs, and STS
#   tf-vpc          : VPC, subnets, IGW, route tables, security groups,
#                     VPC endpoints, and optional RDS shell
#
# All policies use "Resource": "*" because Terraform generates resource
# names at plan time. Scope down Resource to ARN patterns after the
# first apply if your security posture requires it.
# =============================================================================

# -----------------------------------------------------------------------------
# Policy 1 of 5: S3 + KMS
# Covers Terraform state, warehouse buckets, Snowflake export bucket, and export KMS key.
# -----------------------------------------------------------------------------

policy_s3() {
    cat <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3BucketManagement",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:DeleteBucket",
        "s3:ListBucket",
        "s3:ListAllMyBuckets",
        "s3:GetBucketVersioning",
        "s3:PutBucketVersioning",
        "s3:GetBucketPublicAccessBlock",
        "s3:PutBucketPublicAccessBlock",
        "s3:GetEncryptionConfiguration",
        "s3:PutEncryptionConfiguration",
        "s3:GetBucketOwnershipControls",
        "s3:PutBucketOwnershipControls",
        "s3:GetBucketTagging",
        "s3:PutBucketTagging",
        "s3:DeleteBucketTagging",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:GetBucketPolicy",
        "s3:PutBucketPolicy",
        "s3:GetLifecycleConfiguration",
        "s3:PutLifecycleConfiguration",
        "s3:DeleteLifecycleConfiguration",
        "s3:DeleteBucketPolicy"
      ],
      "Resource": "*"
    },
    {
      "Sid": "KMSManagement",
      "Effect": "Allow",
      "Action": [
        "kms:CreateKey",
        "kms:ScheduleKeyDeletion",
        "kms:DescribeKey",
        "kms:EnableKeyRotation",
        "kms:GetKeyRotationStatus",
        "kms:ListAliases",
        "kms:CreateAlias",
        "kms:UpdateAlias",
        "kms:DeleteAlias",
        "kms:TagResource",
        "kms:UntagResource",
        "kms:ListResourceTags",
        "kms:GetKeyPolicy",
        "kms:PutKeyPolicy"
      ],
      "Resource": "*"
    }
  ]
}
JSON
}

# -----------------------------------------------------------------------------
# Policy 2 of 5: Compute (ECR + ECS cluster shell)
# ECR remains passive repository infrastructure. ECS is limited to cluster shell
# management; Terraform does not create task definitions or run tasks.
# -----------------------------------------------------------------------------

policy_compute() {
    cat <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRManagement",
      "Effect": "Allow",
      "Action": [
        "ecr:CreateRepository",
        "ecr:DeleteRepository",
        "ecr:DescribeRepositories",
        "ecr:PutImageTagMutability",
        "ecr:PutImageScanningConfiguration",
        "ecr:GetRepositoryPolicy",
        "ecr:GetAuthorizationToken",
        "ecr:DescribeImages",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage",
        "ecr:BatchCheckLayerAvailability",
        "ecr:ListTagsForResource",
        "ecr:TagResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECSManagement",
      "Effect": "Allow",
      "Action": [
        "ecs:CreateCluster",
        "ecs:DeleteCluster",
        "ecs:DescribeClusters",
        "ecs:UpdateClusterSettings",
        "ecs:TagResource",
        "ecs:ListTagsForResource"
      ],
      "Resource": "*"
    }
  ]
}
JSON
}

# -----------------------------------------------------------------------------
# Policy 3 of 5: IAM
# Terraform creates passive roles, policies, and the optional runner IAM user.
# -----------------------------------------------------------------------------

policy_iam() {
    cat <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "IAMRoleManagement",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:GetRole",
        "iam:UpdateAssumeRolePolicy",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:ListAttachedRolePolicies",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:GetRolePolicy",
        "iam:ListRolePolicies",
        "iam:TagRole",
        "iam:ListRoleTags",
        "iam:CreatePolicy",
        "iam:DeletePolicy",
        "iam:GetPolicy",
        "iam:GetPolicyVersion",
        "iam:ListPolicies",
        "iam:ListPolicyVersions",
        "iam:DeletePolicyVersion",
        "iam:CreatePolicyVersion",
        "iam:CreateUser",
        "iam:DeleteUser",
        "iam:GetUser",
        "iam:TagUser",
        "iam:ListUserTags"
      ],
      "Resource": "*"
    }
  ]
}
JSON
}

# -----------------------------------------------------------------------------
# Policy 4 of 5: Passive support resources
# Covers SNS, Secrets Manager, CloudWatch Logs, and STS identity lookup.
# -----------------------------------------------------------------------------

policy_support() {
    cat <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SNSManagement",
      "Effect": "Allow",
      "Action": [
        "sns:CreateTopic",
        "sns:DeleteTopic",
        "sns:GetTopicAttributes",
        "sns:SetTopicAttributes",
        "sns:ListTagsForResource",
        "sns:TagResource",
        "sns:UntagResource",
        "sns:Subscribe",
        "sns:Unsubscribe"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SecretsManager",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:CreateSecret",
        "secretsmanager:DeleteSecret",
        "secretsmanager:DescribeSecret",
        "secretsmanager:GetSecretValue",
        "secretsmanager:PutSecretValue",
        "secretsmanager:TagResource",
        "secretsmanager:UntagResource",
        "secretsmanager:ListSecrets"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:DeleteLogGroup",
        "logs:DescribeLogGroups",
        "logs:PutRetentionPolicy",
        "logs:ListTagsLogGroup",
        "logs:ListTagsForResource",
        "logs:TagResource",
        "logs:UntagResource",
        "logs:FilterLogEvents",
        "logs:GetLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": "*"
    },
    {
      "Sid": "STSIdentity",
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
JSON
}

# -----------------------------------------------------------------------------
# Policy 5 of 5: VPC, Networking, and optional RDS shell
# Covers the network_runtime module and optional passive MDM RDS data-plane shell.
# -----------------------------------------------------------------------------

policy_vpc() {
    cat <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "VPCManagement",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateVpc",
        "ec2:DeleteVpc",
        "ec2:DescribeVpcs",
        "ec2:ModifyVpcAttribute",
        "ec2:DescribeVpcAttribute",
        "ec2:CreateSubnet",
        "ec2:DeleteSubnet",
        "ec2:DescribeSubnets",
        "ec2:ModifySubnetAttribute",
        "ec2:CreateInternetGateway",
        "ec2:DeleteInternetGateway",
        "ec2:AttachInternetGateway",
        "ec2:DetachInternetGateway",
        "ec2:DescribeInternetGateways",
        "ec2:CreateRouteTable",
        "ec2:DeleteRouteTable",
        "ec2:DescribeRouteTables",
        "ec2:CreateRoute",
        "ec2:DeleteRoute",
        "ec2:AssociateRouteTable",
        "ec2:DisassociateRouteTable",
        "ec2:CreateVpcEndpoint",
        "ec2:DeleteVpcEndpoints",
        "ec2:DescribeVpcEndpoints",
        "ec2:ModifyVpcEndpoint",
        "ec2:CreateSecurityGroup",
        "ec2:DeleteSecurityGroup",
        "ec2:DescribeSecurityGroups",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:RevokeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:RevokeSecurityGroupEgress",
        "ec2:DescribeSecurityGroupRules",
        "ec2:DescribePrefixLists",
        "ec2:CreateTags",
        "ec2:DeleteTags",
        "ec2:DescribeTags",
        "ec2:DescribeAvailabilityZones",
        "ec2:DescribeAccountAttributes"
      ],
      "Resource": "*"
    },
    {
      "Sid": "RDSManagement",
      "Effect": "Allow",
      "Action": [
        "rds:AddTagsToResource",
        "rds:CreateDBInstance",
        "rds:CreateDBSnapshot",
        "rds:CreateDBSubnetGroup",
        "rds:DeleteDBInstance",
        "rds:DeleteDBSnapshot",
        "rds:DeleteDBSubnetGroup",
        "rds:DescribeDBInstances",
        "rds:DescribeDBSnapshots",
        "rds:DescribeDBSubnetGroups",
        "rds:ListTagsForResource",
        "rds:ModifyDBInstance",
        "rds:ModifyDBSubnetGroup",
        "rds:RemoveTagsFromResource"
      ],
      "Resource": "*"
    }
  ]
}
JSON
}

setup_prod() {
    log "Creating five scoped policies for prod environment"

    create_and_attach_policy \
        "${PROJECT}-${ENV}-tf-s3" \
        "$(policy_s3)"

    create_and_attach_policy \
        "${PROJECT}-${ENV}-tf-compute" \
        "$(policy_compute)"

    create_and_attach_policy \
        "${PROJECT}-${ENV}-tf-iam" \
        "$(policy_iam)"

    create_and_attach_policy \
        "${PROJECT}-${ENV}-tf-support" \
        "$(policy_support)"

    create_and_attach_policy \
        "${PROJECT}-${ENV}-tf-vpc" \
        "$(policy_vpc)"

    log "All prod policies created and attached"
}

# =============================================================================
# Access key creation
#
# AWS allows a maximum of two active access keys per IAM user.
# The script checks the current count and refuses to create a third.
# =============================================================================

create_access_key() {
    if [[ "$CREATE_KEY" == false ]]; then
        log "Skipping access key creation (--no-key flag set)"
        return 0
    fi

    log "Checking existing access keys for: $USER_NAME"

    local key_count
    key_count=$(aws iam list-access-keys \
        --user-name "$USER_NAME" \
        --query 'length(AccessKeyMetadata)' \
        --output text)

    if [[ "$key_count" -ge 2 ]]; then
        fail "User '$USER_NAME' already has $key_count access key(s)." \
             "AWS limit is 2. Delete an existing key first:" \
             "aws iam delete-access-key" \
             "--user-name $USER_NAME --access-key-id <KEY_ID>"
    fi

    log "Creating access key"
    local key_json
    key_json=$(aws iam create-access-key --user-name "$USER_NAME")

    local key_id secret_key
    key_id=$(echo "$key_json"     | jq -r '.AccessKey.AccessKeyId')
    secret_key=$(echo "$key_json" | jq -r '.AccessKey.SecretAccessKey')

    # Credentials are printed to stdout only. Do not log to stderr.
    cat <<EOF

=================================================================
CREDENTIALS FOR: $USER_NAME
=================================================================
Export as environment variables (all platforms):

  export AWS_ACCESS_KEY_ID=$key_id
  export AWS_SECRET_ACCESS_KEY=$secret_key
  export AWS_DEFAULT_REGION=$REGION

Or add as a named profile to ~/.aws/credentials:

  [${PROJECT}-${ENV}]
  aws_access_key_id     = $key_id
  aws_secret_access_key = $secret_key
  region                = $REGION

Then use the profile with:
  export AWS_PROFILE=${PROJECT}-${ENV}

=================================================================
IMPORTANT: Store these credentials securely. They are shown once.
=================================================================
EOF
}

# =============================================================================
# Summary: list attached policies
# =============================================================================

print_summary() {
    log "Attached policies for $USER_NAME:"
    aws iam list-attached-user-policies \
        --user-name "$USER_NAME" \
        --query 'AttachedPolicies[].{Name: PolicyName, ARN: PolicyArn}' \
        --output table
    log "Console: https://console.aws.amazon.com/iam/home#/users/$USER_NAME"
}

# =============================================================================
# Main
# =============================================================================

main() {
    log "=== EdgarTools deployer setup ==="
    log "    platform : $PLATFORM"
    log "    env      : $ENV"
    log "    region   : $REGION"
    log "    user     : $USER_NAME"
    log "    key      : $CREATE_KEY"

    check_prereqs
    create_user

    case "$ENV" in
        dev)  setup_dev  ;;
        prod) setup_prod ;;
        *)    fail "Unexpected env: $ENV" ;;
    esac

    create_access_key
    print_summary

    log "=== Done ==="
}

main "$@"
