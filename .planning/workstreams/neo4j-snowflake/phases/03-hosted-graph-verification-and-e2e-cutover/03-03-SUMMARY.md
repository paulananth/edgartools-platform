---
phase: 03-hosted-graph-verification-and-e2e-cutover
plan: 03
subsystem: aws-mdm-e2e
status: blocked
tags: [aws, snowflake, mdm, graph, e2e]

requires:
  - phase: 03-02
    provides: Strict hosted `verify-graph` with required Native App proof
provides:
  - AWS MDM E2E script cut over from external Neo4j connectivity success gate to hosted graph validation semantics
  - Warning-only handling for lingering Neo4j deployment/script references
  - Live dev evidence showing SQL parity and grants pass, with Native App compute pool as the remaining blocker
affects:
  - Phase 3 final verification
  - AWS dev hosted graph E2E acceptance run

tech-stack:
  added: []
  patterns:
    - `mdm_check_connectivity` is no longer a required success step for hosted graph E2E
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
  - "Live dev final acceptance is blocked until `Neo4j_Graph_Analytics` exposes a compute pool selector."
  - "The grant SQL now includes Native App account privileges required by the Phase 1 runbook: `CREATE COMPUTE POOL` and `CREATE WAREHOUSE`."

requirements-progress: [SYNC-04]
blocked-requirements: [VERIFY-05]

completed: null
blocked: 2026-06-12
---

# Phase 3 Plan 03: AWS Hosted Graph E2E Cutover Summary

Plan 03-03 was partially executed and is blocked on live Snowflake Native App compute-pool availability.

## Accomplishments

- Updated `infra/scripts/run-aws-mdm-e2e.sh` wording from MDM/Neo4j to MDM hosted graph validation.
- Removed `mdm_check_connectivity` from the required E2E start-and-wait chain.
- Preserved `--status-only` behavior.
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
- `verify-graph` SQL parity passed:
  - graph nodes: `15`
  - graph edges: `4`
  - node parity: `ok`
  - relationship parity: `ok`
  - diagnostics: no missing/extra nodes, edges, or endpoints
- Native App prerequisite checks passed through database privileges and graph schema sample access.
- Native App compute pool check failed because `CALL Neo4j_Graph_Analytics.graph.show_available_compute_pools();` returned no rows.
- AWS Step Functions status-only check succeeded and showed existing `mdm_sync_graph` and `mdm_verify_graph` historical successes, but those are not final acceptance evidence for this branch.

## Blocker

`Neo4j_Graph_Analytics` must be activated or repaired in Snowflake dev so the Native App exposes `CPU_X64_XS` or another supported compute pool selector. Until then, strict `verify-graph` correctly fails and full AWS hosted graph E2E cannot be counted as successful.

## Next

After the Native App compute pool is available and a dev AWS image containing this branch is deployed, rerun:

```bash
bash infra/scripts/run-aws-mdm-e2e.sh \
  --env dev \
  --aws-profile sec_platform_deployer
```

Then update `03-LIVE-DEV-RUN.md` with passing `GRAPH_INFO`/`BFS`/`WCC` proof and Step Functions execution ARNs/statuses.
