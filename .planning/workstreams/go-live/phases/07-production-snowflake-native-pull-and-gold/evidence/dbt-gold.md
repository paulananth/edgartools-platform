# dbt Gold Evidence - Phase 7 Production Snowflake Native Pull And Gold

Date: 2026-06-20 UTC
Environment: prod
Requirement: SNOW-04

## Phase 7 Plan 07-02 Dependency Preflight

Result: BLOCKED - production dbt/gold execution was not started.

Plan 07-02 depends on Plan 07-01 passing SNOW-03. Plan 07-01 completed its
preflight with SNOW-03 BLOCKED because the prod operator-local Terraform input
files for the native-pull stack are absent in this worktree. Because the
native-pull prerequisite did not pass, 07-02 stopped before profile setup,
grant discovery, dbt execution, status queries, or freshness checks.

## Local dbt Input Presence

The following checks recorded only presence/absence, not credential values:

| Input | Status |
| --- | --- |
| `DBT_SNOWFLAKE_ACCOUNT` | unset |
| `DBT_SNOWFLAKE_USER` | unset |
| `DBT_SNOWFLAKE_PASSWORD` | unset |
| `DBT_SNOWFLAKE_ROLE` | unset |
| `DBT_SNOWFLAKE_DATABASE` | unset |
| `DBT_SNOWFLAKE_WAREHOUSE` | unset |
| `infra/snowflake/dbt/edgartools_gold/profiles.yml` | missing |

`profiles.yml` was intentionally not created because the dependency gate stopped
execution before dbt setup. No production credential placeholders or live values
were written.

## Expected Non-Secret Production Names

The dbt production target still expects these project-standard object names when
07-02 is rerun after SNOW-03 passes:

| Setting | Expected name |
| --- | --- |
| Database | `EDGARTOOLS_PROD` |
| Deployer role | `EDGARTOOLS_PROD_DEPLOYER` |
| Refresh warehouse | `EDGARTOOLS_PROD_REFRESH_WH` |
| Source schema | `EDGARTOOLS_SOURCE` |
| Gold schema | `EDGARTOOLS_GOLD` |

These names are configuration identifiers only; no account locator, password,
token, DSN, ARN, external ID, S3 URL, query result row, or generated artifact was
captured.

## Commands Not Run

No state-changing or live Snowflake/dbt command was run for 07-02.

| Check | Status |
| --- | --- |
| `SHOW GRANTS TO ROLE EDGARTOOLS_PROD_DEPLOYER` | not run |
| `uv run --with dbt-snowflake dbt deps` | not run |
| `uv run --with dbt-snowflake dbt run --target prod` | not run |
| `uv run --with dbt-snowflake dbt test --target prod` | not run |
| `EDGARTOOLS_GOLD_STATUS` status query | not run |
| Dynamic table freshness query | not run |
| Task history query | not run |
| Source mirror row-count query | not run |

## Launch Gate Impact

SNOW-04 remains BLOCKED. The production dbt/gold launch gate cannot be evaluated
until SNOW-03 passes native-pull validation and the operator supplies production
dbt credentials outside git.

Required remediation:

1. Re-run 07-01 after the six prod native-pull Terraform input files are present
   and capture passing SNOW-03 evidence.
2. Re-run 07-02 with production `DBT_SNOWFLAKE_*` variables supplied outside
   git.
3. Confirm direct source-table grants for `EDGARTOOLS_PROD_DEPLOYER`.
4. Run dbt deps/run/test for the production target.
5. Capture summarized `EDGARTOOLS_GOLD_STATUS`, dynamic-table freshness, task
   history, and source mirror row-count evidence without raw result dumps.
