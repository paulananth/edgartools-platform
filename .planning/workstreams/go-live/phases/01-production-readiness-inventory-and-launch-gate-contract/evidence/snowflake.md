# Snowflake Evidence - Phase 1 Production Readiness

Date: 2026-06-14 UTC
Environment: production required; dev rows are precedent only and require separate production proof.
Snowflake connection: production connection required.
Snowflake database: production database required.

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs, full task logs, secret ARNs, and raw Native App job logs.

## Source-Of-Truth Note

Live Snowflake command checks are authoritative for production readiness. Manifests and documentation are supporting evidence only. Production native-pull, dbt, gold status, freshness, and grant checks remain blocked until production identifiers and live access are available.

## Phase 1 Read-Only Checks Actually Run

```bash
for v in DBT_SNOWFLAKE_ACCOUNT DBT_SNOWFLAKE_USER DBT_SNOWFLAKE_PASSWORD DBT_SNOWFLAKE_DATABASE SNOW_CONNECTION SNOWFLAKE_CONNECTION; do
  if [ -n "${!v:-}" ]; then echo "$v=set"; else echo "$v=unset"; fi
done
```

Result: succeeded.

- `DBT_SNOWFLAKE_ACCOUNT`: unset.
- `DBT_SNOWFLAKE_USER`: unset.
- `DBT_SNOWFLAKE_PASSWORD`: unset.
- `DBT_SNOWFLAKE_DATABASE`: unset.
- `SNOW_CONNECTION`: unset.
- `SNOWFLAKE_CONNECTION`: unset.
- `dbt compile` was not run because this shell has no Snowflake/dbt target configuration. This is recorded as a blocked production step, not as evidence.

```bash
find infra/snowflake/dbt/edgartools_gold/models/gold -maxdepth 1 -type f \
  \( -name '*.sql' -o -name '*.yml' -o -name '*.yaml' \) | sort | wc -l
find infra/snowflake/dbt/edgartools_gold/models/gold -maxdepth 1 -type f -name '*.sql' | sort
```

Result: succeeded.

- Gold model/config files at this level: `18`.
- Gold SQL models found: `16`.
- `infra/snowflake/dbt/edgartools_gold/models/gold/edgartools_gold_status.sql` is present.
- Static model inventory is supporting context only. It is not production dbt proof.

## Not-Yet-Runnable Production Steps

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Snowflake native S3 pull stack (infra/scripts/deploy-snowflake-stack.sh)`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Snowflake deployer direct grants for gold dynamic tables`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `dbt compile/run/test for production target`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `EDGARTOOLS_GOLD_STATUS and dynamic-table freshness`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Strict edgar-warehouse mdm verify-graph`.

Planned production `deploy-snowflake-stack.sh --run-validation`, `dbt run`, `dbt test`, and gold freshness SQL checks are not evidence entries here because they were not run during Phase 1.

## Known Grant Gap

`TODOS.md` records that `EDGARTOOLS_DEV_DEPLOYER` lacked direct `SELECT` on `EDGARTOOLS_SOURCE`, which blocked `dbt run --full-refresh` for any gold dynamic table until an ad-hoc dev grant was applied. If `EDGARTOOLS_PROD_DEPLOYER` has the analogous direct-grant gap, production dynamic-table refresh can fail even when ad-hoc queries work through secondary roles.

This is recorded as a matrix blocker, not a pass:

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Snowflake deployer direct grants for gold dynamic tables`.

## Dev Precedent Reconciliation

dev precedent only — prod proof required separately

Existing project evidence shows dev Snowflake-hosted graph verification and dbt/gold workflows have been exercised in prior workstreams, including strict dev `mdm verify-graph` success after Native App compute pool activation. The dev static dbt model inventory in this checkout includes `EDGARTOOLS_GOLD_STATUS`.

Production still requires:

- production Snowflake connection and database,
- production native-pull validation or live discovery,
- production dbt compile/run/test evidence,
- production deployer direct-grant proof for dynamic-table refresh,
- production `EDGARTOOLS_GOLD_STATUS` and freshness summary.

## Gold Status And Freshness Summary Shape

To be filled only after production checks actually run:

| Model/Table | Status | Last refresh |
| --- | --- | --- |
| `EDGARTOOLS_GOLD_STATUS` | pending production proof | pending production proof |
| dynamic tables | pending production proof | pending production proof |

## Generated-JSON Summary Rule

Any generated Snowflake or dbt artifact referenced by go-live evidence must be summarized only as path, existence, top-level purpose, and pass/fail result. Do not paste raw logs, compiled SQL containing sensitive values, Terraform state, or full generated JSON bodies.
