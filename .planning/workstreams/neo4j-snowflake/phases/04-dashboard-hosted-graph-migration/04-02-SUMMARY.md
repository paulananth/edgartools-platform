---
phase: 04-dashboard-hosted-graph-migration
plan: 02
subsystem: dashboard
status: completed
tags: [streamlit, snowflake, mdm, graph, dashboard, native-app]

requires:
  - phase: 04-01
    provides: Hosted graph read-only helper over strict Snowflake verification semantics
provides:
  - Existing Streamlit dashboard migrated to Snowflake-hosted graph comparison payloads
  - Snowflake graph node/edge overview metrics and comparison tables
  - Bounded mismatch diagnostics for missing/extra nodes, missing/extra edges, and missing edge endpoints
  - Failure-only Native App detail table for compute pool, `GRAPH_INFO`, `BFS`, and `WCC` failures
affects:
  - Phase 4 dashboard documentation and final verification
  - Operator hosted graph mismatch review workflow

tech-stack:
  added: []
  patterns:
    - Streamlit remains a renderer over read-only helper payloads
    - `Neo4j Overview` route label is preserved while page copy names Snowflake-hosted graph state
    - Native App proof is quiet when healthy and visible only for failing checks

key-files:
  created: []
  modified:
    - examples/mdm_graph_dashboard/streamlit_app.py
    - tests/architecture/test_dashboard_foundation_boundaries.py

key-decisions:
  - "The dashboard now consumes `graph_readonly.get_snowflake_graph_metrics(...)`; it does not call the old external graph metric path."
  - "Row limit is passed to the hosted graph helper as the bounded diagnostic sample limit."
  - "Dashboard copy and active UI guardrails now allow Snowflake-hosted graph terminology while continuing to block external Neo4j/Bolt assumptions."

requirements-progress: [VERIFY-04, DASH-01, DASH-02, DASH-03]
blocked-requirements: []

completed: 2026-06-12
blocked: null
---

# Phase 4 Plan 02: Dashboard Hosted Graph Migration Summary

The existing Streamlit MDM review dashboard now renders Snowflake-hosted graph parity, bounded mismatch diagnostics, and failure-only Native App readiness detail.

## Accomplishments

- Replaced the old external graph metrics path with `graph_readonly.get_snowflake_graph_metrics(...)`.
- Preserved the existing four routes: `Overview`, `MDM Overview`, `Neo4j Overview`, and `Mismatch Diagnostics`.
- Updated the overview metrics to show `MDM entities`, `MDM relationships`, `Snowflake graph nodes`, `Snowflake graph edges`, and `Pending sync`.
- Added hosted graph entity and relationship comparison tables using verifier-shaped rows.
- Added bounded mismatch tables for missing/extra nodes, missing/extra edges, and missing graph edge endpoints with `source -> target` direction values.
- Added failure-only Native App detail rendering with `Check`, `Status`, `Detail`, and `Remediation` columns.
- Kept healthy Native App proof out of primary dashboard chrome.
- Updated architecture guardrails for active UI copy, hosted graph helper usage, Snowflake table labels, and Native App failure rows.

## Task Commits

1. **Task 1: Update dashboard architecture/UI guardrails for hosted graph copy** - `6449fe6` (test)
2. **Task 2: Render hosted graph overview, comparison, and diagnostics** - `760e3f5` (feat)
3. **Task 3: Render Native App failures without noisy healthy proof** - `6cf132c` (test)

## Files Created/Modified

- `examples/mdm_graph_dashboard/streamlit_app.py` - Streamlit dashboard migrated to hosted graph helper payloads.
- `tests/architecture/test_dashboard_foundation_boundaries.py` - Guardrails for hosted graph copy, helper usage, table columns, and failure-only Native App detail.

## Verification

- RED check: `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` failed before migration with 8 expected failures from old external graph assumptions.
- `python3 -m py_compile examples/mdm_graph_dashboard/streamlit_app.py` passed.
- `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` passed: `24 passed`.
- `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py tests/mdm/test_graph_readonly.py -q` passed: `29 passed`.
- Active dashboard grep found no old external Neo4j/Bolt helper path, credential copy, subprocess/stdout usage, or disallowed Streamlit credential controls.

## Decisions Made

- Kept the `Neo4j Overview` route label for operator continuity, but changed active page/sidebar copy to Snowflake-hosted graph terminology.
- Removed the old dashboard-side relationship coverage builder from the hosted graph path; strict verifier-shaped relationship comparison now owns parity rows.
- Left Phase 4 requirements pending until Plan 04-03 updates the README/runbook and captures final dashboard verification evidence.

## Deviations from Plan

None - plan executed within the planned dashboard and architecture-test scope.

## Issues Encountered

- A legacy architecture assertion still banned the word `snowflake` in active dashboard text. It was narrowed to continue blocking generated AWS/Terraform application paths while allowing the required Snowflake-hosted graph copy.

## User Setup Required

None - no new external service configuration was added by this plan.

## Next Phase Readiness

Plan 04-03 can update dashboard documentation and final verification evidence. The dashboard implementation is ready for the docs plan to point operators at hosted `verify-graph`, Native App prerequisites, and AWS hosted graph E2E evidence.

## Self-Check: PASSED

- Summary created after all task commits.
- Plan-level verification passed.
- 04-03 remains the only incomplete Phase 4 plan.
