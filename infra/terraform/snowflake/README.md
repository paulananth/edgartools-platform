# Snowflake Terraform Layout

This directory contains the Terraform-managed Snowflake deployment for the warehouse gold mirror.

Follow-on implementation assets live alongside it:

- Native-pull validation helper: `infra/snowflake/sql/`
- dbt gold project: `infra/snowflake/dbt/edgartools_gold/`

## Structure

```text
accounts/
  dev/
  prod/
modules/
  account_baseline/
```

## Scope

The Snowflake Terraform roots provision the Snowflake platform and native-pull runtime
objects that the AWS runtime expects to exist:

- account roles for deployer, refresher, and reader access
- the environment database
- the `EDGARTOOLS_SOURCE` and `EDGARTOOLS_GOLD` schemas
- the refresh and reader warehouses
- the storage integration, export stage, file formats, source mirror tables, manifest pipe, manifest stream, procedures, and task
- the Streamlit dashboard schema, source stage, and app object

They do not provision:

- dbt models
- users or workload identity federation bindings

Those remain separate on purpose:

- dbt owns the business-facing gold mirror
- AWS Terraform owns the export bucket, SNS topic, and IAM role that Snowflake assumes
- the deploy wrapper coordinates the AWS and Snowflake states without becoming a third source of truth

## Preferred Build Order

The preferred Snowflake E2E path is:

1. AWS Terraform bootstrap apply for the export bucket, SNS topic, and temporary trust
2. Snowflake Terraform apply for the native-pull objects
3. AWS Terraform reconcile apply to narrow trust to the exact Snowflake-managed principal
4. Snowflake Terraform re-apply and validation
5. dbt deployment of business-facing gold models and dynamic tables
6. Streamlit artifact upload

This keeps the canonical warehouse independent from Snowflake while still giving Snowflake a stable
gold-serving contract with a single automation entrypoint.

## Apply order

1. Copy `backend.hcl.example` to `backend.hcl` in the target account root.
2. Set the Snowflake provider connection inputs in `terraform.tfvars`.
3. Prefer the top-level deploy wrapper:

   ```bash
   bash infra/scripts/deploy-snowflake-stack.sh --env dev
   ```

4. If you need to operate the Snowflake root directly, pass the AWS outputs as Terraform variables instead of using the legacy manual bootstrap flow.

## Notes

- Terraform CLI is pinned to `1.14.8`.
- Snowflake provider is pinned to `2.14.1`.
- Snowflake state should use a key that is separate from the AWS account roots.
- The provider configuration uses `organization_name` and `account_name`, matching the current
  Snowflake provider requirements.
