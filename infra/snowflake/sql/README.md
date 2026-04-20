# Snowflake SQL Bootstrap Assets

This directory contains the SnowCLI-oriented SQL bootstrap assets for the Snowflake gold mirror.

These files are the layer between:

- Terraform-managed Snowflake platform objects in `infra/terraform/snowflake/`
- dbt-managed gold models in `infra/snowflake/dbt/edgartools_gold/`

## Scope

The bootstrap SQL is responsible for:

1. the storage integration, S3 import path, and run-manifest auto-ingest objects
2. the technical per-run refresh-status table and manifest stream
3. the source-side load wrapper
4. the public gold refresh wrapper and triggered manifest-processing task that waits for dbt-owned dynamic tables

The dbt project is responsible for:

- curated gold models
- dynamic tables
- the business-facing `EDGARTOOLS_GOLD_STATUS` view

## Execution order

Use the bootstrap driver after the baseline database, schemas, roles, and warehouses exist:

```bash
uv run python infra/snowflake/sql/bootstrap_native_pull.py \
  --aws-root infra/terraform/accounts/dev \
  --snowflake-root infra/terraform/snowflake/accounts/dev \
  --connection snowconn \
  --artifact-path infra/snowflake/sql/dev_native_pull_handshake.json
```

The driver runs these files in order, captures `DESC INTEGRATION`, and emits the
`snowflake_storage_external_id` value that must be fed back into AWS Terraform:

1. `bootstrap/01_source_stage.sql`
2. `bootstrap/02_refresh_status.sql`
3. `bootstrap/03_source_load_wrapper.sql`
4. `bootstrap/04_refresh_wrapper.sql`
5. `bootstrap/05_refresher_keypair.sql` (deprecated no-op marker)

After applying the AWS root with that external ID and the export-role KMS permissions, rerun the
driver with `--storage-external-id` and `--validate-native-pull` to confirm `LIST` and
`COPY_HISTORY` succeed.

## Required session variables

The driver sets these Snowflake session variables automatically. If you run the SQL files
manually in a single Snowflake session, set:

- `database_name`
- `source_schema_name`
- `gold_schema_name`
- `deployer_role_name`
- `storage_integration_name`
- `storage_role_arn`
- `storage_external_id`
- `export_root_url`
- `stage_name`
- `parquet_file_format_name`
- `manifest_file_format_name`
- `manifest_inbox_table_name`
- `manifest_pipe_name`
- `manifest_stream_name`
- `manifest_task_name`
- `manifest_sns_topic_arn`
- `refresh_warehouse_name`
- `status_table_name`
- `source_load_procedure_name`
- `refresh_procedure_name`
- `stream_processor_procedure_name`

The SQL files use `IDENTIFIER($variable_name)` so one file set can serve both `dev` and `prod`.
For the S3 import path, `export_root_url` should include the trailing slash on the
`snowflake_exports/` prefix so it matches the Snowflake integration allow-list exactly.
