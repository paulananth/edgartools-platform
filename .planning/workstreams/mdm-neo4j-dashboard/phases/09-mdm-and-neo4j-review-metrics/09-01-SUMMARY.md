---
phase: 09-mdm-and-neo4j-review-metrics
plan: 01
subsystem: mdm-dashboard
tags: [python, sqlalchemy, pytest, mdm, dashboard, read-only]
requires:
  - phase: 08-dashboard-foundations-and-read-only-data-access
    provides: Read-only dashboard helper shape and credential-free test pattern
provides:
  - Structured MDM entity and relationship dashboard metrics
  - Bounded pending graph-sync samples without raw relationship properties
  - Bounded active relationship diagnostic inputs for Neo4j coverage checks
  - Relationship coverage row computation for missing and extra graph data
affects: [09-02, 09-03, mdm-neo4j-dashboard]
tech-stack:
  added: []
  patterns:
    - Frozen dataclass results with as_dict() for Streamlit consumption
    - SQLAlchemy SELECT-only helper functions with injected session support
    - Fixed-copy unavailable payloads for secret-safe dashboard failures
key-files:
  created:
    - .planning/workstreams/mdm-neo4j-dashboard/phases/09-mdm-and-neo4j-review-metrics/09-01-SUMMARY.md
  modified:
    - edgar_warehouse/mdm/dashboard_readonly.py
    - tests/mdm/test_dashboard_readonly.py
key-decisions:
  - "Kept MDM dashboard reads in dashboard_readonly.py instead of calling CLI or graph sync surfaces."
  - "Used active MdmRelationshipType rows as the relationship metric driver so zero-row registered types still render."
  - "Returned fixed unavailable copy and env var names only on failures."
patterns-established:
  - "MDM relationship diagnostics return candidate_rows plus known_mdm_edge_keys grouped by relationship type."
  - "Dashboard sample helpers clamp per-type and global limits before SQL query construction."
requirements-completed: [MDM-01, MDM-02, MDM-03, GRAPH-02]
duration: 6min
completed: 2026-05-21
---

# Phase 09 Plan 01: MDM Metrics Helper Summary

**Read-only MDM dashboard metrics with bounded relationship diagnostics and secret-safe failure payloads**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-21T00:34:30Z
- **Completed:** 2026-05-21T00:39:32Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added failing TDD coverage for all five MDM entity domains, active relationship type counts, pending graph-sync samples, diagnostic inputs, coverage row math, warning safety, and no-commit behavior.
- Implemented structured MDM metrics dataclasses and helper functions in `edgar_warehouse/mdm/dashboard_readonly.py`.
- Preserved the read-only boundary: helpers use SQLAlchemy SELECT queries, injected sessions, fixed unavailable copy, and no pipeline/sync/migration imports.

## Task Commits

1. **Task 1: Add MDM metric and pending-sample tests** - `fbe745c` (test)
2. **Task 2: Implement structured MDM metrics helpers** - `3af7ca0` (feat)

## Files Created/Modified

- `tests/mdm/test_dashboard_readonly.py` - Phase 9 tests and local MDM seed helpers for entity counts, relationship counts, bounded samples, warnings, and no commits.
- `edgar_warehouse/mdm/dashboard_readonly.py` - MDM metric dataclasses, `get_mdm_dashboard_metrics`, `get_active_relationship_diagnostic_inputs`, and `build_relationship_coverage_rows`.
- `.planning/workstreams/mdm-neo4j-dashboard/phases/09-mdm-and-neo4j-review-metrics/09-01-SUMMARY.md` - Execution record for this plan.

## Verification

- `uv run pytest tests/mdm/test_dashboard_readonly.py -q` failed during RED as expected: 7 new tests failed on missing helper identifiers.
- `uv run pytest tests/mdm/test_dashboard_readonly.py -q` passed after implementation: 14 passed.
- `uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q` passed: 27 passed.
- Static blocked-token scan for `dashboard_readonly.py` returned no mutation/import boundary hits.

## Decisions Made

- Relationship metrics are keyed by active registered relationship type and include zero active-row types.
- Diagnostic samples expose source/target IDs, cheap names, timestamps, and stable `(relationship_type, source_entity_id, target_entity_id)` keys only.
- Empty result collections appear only in unavailable payloads or no-row states; they are not UI placeholder stubs.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. Stub scan found intentional empty unavailable/no-row payload fields, not unimplemented UI or mock data.

## Threat Flags

None. This plan added no endpoints, auth paths, file access, schema changes, or new network surfaces.

## TDD Gate Compliance

- RED gate: `fbe745c` added failing tests before implementation.
- GREEN gate: `3af7ca0` implemented the helper API and made the focused tests pass.
- Refactor gate: not needed.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 09-02 can consume `get_active_relationship_diagnostic_inputs()` for missing-edge and extra-graph diagnostics without querying SQL directly.

## Self-Check: PASSED

- Summary file exists at `.planning/workstreams/mdm-neo4j-dashboard/phases/09-mdm-and-neo4j-review-metrics/09-01-SUMMARY.md`.
- Task commit `fbe745c` exists in git history.
- Task commit `3af7ca0` exists in git history.
- `.planning/active-workstream` remains unstaged and untouched by this plan.

---
*Phase: 09-mdm-and-neo4j-review-metrics*
*Completed: 2026-05-21*
