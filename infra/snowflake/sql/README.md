# Snowflake Native-Pull Validation Assets

This directory contains the validation helper for the Terraform-managed Snowflake native-pull path,
plus the legacy bootstrap SQL retained as implementation reference.

These files sit between:

- Terraform-managed Snowflake platform and native-pull objects in `infra/terraform/snowflake/`
- dbt-managed gold models in `infra/snowflake/dbt/edgartools_gold/`

## Scope

Terraform now owns:

- the storage integration, S3 import path, and run-manifest auto-ingest objects
- the technical per-run refresh-status table and manifest stream
- the source-side load wrapper
- the public gold refresh wrapper and triggered manifest-processing task that waits for dbt-owned dynamic tables

The dbt project is responsible for:

- curated gold models
- dynamic tables
- the business-facing `EDGARTOOLS_GOLD_STATUS` view

## Execution order

Use the deploy wrapper to coordinate AWS Terraform, Snowflake Terraform, dbt, and dashboard upload:

```bash
bash infra/scripts/deploy-snowflake-stack.sh --env dev
```

The validation helper can still be run directly after deployment to emit a structured artifact and
optionally validate stage access and manifest copy history:

```bash
python3 infra/snowflake/sql/bootstrap_native_pull.py \
  --aws-root infra/terraform/accounts/dev \
  --snowflake-root infra/terraform/snowflake/accounts/dev \
  --connection edgartools-dev \
  --artifact-path infra/snowflake/sql/dev_native_pull_handshake.json \
  --validate-native-pull
```

The SQL files under `bootstrap/` are no longer the deployment mechanism. They remain in the repo as
reference implementations for the object contract now encoded in Terraform.
