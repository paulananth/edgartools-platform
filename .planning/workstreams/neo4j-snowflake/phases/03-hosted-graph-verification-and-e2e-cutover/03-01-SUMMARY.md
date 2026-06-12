---
phase: 03-hosted-graph-verification-and-e2e-cutover
plan: 01
subsystem: hosted-graph-verification
tags: [snowflake, mdm, graph, verification, parity]

requires:
  - phase: 02-03
    provides: Snowflake graph sync CLI wiring and graph-ready tables
provides:
  - Strict SQL parity verification for `edgar-warehouse mdm verify-graph`
  - Structured node, edge, and endpoint diagnostics for hosted graph mismatches
  - Credential-free regression tests for Snowflake graph verification
affects:
  - Phase 3 Plan 03-02 Native App smoke proof
  - Phase 3 Plan 03-03 AWS MDM E2E cutover

tech-stack:
  added: []
  patterns:
    - CLI handlers return secret-safe JSON and nonzero exits for failed gates
    - Snowflake graph verification uses reusable connection settings and fake cursor tests

key-files:
  modified:
    - edgar_warehouse/mdm/cli.py
    - edgar_warehouse/mdm/snowflake_graph.py
    - tests/mdm/test_cli_snowflake_graph.py
    - tests/mdm/test_export.py

key-decisions:
  - "`verify-graph` now uses a reusable `SnowflakeGraphVerifier` instead of direct node/edge count SQL in the CLI handler."
  - "The verifier reports node parity by entity type, relationship parity by relationship type, and bounded mismatch samples."
  - "Native App `GRAPH_INFO`/`BFS`/`WCC` proof remains Plan 03-02; this plan establishes the SQL parity gate it will extend."

requirements-progress: [SYNC-04, VERIFY-01, VERIFY-02]

completed: 2026-06-11
---

# Phase 3 Plan 01: Strict Snowflake SQL Parity Gate Summary

`edgar-warehouse mdm verify-graph` now verifies Snowflake-hosted graph tables against active MDM source rows instead of checking only that graph node and edge tables are nonempty.

## Accomplishments

- Added `SnowflakeGraphVerificationConfig`, `SnowflakeGraphVerificationResult`, and `SnowflakeGraphVerifier`.
- Added SQL parity queries for:
  - active MDM entities vs `MDM_GRAPH_NODES` by entity type,
  - active MDM relationship instances vs `MDM_GRAPH_EDGES` by relationship type,
  - missing and extra graph node samples,
  - missing and extra graph edge samples,
  - graph edges whose source or target node is missing.
- Rewired `_handle_verify_graph` to emit the strict parity payload and fail on any mismatch.
- Added credential-free fake-cursor tests for success, node mismatch diagnostics, relationship mismatch diagnostics, and endpoint diagnostics.
- Tightened `tests/mdm/test_export.py` so the missing-settings test is isolated from local Snowflake CLI config.

## Verification

- `uv run --extra mdm-runtime pytest tests/mdm/test_cli_snowflake_graph.py -q` passed: `7 passed`.
- `uv run --extra mdm-runtime pytest tests/mdm/test_cli_snowflake_graph.py tests/mdm/test_snowflake_graph_migration.py tests/mdm/test_export.py -q` passed: `21 passed`.

## Next

Proceed to Plan 03-02: Native App grant automation, grant validation, and default `GRAPH_INFO`/`BFS`/`WCC` proof inside `verify-graph`.
