# Terraform Layout

This directory contains passive cloud-infrastructure Terraform roots for AWS.

AWS account roots are infra-only. They may create networks, storage,
registries, databases, logs, and empty secret containers. They
must not create runnable application jobs/services, schedules, workflow engines,
SQL procedures/tasks, access-control bindings, or runtime secret values.

## Structure

```text
bootstrap-state/
access/
  aws/accounts/{dev,prod}/        # IAM, SNS trust policies, ECS task roles
accounts/
  dev/
  prod/
modules/
  network_runtime/
  storage_buckets/
  storage_buckets_destroyable/
  warehouse_runtime/     # ECR, ECS cluster/logs, SNS topic, empty secrets only
```

## AWS Principal Model

- Apply `bootstrap-state`, `accounts/<env>`, and `access/aws/accounts/<env>`
  with an AWS admin profile in the target account.
- Deploy images, task definitions, state machines, and executions with
  `sec_platform_deployer`, preferably an IAM Identity Center permission set or
  CI OIDC role. The IAM user helper in `infra/scripts/create-deployer.sh` is a
  fallback for environments that cannot federate yet.
- Runtime does not use a runner IAM user. It uses service-assumed roles named
  `sec_platform_runner_execution`, `sec_platform_runner_task`, and
  `sec_platform_runner_step_functions`.

## AWS Infra Apply

1. Run `bootstrap-state` with an admin profile in the target account to create
   the Terraform state bucket.
2. Copy `backend.hcl.example` to `backend.hcl` in the target account root.
3. Run `terraform init -backend-config=backend.hcl`.
4. Run `terraform plan` and `terraform apply`.
5. Apply the AWS access root:
   `cd infra/terraform/access/aws/accounts/<env>`, copy `backend.hcl.example`
   and `terraform.tfvars.example`, then run `terraform init`, `terraform plan`,
   and `terraform apply` with the same admin profile.
6. Populate runtime secrets out-of-band if an operator workflow needs them:
   - `edgartools-<env>-edgar-identity`
   - `edgartools-<env>/mdm/postgres_dsn` for the operational store
7. Publish images with `infra/scripts/publish-warehouse-image.sh`.

AWS Terraform no longer accepts warehouse image, workflow schedule, app command,
Snowflake trust principal, IAM role, or EDGAR identity value inputs.
The former runner-credentials, MDM Neo4j, and MDM API-key empty containers are
removed from Terraform state without destroying them. Schedule their recoverable
deletion only with `scripts/ops/delete_unused_aws_secrets.py` after applying this
root and its matching access root.

## Post-Infra Operators

Run workload actions explicitly after infra has been applied:

- Publish AWS images with `infra/scripts/publish-warehouse-image.sh`.
- Run MDM migrations/pipelines only from operator-owned jobs or local operator
  commands, not from Terraform.

## Notes

- Terraform CLI `1.14.7` or newer is required for AWS roots.
- AWS provider is pinned to `6.39.0`.
- State bootstrap derives the bucket suffix from the authenticated AWS account and refuses retired accounts or stale account-ID overrides.
- S3 backend state locking uses `use_lockfile = true`.
- Bronze and warehouse data use separate buckets.
