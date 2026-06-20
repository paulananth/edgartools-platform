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

## Launch Gate Impact (initial)

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

## Dependency Update (branch takeover, 2026-06-19 continuation)

SNOW-03's blocking dependency has been resolved — see
`evidence/native-pull.md`'s "Phase 7 Plan 07-01 Retry" section. As part of
that work, a production service user (`EDGARTOOLS_PROD_DEPLOYER`) was created
and verified end-to-end: it authenticates correctly, holds exactly the
`EDGARTOOLS_PROD_DEPLOYER` role, and has confirmed `SELECT` access on the
source schema's tables. Credentials are stored in a new AWS secret,
`edgartools-prod/dbt/snowflake`, using the `DBT_SNOWFLAKE_ACCOUNT/USER/
PASSWORD/ROLE/DATABASE/WAREHOUSE` key schema dbt's `profiles.yml` and
`edgar_warehouse/mdm/export.py`'s `_snowflake_setting()` both already expect.
This secret is intentionally separate from `edgartools-prod/mdm/snowflake`
(Phase 8/MDM-02-owned, per D-05/D-06) to avoid a future cross-phase overwrite.

Updated local input table:

| Input | Status |
| --- | --- |
| `DBT_SNOWFLAKE_ACCOUNT` | set (sourced from `edgartools-prod/dbt/snowflake` at runtime) |
| `DBT_SNOWFLAKE_USER` | set (`EDGARTOOLS_PROD_DEPLOYER`) |
| `DBT_SNOWFLAKE_PASSWORD` | set (rotated once; never printed; stored only in Secrets Manager) |
| `DBT_SNOWFLAKE_ROLE` | set (`EDGARTOOLS_PROD_DEPLOYER`) |
| `DBT_SNOWFLAKE_DATABASE` | set (`EDGARTOOLS_PROD`) |
| `DBT_SNOWFLAKE_WAREHOUSE` | set (`EDGARTOOLS_PROD_REFRESH_WH`) |
| `infra/snowflake/dbt/edgartools_gold/profiles.yml` | still missing — not yet created |

**`dbt deps`/`dbt run`/`dbt test` have deliberately not been run.** Creating
the user and populating the credential secret was the explicitly requested
scope for this continuation; actually building the 9 production gold dynamic
tables + 1 status view is a separate, further state-changing action this
evidence update does not assume approval for.

## Launch Gate Impact (final, this continuation)

SNOW-04 status: **BLOCKED, dependency cleared, ready to retry on explicit
approval.** All preconditions the original remediation plan listed are now
satisfied except the actual dbt execution:

1. ~~Re-run 07-01 ... capture passing SNOW-03 evidence~~ — done, see
   `native-pull.md`.
2. ~~Re-run 07-02 with production `DBT_SNOWFLAKE_*` variables supplied outside
   git~~ — credentials now exist in `edgartools-prod/dbt/snowflake`.
3. ~~Confirm direct source-table grants for `EDGARTOOLS_PROD_DEPLOYER`~~ —
   confirmed via a live `SELECT` against the source schema as that exact user.
4. **Not yet done:** run `dbt deps`/`dbt run --target prod`/`dbt test --target
   prod`, which creates the 9 production gold dynamic tables + 1 status view.
5. **Not yet done:** capture summarized `EDGARTOOLS_GOLD_STATUS`,
   dynamic-table freshness, task history, and source mirror row-count
   evidence.
