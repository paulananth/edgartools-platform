# Terraform Layout

This directory contains passive cloud-infrastructure Terraform roots for AWS,
plus separate Snowflake Terraform trees for analytics/database-object
provisioning and access control.

AWS account roots are infra-only. They may create networks, storage,
registries, databases, logs, and empty secret containers. They
must not create runnable application jobs/services, schedules, workflow engines,
SQL procedures/tasks, dashboard apps, access-control bindings, or runtime secret
values.

## Structure

```text
bootstrap-state/
access/
  aws/accounts/{dev,prod}/        # IAM, SNS trust policies, ECS task roles
  snowflake/accounts/{dev,prod}/  # roles and grants
accounts/
  dev/
  prod/
snowflake/
  accounts/
    dev/
    prod/
  modules/
    account_baseline/
    dashboard/
    native_pull/
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
   - `edgartools-<env>-runner-credentials` only as a legacy compatibility
     container for non-runtime operator credentials
   - `edgartools-<env>/mdm/*` for MDM runtime DSNs and graph/export settings
7. Deploy active AWS application components from the operator script:
   `bash infra/scripts/deploy-aws-application.sh --env dev --aws-profile sec_platform_deployer --aws-account-id 690839588395 --build-image`.

AWS Terraform no longer accepts warehouse image, workflow schedule, app command,
Snowflake trust principal, IAM role, or EDGAR identity value inputs.

## Snowflake Apply

1. Apply Snowflake provisioning from `infra/terraform/snowflake/accounts/<env>`
   to create database objects, schemas, warehouses, native-pull objects, and the
   dashboard shell.
2. Apply Snowflake access from `infra/terraform/access/snowflake/accounts/<env>`
   to create roles and grants.
3. For native-pull AWS trust, use `infra/scripts/deploy-snowflake-stack.sh`; it
   bootstraps AWS access trust, applies Snowflake provisioning, narrows AWS trust
   to the emitted Snowflake principal, and then applies Snowflake access grants.

## State Migration

For environments where IAM/RBAC/Snowflake grant resources already exist in the
old provisioning states, migrate state before applying the new access roots:

- Move AWS IAM role and SNS topic policy resources from
  `infra/terraform/accounts/<env>` to `infra/terraform/access/aws/accounts/<env>`.
  Retire any old `edgartools-<env>-runner` IAM user after its access keys have
  been deleted; the new runner model is service-role based.
- Move Snowflake account role and grant resources from
  `infra/terraform/snowflake/accounts/<env>` to
  `infra/terraform/access/snowflake/accounts/<env>`.

Use `terraform state mv` when source and destination addresses are known, or
`terraform import` into the access root before removing the old state entry.
Do this first in `dev`; do not apply `prod` until plans show no replacement for
buckets, databases, or Snowflake database objects.

## Post-Infra Operators

Run workload actions explicitly after infra has been applied:

- Deploy AWS application components with
  `infra/scripts/deploy-aws-application.sh --aws-profile sec_platform_deployer --aws-account-id 690839588395`.
  This script can build/push the
  warehouse image, registers ECS task definitions, and creates or updates Step
  Functions state machines using AWS CLI calls. When MDM secret ARNs are present
  in Terraform outputs, it also registers MDM task definitions and state
  machines for migrate, connectivity, run, graph sync/verify, and counts.
  Runner role ARNs are read from the AWS access root when available.
- Publish a standalone AWS image with `infra/scripts/publish-warehouse-image.sh`
  when you need to separate image build from application rollout.
- Run MDM migrations/pipelines only from operator-owned jobs or local operator
  commands, not from Terraform.
- Provision Snowflake database objects from `infra/terraform/snowflake/` and
  Snowflake access from `infra/terraform/access/snowflake/`.
- Upload Snowflake Streamlit dashboard artifacts with the Snowflake operator
  scripts, not as part of AWS infra apply.

## Notes

- Terraform CLI `1.14.7` or newer is required for AWS roots.
- AWS provider is pinned to `6.39.0`.
- State bootstrap derives the bucket suffix from the authenticated AWS account and refuses retired accounts or stale account-ID overrides.
- S3 backend state locking uses `use_lockfile = true`.
- Bronze and warehouse data use separate buckets.
- Snowflake Terraform uses separate state keys and is not part of the AWS
  infra-only guarantee.
