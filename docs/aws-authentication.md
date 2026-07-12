# AWS account and profile selection

This repository uses named AWS CLI profiles so operators must deliberately select both an environment and an AWS principal. Never infer the target account from a profile name alone: verify the caller identity before every Terraform apply or application deployment.

## Current account map

| Environment | Admin profile | Application profile | Expected AWS account | Resource boundary |
| --- | --- | --- | --- | --- |
| dev | `aws-admin-dev` | `sec_platform_deployer` | `690839588395` | `edgartools-dev-*` resources and dev Terraform state keys |
| prod | `aws-admin-prod` | `sec_platform_deployer` | `690839588395` | `edgartools-prod-*` resources and prod Terraform state keys |

Dev and prod currently share the canonical AWS account. They are separated by resource names, Terraform state keys, secrets, and deployment inputs—not by AWS account. Account `077127448006` is retired and must never be used for bootstrap, Terraform, image publishing, or deployment.

## Configure the profiles

Prefer AWS IAM Identity Center or an organization-managed credential process. The exact SSO start URL and admin role name are operator-specific; obtain them from the AWS administrator. A typical `~/.aws/config` shape is:

```ini
[sso-session edgartools]
sso_start_url = https://<organization>.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access

[profile aws-admin-dev]
sso_session = edgartools
sso_account_id = 690839588395
sso_role_name = <admin-role-name>
region = us-east-1
output = json

[profile aws-admin-prod]
sso_session = edgartools
sso_account_id = 690839588395
sso_role_name = <admin-role-name>
region = us-east-1
output = json

[profile sec_platform_deployer]
sso_session = edgartools
sso_account_id = 690839588395
sso_role_name = sec_platform_deployer
region = us-east-1
output = json
```

Do not alias these profiles to `default` unless `default` is independently verified to resolve to the canonical account and the alias is an intentional local credential design. Never copy access keys into this repository.

For SSO-backed profiles, authenticate before use:

```bash
aws sso login --profile aws-admin-dev
aws sso login --profile aws-admin-prod
aws sso login --profile sec_platform_deployer
```

## Mandatory identity gate

Select exactly one admin profile and verify its account before running Terraform.

For dev:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export AWS_PROFILE=aws-admin-dev
export AWS_DEFAULT_REGION=us-east-1

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
test "$ACCOUNT_ID" = "690839588395" || {
  echo "Refusing dev operation: aws-admin-dev resolved to $ACCOUNT_ID" >&2
  exit 1
}
aws sts get-caller-identity
```

For prod:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export AWS_PROFILE=aws-admin-prod
export AWS_DEFAULT_REGION=us-east-1

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
test "$ACCOUNT_ID" = "690839588395" || {
  echo "Refusing prod operation: aws-admin-prod resolved to $ACCOUNT_ID" >&2
  exit 1
}
aws sts get-caller-identity
```

If either check reports `077127448006`, stop. Fix `~/.aws/config`, the selected SSO account/role, credential-process configuration, or exported credential variables. Do not run Terraform with an override that points back to the retired account.

Useful diagnostics:

```bash
aws configure list-profiles
aws configure list --profile aws-admin-dev
aws configure list --profile aws-admin-prod
aws sts get-caller-identity --profile aws-admin-dev
aws sts get-caller-identity --profile aws-admin-prod
```

## Which profile to use

- Use `aws-admin-dev` for dev state bootstrap, `infra/terraform/accounts/dev`, and `infra/terraform/access/aws/accounts/dev`.
- Use `aws-admin-prod` for prod state bootstrap, `infra/terraform/accounts/prod`, and `infra/terraform/access/aws/accounts/prod`.
- Use `sec_platform_deployer` only after passive infrastructure and access exist. It publishes images, registers ECS task definitions, updates Step Functions, and starts executions.
- Runtime uses service-assumed runner roles. Do not create runner access keys.

Always keep the same verified admin profile selected through bootstrap, passive-infrastructure apply, and access apply for one environment. Do not switch from dev to prod merely by changing the Terraform directory while leaving an unverified profile active.

For application rollout, pass the expected account to the deployment script as a second, executable identity gate:

```bash
bash infra/scripts/deploy-aws-application.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --aws-account-id 690839588395 \
  --aws-region us-east-1 \
  --build-image \
  --also-tag dev \
  --output-file infra/aws-dev-application.json
```

Use the same `--aws-account-id 690839588395` argument for prod, changing `--env` and the output filename to `prod`. The script compares the argument with `aws sts get-caller-identity` before ECR cleanup, image building, task registration, or state-machine updates.

## Bootstrap and backend configuration

The bootstrap root derives the state bucket from the selected environment and authenticated account:

```text
edgartools-<environment>-tfstate-<authenticated-account-id>
```

For the current account, the expected buckets are:

- Dev: `edgartools-dev-tfstate-690839588395`
- Prod: `edgartools-prod-tfstate-690839588395`

Bootstrap dev:

```bash
export AWS_PROFILE=aws-admin-dev
cd infra/terraform/bootstrap-state
cp terraform.tfvars.example terraform.tfvars
# Set environment = "dev". Normally omit terraform_state_bucket_name.
terraform init
terraform apply
```

Bootstrap prod:

```bash
export AWS_PROFILE=aws-admin-prod
cd infra/terraform/bootstrap-state
cp terraform.tfvars.example terraform.tfvars
# Set environment = "prod". Normally omit terraform_state_bucket_name.
terraform init
terraform apply
```

Copy the reported bucket name into the matching environment's `backend.hcl`. Never reuse the dev state key for prod or the prod state key for dev.

## Failure behavior

The bootstrap Terraform root rejects retired account `077127448006`. The deployment script contains no account IDs; it requires `--aws-account-id` and rejects any mismatch between that operator-supplied value and STS. Never pass a retired account as the expected deployment account. A mismatch is a credential-selection failure, not a reason to weaken the guard or edit an account ID into Terraform variables.

If application deployment reports missing subnets, buckets, ECR repositories, or roles after the identity gate passes, apply the passive infrastructure and access roots first. See [AWS deployment runbook](runbook.md).
