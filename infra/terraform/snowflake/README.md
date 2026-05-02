# Snowflake Terraform Layout

This directory contains the Terraform-managed Snowflake deployment for the
warehouse gold mirror. It is analytics/database-object provisioning, not part of
the AWS/Azure passive cloud-infrastructure roots. Snowflake roles and grants now
live in `infra/terraform/access/snowflake/`.

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
  dashboard/
  native_pull/
```

## Scope

The Snowflake Terraform roots provision the Snowflake platform and native-pull
runtime objects:

- the environment database
- the `EDGARTOOLS_SOURCE` and `EDGARTOOLS_GOLD` schemas
- the refresh and reader warehouses
- the storage integration, export stage, file formats, source mirror tables, manifest pipe, manifest stream, procedures, and task
- the Streamlit dashboard schema, source stage, and app object

They do not provision:

- account roles or grants
- dbt models
- users or workload identity federation bindings

Those remain separate on purpose:

- dbt owns the business-facing gold mirror
- AWS Terraform owns only the passive export bucket, SNS topic container, and
  AWS access owns the IAM role that Snowflake assumes
- Snowflake access Terraform owns deployer/refresher/reader roles and grants
- Snowflake applies are explicit post-infra analytics/database-object operations

## Preferred Build Order

The preferred Snowflake E2E path is an explicit post-infra operation:

1. AWS provisioning apply for the export bucket and SNS topic container
2. AWS access apply for temporary Snowflake trust
3. Snowflake provisioning apply for the native-pull objects
4. AWS access reconcile apply to narrow trust to the exact Snowflake-managed principal
5. Snowflake provisioning re-apply and Snowflake access apply
6. dbt deployment of business-facing gold models and dynamic tables
7. Streamlit artifact upload

This keeps AWS/Azure `terraform apply` limited to passive cloud infrastructure.

## Apply order

1. Copy `backend.hcl.example` to `backend.hcl` in the target account root.
2. Set the Snowflake provider connection inputs in `terraform.tfvars`.
3. Run the Snowflake deploy wrapper only when you intentionally want to manage
   Snowflake database objects:

   ```bash
   bash infra/scripts/deploy-snowflake-stack.sh --env dev
   ```

4. Prepare and apply `infra/terraform/access/snowflake/accounts/<env>` after
   provisioning when you need roles and grants outside the wrapper.

## Notes

- Terraform CLI is pinned to `1.14.8`.
- Snowflake provider is pinned to `2.14.1`.
- Snowflake state should use a key that is separate from the AWS account roots.
- The provider configuration uses `organization_name` and `account_name`, matching the current
  Snowflake provider requirements.
