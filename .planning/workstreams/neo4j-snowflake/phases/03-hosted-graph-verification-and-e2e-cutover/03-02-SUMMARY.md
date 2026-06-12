---
phase: 03-hosted-graph-verification-and-e2e-cutover
plan: 02
subsystem: hosted-graph-verification
tags: [snowflake, mdm, graph, native-app, verification]

requires:
  - phase: 03-01
    provides: Strict Snowflake SQL parity verification for `verify-graph`
provides:
  - Repo-managed least-privilege Native App grant SQL for `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION`
  - Default `verify-graph` hard gate for Native App installation, app roles, database-role grants, compute pool, and graph schema access
  - Default `GRAPH_INFO`, `BFS`, and `WCC` smoke SQL execution after prerequisites pass
  - Explicit offline-only `--skip-native-app` path that cannot satisfy Phase 3 live acceptance
affects:
  - Phase 3 Plan 03-03 AWS MDM E2E cutover and live dev evidence capture
  - Operator Snowflake grant setup for the Neo4j Graph Analytics Native App

tech-stack:
  added: []
  patterns:
    - `verify-graph` fails hard when Native App prerequisites or smoke SQL fail
    - Missing Native App setup emits structured remediation pointing to the repo-managed grant SQL
    - Algorithm smoke checks run only after prerequisite checks are clean

key-files:
  added:
    - infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql
  modified:
    - edgar_warehouse/mdm/cli.py
    - edgar_warehouse/mdm/snowflake_graph.py
    - tests/mdm/test_cli_snowflake_graph.py
    - tests/mdm/test_snowflake_graph_migration.py

key-decisions:
  - "`verify-graph` now includes a required Native App section by default and combines it into the command exit status."
  - "Least-privilege grant setup uses `NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE`, app user/admin consumer roles, table/view SELECT, and scoped CREATE TABLE for algorithm outputs."
  - "`--skip-native-app` remains available only for local/offline parity tests and returns `phase3_acceptance: false`."
  - "Live Snowflake grant application was not performed in this plan; Plan 03-03 owns the operator-applied dev run and evidence capture."

requirements-progress: [SYNC-04, SNOW-03, VERIFY-01, VERIFY-03]

completed: 2026-06-11
---

# Phase 3 Plan 02: Native App Grant And Smoke Proof Summary

`edgar-warehouse mdm verify-graph` now validates the hosted Neo4j Graph Analytics Native App path, not only Snowflake table parity.

## Accomplishments

- Added `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` for dev Native App setup with dedicated database role, app role grants, table/view SELECT, future object grants, and scoped CREATE TABLE output permission.
- Extended `SnowflakeGraphVerificationConfig` with Native App name, database role, compute pool, and `verify_native_app` controls.
- Added Native App checks for installation, `app_user` and `app_admin` role grants, database role grant to the application, graph schema privileges, compute pool availability, and graph schema sample access.
- Added default `GRAPH_INFO`, `BFS`, and `WCC` smoke SQL execution after prerequisites pass.
- Added `edgar-warehouse mdm verify-graph --skip-native-app` for local/offline tests, with output explicitly marked as not satisfying Phase 3 live acceptance.
- Added credential-free tests for success, missing grant failure with remediation, offline skip semantics, and grant SQL least-privilege intent.

## Verification

- `uv run --extra mdm-runtime pytest tests/mdm/test_snowflake_graph_migration.py -q` passed: `9 passed`.
- `uv run --extra mdm-runtime pytest tests/mdm/test_cli_snowflake_graph.py tests/mdm/test_snowflake_graph_migration.py -q` passed: `18 passed`.
- `uv run --extra mdm-runtime pytest tests/mdm/test_cli_snowflake_graph.py tests/mdm/test_snowflake_graph_migration.py tests/mdm/test_export.py -q` passed: `24 passed`.

## Live Validation Note

The repo now contains the operator-run grant SQL, but this plan did not mutate the live Snowflake dev account. Plan 03-03 should apply or confirm the dev grants, then run `SNOW_CONNECTION=snowconn DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV edgar-warehouse mdm verify-graph` and capture non-secret evidence.

## Next

Proceed to Plan 03-03: cut AWS MDM E2E validation over to Snowflake `sync-graph` plus strict hosted `verify-graph`, then capture the live dev proof.
