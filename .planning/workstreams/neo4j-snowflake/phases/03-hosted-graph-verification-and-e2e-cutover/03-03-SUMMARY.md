---
phase: 03-hosted-graph-verification-and-e2e-cutover
plan: 03
subsystem: aws-mdm-e2e
status: completed
tags: [aws, snowflake, mdm, graph, e2e]

requires:
  - phase: 03-02
    provides: Strict hosted `verify-graph` with required Native App proof
provides:
  - AWS MDM E2E script cut over from external Neo4j connectivity success gate to hosted graph validation semantics
  - Local strict `verify-graph` preflight before AWS Step Functions executions
  - Warning-only handling for lingering Neo4j deployment/script references
  - Live dev evidence showing strict hosted graph verification and AWS MDM E2E pass
affects:
  - Phase 3 final verification
  - AWS dev hosted graph E2E acceptance run

tech-stack:
  added: []
  patterns:
    - `mdm_check_connectivity` is no longer a required success step for hosted graph E2E
    - full E2E runs preflight local strict `verify-graph` before starting AWS executions
    - `mdm_sync_graph` and strict `mdm_verify_graph` remain required E2E steps
    - stale `NEO4J_*` references are warnings unless they block the hosted path

key-files:
  added:
    - .planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md
  modified:
    - infra/scripts/run-aws-mdm-e2e.sh
    - infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql
    - tests/architecture/test_dashboard_foundation_boundaries.py
    - tests/mdm/test_snowflake_graph_migration.py

key-decisions:
  - "The AWS E2E script now runs MDM hosted graph validation, not MDM/Neo4j connectivity validation."
  - "Live dev final acceptance requires both local strict `verify-graph` Native App proof and AWS `mdm_sync_graph` plus `mdm_verify_graph` Step Functions success."
  - "The grant SQL now includes Native App account privileges required by the Phase 1 runbook: `CREATE COMPUTE POOL` and `CREATE WAREHOUSE`."

requirements-progress: [SYNC-04, VERIFY-05]
blocked-requirements: []

completed: 2026-06-12
blocked: null
---

# Phase 3 Plan 03: AWS Hosted Graph E2E Cutover Summary

Plan 03-03 was executed and accepted in live dev.

## Accomplishments

- Updated `infra/scripts/run-aws-mdm-e2e.sh` wording from MDM/Neo4j to MDM hosted graph validation.
- Removed `mdm_check_connectivity` from the required E2E start-and-wait chain.
- Preserved `--status-only` behavior.
- Added default local strict `edgar-warehouse mdm verify-graph` preflight before AWS Step Functions executions.
- Added `--snow-connection`, `--snowflake-database`, and `--native-app-compute-pool` preflight flags.
- Added emergency `--skip-preflight`, with warning output that skipped-preflight runs cannot satisfy Phase 3 acceptance.
- Kept `mdm_migrate`, `mdm_run`, `mdm_backfill_relationships`, `mdm_sync_graph`, `mdm_verify_graph`, and `mdm_counts` as the hosted graph E2E chain.
- Added warning-only detection for lingering `NEO4J_*`, `neo4j`, `--neo4j`, and `mdm_check_connectivity` references in deployment artifacts/scripts.
- Added architecture coverage for the hosted graph E2E script contract.
- Updated the Native App grant SQL with account-level `CREATE COMPUTE POOL` and `CREATE WAREHOUSE` grants after live validation showed they were missing from the runbook automation.
- Captured live dev evidence in `03-LIVE-DEV-RUN.md`.

## Verification

- `bash -n infra/scripts/run-aws-mdm-e2e.sh` passed.
- `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` passed: `16 passed, 1 skipped`.
- `uv run --extra mdm-runtime pytest tests/mdm/test_snowflake_graph_migration.py tests/mdm/test_cli_snowflake_graph.py -q` passed: `18 passed`.

## Live Dev Result

- Native App/database grants were applied successfully.
- The initial strict `verify-graph` run proved SQL parity but failed because
  `CALL Neo4j_Graph_Analytics.graph.show_available_compute_pools();` returned no rows.
- After operator activation/repair, strict `verify-graph` passed:
  - graph nodes: `15`
  - graph edges: `4`
  - node parity: `ok`
  - relationship parity: `ok`
  - diagnostics: no missing/extra nodes, edges, or endpoints
  - Native App compute pool: `CPU_X64_XS`
  - Native App smoke proof: `GRAPH_INFO`, `BFS`, and `WCC` all `ok`
  - `phase3_acceptance`: `true`
- AWS Step Functions status-only check succeeded and showed the latest hosted graph E2E
  executions succeeded:
  - `mdm_migrate`: `aws-mdm-e2e-1781277675-migrate`
  - `mdm_run`: `aws-mdm-e2e-1781277675-run`
  - `mdm_backfill_relationships`: `aws-mdm-e2e-1781277675-backfill`
  - `mdm_sync_graph`: `aws-mdm-e2e-1781277675-sync`
  - `mdm_verify_graph`: `aws-mdm-e2e-1781277675-verify`
  - `mdm_counts`: `aws-mdm-e2e-1781277675-counts`

## Next

Phase 4 should migrate the review dashboard to the Snowflake-hosted graph target. For
future regression checks, rerun:

```bash
bash infra/scripts/run-aws-mdm-e2e.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --snow-connection snowconn \
  --snowflake-database EDGARTOOLS_DEV
```
