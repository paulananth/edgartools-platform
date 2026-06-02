# AWS Authentication Findings

This note captures the local AWS authentication issue diagnosed on June 2, 2026.
It documents the observed state, local repair, and remaining infrastructure gap.

## Finding

The AWS CLI itself was installed and the default credentials were valid, but the
repo-expected named profiles were missing.

Initial state:

- `aws configure list-profiles` returned only `default`.
- `aws sts get-caller-identity` succeeded for account `077127448006`.
- The caller was `arn:aws:iam::077127448006:user/cli-access`.
- `cli-access` had `AdministratorAccess`.
- Commands using `--profile sec_platform_deployer` failed with:

```text
The config profile (sec_platform_deployer) could not be found
```

This repo's AWS path expects named profiles:

- `aws-admin-dev`
- `aws-admin-prod`
- `sec_platform_deployer`

## Local Repair

The named profiles were added to `~/.aws/config` as aliases backed by the valid
`default` credentials. Secret keys were not duplicated.

Profile shape:

```ini
[profile sec_platform_deployer]
region = us-east-1
output = json
credential_process = aws configure export-credentials --profile default --format process

[profile aws-admin-dev]
region = us-east-1
output = json
credential_process = aws configure export-credentials --profile default --format process

[profile aws-admin-prod]
region = us-east-1
output = json
credential_process = aws configure export-credentials --profile default --format process
```

A timestamped backup of the prior config was saved under `~/.aws/`.

## Validation

These forms now work:

```bash
aws --profile sec_platform_deployer --region us-east-1 sts get-caller-identity
AWS_PROFILE=sec_platform_deployer aws --region us-east-1 sts get-caller-identity
aws --profile aws-admin-dev --region us-east-1 sts get-caller-identity
aws --profile aws-admin-prod --region us-east-1 sts get-caller-identity
```

All resolved to AWS account `077127448006`.

ECR auth also worked:

```bash
aws --profile sec_platform_deployer --region us-east-1 ecr get-login-password
```

## Docker And ECR

`docker login` initially wrote an inline ECR auth token to
`~/.docker/config.json`. That was replaced with the AWS ECR Docker credential
helper.

Installed tool:

```bash
brew install docker-credential-helper-ecr
```

Docker config shape:

```json
{
  "currentContext": "colima",
  "credHelpers": {
    "077127448006.dkr.ecr.us-east-1.amazonaws.com": "ecr-login"
  }
}
```

The helper was validated with:

```bash
printf '%s' '077127448006.dkr.ecr.us-east-1.amazonaws.com' \
  | docker-credential-ecr-login get >/dev/null
```

## Remaining Gap

Authentication is fixed, but some expected active AWS resources were not present
at the time of diagnosis.

Observed:

- `edgartools-dev-*` S3 buckets existed.
- No ECR repositories were listed in `us-east-1` or `us-east-2`.
- No ECS clusters were listed in `us-east-1` or `us-east-2`.
- No Step Functions state machines were listed in `us-east-1` or `us-east-2`.

If image publish or deployment fails with `RepositoryNotFoundException`, that is
not an authentication issue. Apply or restore the passive AWS infrastructure and
access roots before running application rollout.

Relevant commands:

```bash
cd infra/terraform/accounts/dev
terraform init -backend-config=backend.hcl
terraform plan
terraform apply

cd ../../../access/aws/accounts/dev
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

Then deploy active application components with:

```bash
bash infra/scripts/deploy-aws-application.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --aws-region us-east-1 \
  --build-image \
  --publish-mode linux \
  --output-file infra/aws-dev-application.json
```

