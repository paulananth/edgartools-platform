---
phase: 09-mdm-and-neo4j-review-metrics
plan: 02
subsystem: mdm-dashboard
tags: [python, pytest, mdm, neo4j, dashboard, read-only]
requires:
  - phase: 09-mdm-and-neo4j-review-metrics
    plan: 01
    provides: Bounded MDM relationship diagnostic inputs
provides:
  - Structured Neo4j node and relationship graph metrics
  - Registry-validated dynamic Cypher identifier checks
  - Bounded missing-edge and extra-graph diagnostic sample helpers
  - Secret-safe Neo4j unavailable and query-failed graph metric payloads
affects: [09-03, mdm-neo4j-dashboard]
tech-stack:
  added: []
  patterns:
    - Frozen dataclass results with as_dict() for dashboard consumption
    - Fake Neo4j client/session tests with captured Cypher calls
    - Read-only Cypher limited to MATCH and RETURN query shapes
key-files:
  created:
    - .planning/workstreams/mdm-neo4j-dashboard/phases/09-mdm-and-neo4j-review-metrics/09-02-SUMMARY.md
  modified:
    - edgar_warehouse/mdm/graph_readonly.py
    - tests/mdm/test_graph_readonly.py
key-decisions:
  - "Kept Neo4j graph metrics in graph_readonly.py and avoided graph sync, merge, backfill, and CLI mutation imports."
  - "Validated every dynamic Neo4j label and relationship type with an alpha-leading alphanumeric/underscore allowlist before interpolation."
  - "Returned only operator-readable identifiers and names for graph diagnostic samples."
patterns-established:
  - "Graph metric helpers consume Plan 09-01 diagnostic inputs: candidate_rows and known_mdm_edge_keys."
  - "Missing-edge checks are bounded by candidate rows and requested limit before issuing Cypher."
requirements-completed: [GRAPH-01, GRAPH-03]
duration: 5min
completed: 2026-05-21
---

# Phase 09 Plan 02: Neo4j Graph Metrics Helper Summary

**Read-only Neo4j node and relationship metrics with bounded graph diagnostics**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-21T09:52:49Z
- **Completed:** 2026-05-21T09:57:48Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added TDD coverage for Neo4j node counts, relationship counts, unsafe identifier rejection, secret-safe unavailable states, bounded missing-edge checks, bounded extra-graph samples, and no write Cypher.
- Implemented `get_neo4j_graph_metrics`, `find_missing_edge_samples`, and `find_extra_graph_samples` in `edgar_warehouse/mdm/graph_readonly.py`.
- Preserved the dashboard read-only boundary: no sync engine imports, no merge/backfill helpers, no mutation controls, and no raw property dictionaries in diagnostic samples.

## Task Commits

1. **Task 1: Add Neo4j graph metric and bounded-Cypher tests** - `d4879e9` (test)
2. **Task 2: Implement registry-validated Neo4j metric helpers** - `f9b003f` (feat)

## Files Created/Modified

- `tests/mdm/test_graph_readonly.py` - Fake-client tests for graph counts, Cypher validation, unavailable states, bounded missing-edge checks, bounded extra samples, and read-only query assertions.
- `edgar_warehouse/mdm/graph_readonly.py` - Graph metric dataclasses, registry identifier validation, Neo4j graph count helpers, bounded missing-edge checks, and bounded extra-graph sample helpers.
- `.planning/workstreams/mdm-neo4j-dashboard/phases/09-mdm-and-neo4j-review-metrics/09-02-SUMMARY.md` - Execution record for this plan.

## Verification

- `uv run pytest tests/mdm/test_graph_readonly.py -q` failed during RED as expected: 6 new tests failed on missing helper identifiers.
- `uv run pytest tests/mdm/test_graph_readonly.py -q` passed after implementation: 14 passed.
- `uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q` passed: 33 passed.
- Static blocked-token scan for `graph_readonly.py` returned no sync imports or write Cypher tokens.

## Decisions Made

- Invalid labels and relationship types return an unavailable `invalid_identifier` metrics payload for aggregate metrics and an empty sample list for direct diagnostic helpers, with no Cypher issued.
- Missing-edge diagnostics check only the bounded supplied MDM candidate rows, using source and target `entity_id` parameters.
- Extra-graph diagnostics query Neo4j for bounded readable edge rows, filter out supplied MDM keys locally, and omit raw property payloads.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. Stub scan found no placeholder markers or unimplemented data paths in the files modified by this plan.

## Threat Flags

None. The new Neo4j read surface was included in the plan threat model and mitigated with identifier validation, read-only Cypher, safe failure copy, and bounded diagnostic loops.

## TDD Gate Compliance

- RED gate: `d4879e9` added failing tests before implementation.
- GREEN gate: `f9b003f` implemented the helper API and made the focused tests pass.
- Refactor gate: not needed.

## Issues Encountered

None.

## User Setup Required

None - no external Neo4j credentials are required for the fake-client test coverage.

## Next Phase Readiness

Plan 09-03 can consume `Neo4jGraphMetrics.as_dict()` for Neo4j Overview and Graph Coverage rendering, including `node_counts`, `relationship_counts`, `missing_edge_samples`, `extra_graph_samples`, and warnings.

## Self-Check: PASSED

- Summary file exists at `.planning/workstreams/mdm-neo4j-dashboard/phases/09-mdm-and-neo4j-review-metrics/09-02-SUMMARY.md`.
- Task commit `d4879e9` exists in git history.
- Task commit `f9b003f` exists in git history.
- `.planning/active-workstream` and `.planning/workstreams/pipeline-scaling/` remain unstaged by this plan.

---
*Phase: 09-mdm-and-neo4j-review-metrics*
*Completed: 2026-05-21*
