---
phase: 04-dashboard-hosted-graph-migration
plan: 01
subsystem: dashboard
status: completed
tags: [snowflake, mdm, graph, dashboard, native-app]

requires:
  - phase: 03-01
    provides: Strict Snowflake SQL graph parity verification semantics
  - phase: 03-02
    provides: Native App compute pool and graph algorithm proof checks
provides:
  - Hosted graph read-only helper for dashboard-ready Snowflake graph metrics
  - Secret-safe unavailable and permission-denied payloads for dashboard rendering
  - Bounded node, edge, endpoint, entity type, and relationship type diagnostics
  - Architecture guardrails that keep the hosted graph dashboard helper read-only
affects:
  - Phase 4 Streamlit dashboard migration
  - Phase 4 dashboard documentation and final verification

tech-stack:
  added: []
  patterns:
    - Dashboard graph data reuses `SnowflakeGraphVerifier` instead of shelling out to the CLI
    - Native App failures expose only failing checks, sanitized details, and remediation text
    - Dashboard unavailable states name expected setting names without returning connector exceptions

key-files:
  created:
    - edgar_warehouse/mdm/graph_readonly.py
    - tests/mdm/test_graph_readonly.py
  modified:
    - tests/architecture/test_dashboard_foundation_boundaries.py

key-decisions:
  - "The dashboard helper is an inspection surface, not a new acceptance gate."
  - "The helper does not expose sync, repair, grant, activation, migration, or write operations."
  - "No changes to `snowflake_graph.py` were needed; the helper adapts verifier output at the dashboard boundary."

requirements-progress: [VERIFY-04, DASH-01, DASH-02, DASH-03]
blocked-requirements: []

completed: 2026-06-12
blocked: null
---

# Phase 4 Plan 01: Hosted Graph Read-Only Helper Summary

The dashboard can now consume strict Snowflake hosted graph verification output through a read-only, secret-safe helper.

## Accomplishments

- Added `edgar_warehouse/mdm/graph_readonly.py` with `get_snowflake_graph_metrics(...)` and a serializable metrics dataclass.
- Normalized strict `verify-graph` results into dashboard-ready node counts, edge counts, entity comparison rows, relationship comparison rows, bounded diagnostics, and Native App failure rows.
- Preserved Native App diagnosis for compute pool, `GRAPH_INFO`, `BFS`, and `WCC` failures while suppressing raw connector exceptions and secrets.
- Added architecture coverage that rejects CLI shell-outs, subprocess usage, external Neo4j credential dependencies, and mutation-oriented MDM surfaces in the helper.

## Task Commits

1. **Task 1: Add hosted graph helper tests** - `0eb78af` (test)
2. **Task 2: Implement hosted graph read-only helper** - `c7a46af` (feat)

## Files Created/Modified

- `edgar_warehouse/mdm/graph_readonly.py` - Hosted graph dashboard helper over the strict Snowflake verifier.
- `tests/mdm/test_graph_readonly.py` - Credential-free helper tests for success mapping, diagnostics, Native App failures, unavailable states, bounded samples, timestamps, and secret safety.
- `tests/architecture/test_dashboard_foundation_boundaries.py` - Read-only hosted graph dashboard boundary checks.

## Verification

- RED check: `uv run pytest tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q` failed before implementation because `edgar_warehouse/mdm/graph_readonly.py` was missing.
- `uv run pytest tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q` passed: `24 passed`.
- `uv run pytest tests/mdm/test_graph_readonly.py tests/mdm/test_cli_snowflake_graph.py tests/mdm/test_snowflake_graph_migration.py -q` passed: `23 passed`.
- `uv run pytest tests/mdm/test_graph_readonly.py tests/mdm/test_cli_snowflake_graph.py tests/mdm/test_snowflake_graph_migration.py tests/architecture/test_dashboard_foundation_boundaries.py -q` passed: `42 passed`.
- `python3 -m py_compile edgar_warehouse/mdm/graph_readonly.py tests/mdm/test_graph_readonly.py` passed.

## Decisions Made

- Reused `SnowflakeGraphVerifier` and `SnowflakeGraphVerificationConfig` as the single source of parity semantics.
- Kept healthy Native App proof out of primary dashboard chrome; the helper surfaces failing checks for operator diagnosis.
- Kept Phase 4 requirements pending until the existing Streamlit dashboard and final dashboard verification are completed.

## Deviations from Plan

None. `snowflake_graph.py` was listed as a possible implementation file, but no verifier changes were necessary.

## Issues Encountered

None.

## Next Phase Readiness

Plan 04-02 can migrate the existing Streamlit review dashboard to consume `get_snowflake_graph_metrics(...)` instead of external Neo4j/Bolt assumptions.
