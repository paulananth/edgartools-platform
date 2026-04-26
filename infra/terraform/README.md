# Terraform Layout

This directory contains the AWS/Snowflake reference deployment and the Azure/Databricks
parallel-run deployment for the SEC warehouse.

## Structure

```text
bootstrap-state/
azure/
  accounts/
    dev/
    prod/
  modules/
    container_apps_jobs/
    container_registry/
    databricks_workspace/
    key_vault/
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
modules/
  network_runtime/
  storage_buckets/
  storage_buckets_destroyable/
  warehouse_runtime/
```

## AWS/Snowflake Apply Order

1. Run `bootstrap-state` in the target account to create the Terraform state bucket.
2. Copy `backend.hcl.example` to `backend.hcl` in the target account root.
3. Run `terraform init -backend-config=backend.hcl`.
4. Set the runtime bootstrap inputs in `terraform.tfvars`:
   - `container_image`
   - `edgar_identity_value` or `edgar_identity_secret_arn`
5. Publish the warehouse image outside Terraform using the Linux-first repo policy:
   - preferred: `bash infra/scripts/publish-warehouse-image.sh --aws-region <region> --ecr-repository edgartools-<env>-warehouse --image-tag <git-sha> --mode linux`
   - CodeBuild reference buildspec: `infra/codebuild/buildspec.publish-warehouse-image.yml`
   - fallback only from this Windows workspace: `--mode crane`
6. Update `container_image` in `terraform.tfvars` to the verified digest emitted by the publish step.
7. Run `terraform plan` and `terraform apply`.
8. If Terraform created empty secret containers, populate:
   - `edgartools-<env>-edgar-identity`
   - `edgartools-<env>-runner-credentials` after `aws iam create-access-key --user-name edgartools-<env>-runner`
9. Capture the `snowflake_manifest_sns_topic_arn` output and use it when bootstrapping the Snowflake-native pull objects.

## Notes

- Terraform CLI is pinned to `1.14.7`.
- AWS provider is pinned to `6.39.0`.
- S3 backend state locking uses `use_lockfile = true`.
- Bronze and warehouse data use separate buckets.
- The repository includes a Linux-first image publish script at `infra/scripts/publish-warehouse-image.sh`.
- The repository includes a reference CodeBuild buildspec at `infra/codebuild/buildspec.publish-warehouse-image.yml`.
- Runner access keys are intentionally created outside Terraform and then stored in
  `edgartools-<env>-runner-credentials`.
- The AWS runtime no longer owns Snowflake runtime secrets or private keys.
- Snowflake import bootstrap now consumes the exported manifest SNS topic ARN rather than an AWS-held Snowflake credential.
- CI/CD automation remains outside Terraform, but release publishing should use a Linux runner and direct `buildx --push`.
- No DynamoDB, Glue, Athena, NAT gateways, or private subnets are provisioned in v1.
- `accounts/dev` is intentionally destroyable. It uses force-delete semantics for data buckets, the
  ECR repository, and the runner IAM user so `terraform destroy` can fully tear down the account root.
- `accounts/prod` is intentionally not destroyable from the account root. The protected storage
  module keeps the bronze bucket behind `prevent_destroy`.
- Snowflake baseline objects are provisioned from `infra/terraform/snowflake/` and use separate
  state keys from the AWS account roots.

## Azure/Databricks Apply Order

1. Create an Azure Storage backend for Terraform state, then copy
   `infra/terraform/azure/accounts/<env>/backend.hcl.example` to `backend.hcl`.
2. Publish the warehouse image to ACR:
   `bash infra/scripts/publish-warehouse-image-acr.sh --acr-name <acr> --image-tag <git-sha>`.
3. Set `container_image`, `storage_account_name`, `container_registry_name`, and
   `key_vault_name` in `terraform.tfvars`.
4. Apply only the resource group and Key Vault:
   `bash infra/scripts/deploy-azure-stack.sh --env dev --key-vault-only`.
5. Populate runtime secrets outside Terraform state:
   `bash infra/scripts/bootstrap-azure-secrets.sh --key-vault-name <kv> --edgar-identity "EdgarTools Platform data-ops@example.com"`.
6. Apply the full Azure root:
   `bash infra/scripts/deploy-azure-stack.sh --env dev --start-validation-job`.
7. Register Unity Catalog external tables over the serving export root using
   `infra/databricks/sql/register_external_tables.sql`.
8. Run dbt with the Databricks target:
   `bash infra/scripts/run-databricks-dbt.sh --target databricks_dev --key-vault-name <kv>`.

The Azure path writes the same serving Parquet contract used by the Snowflake export path,
but the preferred runtime variable is now `SERVING_EXPORT_ROOT`. `SNOWFLAKE_EXPORT_ROOT`
remains accepted as a temporary fallback for parallel runs.

Optional Azure MDM data plane:

- Set `enable_mdm = true` in `infra/terraform/azure/accounts/<env>/terraform.tfvars`.
- Set globally unique names for `mdm_sql_server_name` and
  `mdm_neo4j_storage_account_name`.
- Terraform provisions Azure SQL Server/Database for MDM relational state and a
  single-node Neo4j Container App backed by Azure Files.
- Terraform also creates an MDM FastAPI Container App plus manual Container Apps
  Jobs for `mdm migrate`, `mdm run`, and `mdm counts`.
- Runtime secrets are written to Key Vault:
  `mdm-database-url`, `mdm-sql-admin-username`, `mdm-sql-admin-password`,
  `mdm-neo4j`, split `mdm-neo4j-*` values, `mdm-api-keys`, and
  `mdm-api-keys-csv`.
- Validate MDM e2e with
  `EDGAR_WAREHOUSE_CMD="uv run --extra mdm edgar-warehouse" bash infra/scripts/test-mdm-e2e.sh --env dev`.
