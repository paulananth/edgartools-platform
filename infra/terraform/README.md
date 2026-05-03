# Terraform Layout

This directory contains passive cloud-infrastructure Terraform roots for AWS and
Azure, plus separate Snowflake Terraform trees for analytics/database-object
provisioning and access control.

AWS and Azure account roots are infra-only. They may create networks, storage,
registries, databases, logs, and empty secret containers. They
must not create runnable application jobs/services, schedules, workflow engines,
SQL procedures/tasks, dashboard apps, access-control bindings, or runtime secret
values.

## Structure

```text
bootstrap-state/
access/
  aws/accounts/{dev,prod}/        # IAM, SNS trust policies, ECS task roles
  azure/accounts/{dev,prod}/      # managed identities, RBAC, Key Vault policies
  snowflake/accounts/{dev,prod}/  # roles and grants
azure/
  accounts/
    dev/
    prod/
  modules/
    container_apps_jobs/  # legacy name; now Log Analytics only
    container_registry/
    databricks_workspace/
    key_vault/
    mdm_data_plane/      # Azure SQL + storage shell only
    resource_group/
    storage_account/
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
  mdm_database/          # RDS + empty secret containers only
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
   - `edgartools-<env>/mdm/*` when the AWS MDM database shell is enabled
7. Deploy active AWS application components from the operator script:
   `bash infra/scripts/deploy-aws-application.sh --env dev --aws-profile sec_platform_deployer --build-image`.

AWS Terraform no longer accepts warehouse image, workflow schedule, app command,
Snowflake trust principal, IAM role, or EDGAR identity value inputs.

## Azure Infra Apply

1. Create an Azure Storage backend for Terraform state, then copy
   `infra/terraform/azure/accounts/<env>/backend.hcl.example` to `backend.hcl`.
2. Set `storage_account_name`, `container_registry_name`, and `key_vault_name`
   in `terraform.tfvars`.
3. Apply the infra root:
   `bash infra/scripts/deploy-azure-stack.sh --env dev`.
4. Apply the Azure access root:
   `cd infra/terraform/access/azure/accounts/<env>`, copy `backend.hcl.example`
   and `terraform.tfvars.example`, then run `terraform init`, `terraform plan`,
   and `terraform apply`.
5. Populate runtime secrets outside Terraform state:
   `bash infra/scripts/bootstrap-azure-secrets.sh --key-vault-name <kv> --edgar-identity "EdgarTools Platform data-ops@example.com"`.
6. Build images, deploy runtime apps/jobs, and run MDM schema migrations from
   explicit operator scripts, for example:
   `bash infra/scripts/deploy-azure-runtime.sh --env dev --build-images --run-schema`.

Azure Terraform no longer accepts container image, schedule, app command, MDM API
key, Neo4j password, or DSN value inputs. It creates no Container Apps jobs,
Container Apps services, MDM API app, or Neo4j app container.

Optional Azure MDM provisions only Azure SQL and a Neo4j data storage share shell.
If enabled, Terraform emits versionless Key Vault URIs for expected runtime
secret names, but it does not create `azurerm_key_vault_secret` values.

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
- Move Azure managed identity, role assignments, and Key Vault access policies
  from `infra/terraform/azure/accounts/<env>` to
  `infra/terraform/access/azure/accounts/<env>`.
- Move Snowflake account role and grant resources from
  `infra/terraform/snowflake/accounts/<env>` to
  `infra/terraform/access/snowflake/accounts/<env>`.

Use `terraform state mv` when source and destination addresses are known, or
`terraform import` into the access root before removing the old state entry.
Do this first in `dev`; do not apply `prod` until plans show no replacement for
buckets, storage accounts, databases, Key Vaults, or Snowflake database objects.

## Post-Infra Operators

Run workload actions explicitly after infra has been applied:

- Publish Azure images with `infra/scripts/build-azure-images.sh`, or publish one
  image with `infra/scripts/publish-warehouse-image-acr.sh`.
- Populate Azure Key Vault values with `infra/scripts/bootstrap-azure-secrets.sh`.
  MDM runtime values use these secret names:
  `mdm-database-url`, `mdm-neo4j-uri`, `mdm-neo4j-user`,
  `mdm-neo4j-password`, `mdm-neo4j-auth`, `mdm-api-keys-csv`, and
  `mdm-api-keys`.
- Deploy Azure Container Apps runtime jobs/apps with
  `infra/scripts/deploy-azure-runtime.sh`. This script creates or updates
  Container Apps resources using Azure CLI/ARM REST, not Terraform. Pass
  `--daily-cron` or `--full-reconcile-cron` only when schedules should be active.
- Apply MDM SQL schema with `infra/scripts/run-azure-mdm-schema.sh`, or pass
  `--run-schema` to `deploy-azure-runtime.sh`.
- Run MDM ingestion with `infra/scripts/run-mdm-pipeline.sh`; it starts the
  operator-managed Container Apps Jobs.
- Deploy AWS application components with
  `infra/scripts/deploy-aws-application.sh --aws-profile sec_platform_deployer`.
  This script can build/push the
  warehouse image, registers ECS task definitions, and creates or updates Step
  Functions state machines using AWS CLI calls. When MDM secret ARNs are present
  in Terraform outputs, it also registers MDM task definitions and state
  machines for migrate, connectivity, run, graph sync/verify, and counts.
  Runner role ARNs are read from the AWS access root when available.
- Publish a standalone AWS image with `infra/scripts/publish-warehouse-image.sh`
  when you need to separate image build from application rollout.
- Run Databricks dbt with `infra/scripts/run-databricks-dbt.sh`.
- Run MDM migrations/pipelines only from operator-owned jobs or local operator
  commands, not from Terraform.
- Provision Snowflake database objects from `infra/terraform/snowflake/` and
  Snowflake access from `infra/terraform/access/snowflake/`.
- Upload Snowflake Streamlit dashboard artifacts with the Snowflake operator
  scripts, not as part of AWS or Azure infra apply.

## Notes

- Terraform CLI is pinned to `1.14.7` for AWS roots.
- AWS provider is pinned to `6.39.0`.
- Azure provider is pinned to `~> 3.110`.
- S3 backend state locking uses `use_lockfile = true`.
- Bronze and warehouse data use separate buckets.
- Snowflake Terraform uses separate state keys and is not part of the AWS/Azure
  infra-only guarantee.
