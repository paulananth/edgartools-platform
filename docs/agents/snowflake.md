# Snowflake native S3 pull, dbt and the dashboard

Moved out of AGENTS.md (ticket 63) unchanged: reference read when a task touches Snowflake or dbt. Snowflake is the target platform; use the [aws-snowflake-operations](../../skills/aws-snowflake-operations/SKILL.md) skill before any command.

## Snowflake Native S3 Pull

Snowflake is the analytics target for the AWS path. Use the wrapper for normal AWS/Snowflake native-pull deployment:

```bash
bash infra/scripts/deploy-snowflake-stack.sh \
  --env prod \
  --snow-connection edgartools-prod
```

The wrapper coordinates:

1. AWS access bootstrap apply with temporary Snowflake trust and deterministic external ID.
2. Snowflake provisioning for storage integration, S3 stage, source mirror tables, pipe, stream, procedures, and task.
3. AWS access reconcile apply narrowed to the Snowflake-managed AWS principal.
4. Snowflake provisioning re-apply.
5. Snowflake access Terraform apply.
6. Optional native-pull validation, dbt run/test, and dashboard upload.

Useful flags:

```bash
bash infra/scripts/deploy-snowflake-stack.sh --env-name prod --snow-connection edgartools-prod --run-validation
bash infra/scripts/deploy-snowflake-stack.sh --env-name prod --snow-connection edgartools-prod --run-dbt
bash infra/scripts/deploy-snowflake-stack.sh --env-name prod --snow-connection edgartools-prod --upload-dashboard
```

Native-pull gotchas:

- `snowflake_export_root_url` must include the trailing slash on `snowflake_exports/`.
- Capture `snowflake_manifest_sns_topic_arn` from AWS provisioning outputs.
- The SnowCLI connection must exist before running the wrapper.
- Snowflake Enterprise or higher is required for dynamic tables.

### Dev Snowflake Connection

For all local verification, DDL deployment, and `snow sql` commands targeting the dev Snowflake account, always use:

```bash
export SNOW_CONNECTION=snowconn
```

The `snowconn` connection uses ACCOUNTADMIN role, which is required for `CREATE STORAGE INTEGRATION` (needed by `01_source_stage.sql`) and all other DDL operations in the dev account. Do not use `YG91578` or `edgartools-dev` for verification scripts — those connections lack the required privileges.

## dbt And Dashboard

dbt project root:

```bash
cd infra/snowflake/dbt/edgartools_gold
```

Use environment-backed profiles:

```bash
cp profiles.yml.example profiles.yml
export DBT_SNOWFLAKE_ACCOUNT="ORGNAME-ACCOUNTNAME"
export DBT_SNOWFLAKE_USER="your_user"
export DBT_SNOWFLAKE_PASSWORD="your_password"
export DBT_SNOWFLAKE_ROLE="EDGARTOOLS_PROD_DEPLOYER"
export DBT_SNOWFLAKE_DATABASE="EDGARTOOLS_PROD"
export DBT_SNOWFLAKE_WAREHOUSE="EDGARTOOLS_PROD_REFRESH_WH"
```

Run with `uv`:

```bash
uv run --with dbt-snowflake dbt deps
uv run --with dbt-snowflake dbt compile --target prod
uv run --with dbt-snowflake dbt run --target prod
uv run --with dbt-snowflake dbt test --target prod
```

Dashboard artifact upload:

```bash
SNOW_CONNECTION=edgartools-prod \
DASHBOARD_DATABASE=EDGARTOOLS_PROD \
bash infra/snowflake/streamlit/deploy.sh
```
