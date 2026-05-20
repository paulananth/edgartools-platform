---
phase: 08-dashboard-foundations-and-read-only-data-access
plan: 02
subsystem: mdm
tags: [neo4j, dashboard, readonly, pytest]
requires: []
provides:
  - Optional Neo4j review-only status and smoke-query helpers.
  - Credential-free fake-client tests for Neo4j config, query, and secret-safe failure states.
affects: [phase-08, dashboard, neo4j]
tech-stack:
  added: []
  patterns: [structured review status, static Cypher smoke query, optional graph startup]
key-files:
  created:
    - edgar_warehouse/mdm/graph_readonly.py
    - tests/mdm/test_graph_readonly.py
  modified: []
key-decisions:
  - "Neo4j absence is non-blocking and returns not_configured status for the dashboard."
  - "Phase 8 Neo4j smoke checks use only static RETURN 1 AS ok Cypher."
patterns-established:
  - "Neo4j dashboard helpers return structured status without exposing raw env values or driver exceptions."
  - "Graph review helpers reuse Neo4jGraphClient construction without importing graph sync or merge paths."
requirements-completed: [DASH-03, ISO-02]
duration: 5min
completed: 2026-05-17
---

# Phase 08: Dashboard Foundations And Read-Only Data Access - Plan 02 Summary

**Optional Neo4j review-only dashboard boundary with static smoke-query verification**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-17T22:40:24Z
- **Completed:** 2026-05-17T22:45:12Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added fake-client tests covering optional Neo4j startup, env compatibility, static read-only Cypher, owned-client cleanup, and secret-safe failures.
- Added `Neo4jReviewStatus`, `load_neo4j_review_client`, `check_neo4j_status`, and `run_neo4j_smoke_query`.
- Preserved existing `NEO4J_URI`, `NEO4J_USER`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, and `NEO4J_SECRET_JSON` conventions while keeping returned status payloads secret-safe.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define fake-client Neo4j read-only helper tests** - `e3e49ff` (test)
2. **Task 2: Implement Neo4j review-only helpers** - `528db50` (feat)

## Files Created/Modified

- `tests/mdm/test_graph_readonly.py` - Verifies optional config behavior, static smoke query, safe failures, and no graph sync/write surfaces.
- `edgar_warehouse/mdm/graph_readonly.py` - Provides structured Neo4j review status helpers using `Neo4jGraphClient` construction conventions.

## Decisions Made

- Neo4j connectivity is optional for Phase 8 dashboard startup.
- `neo4j://` URIs are normalized to `bolt://` to match existing CLI behavior.
- Phase 8 graph checks intentionally avoid labels, relationship types, and user-supplied Cypher.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

None.

## Verification

- `uv run --with pytest pytest tests/mdm/test_graph_readonly.py -q` - 8 passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The Streamlit shell can show Neo4j configured, connected, not configured, or query failed states without invoking graph sync, merge, backfill, or write-oriented APIs.

## Self-Check: PASSED

- All planned public identifiers exist.
- Focused tests pass without live Neo4j credentials.
- Helper code uses only static `RETURN 1 AS ok` and avoids graph mutation surfaces.

---
*Phase: 08-dashboard-foundations-and-read-only-data-access*
*Completed: 2026-05-17*
