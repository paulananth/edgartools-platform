---
phase: 02-snowflake-graph-sync-contract
plan: 01
subsystem: snowflake-graph-sync
tags: [snowflake, neo4j, mdm, graph-projection, sql-generation]

requires:
  - phase: 01-02
    provides: Accepted Snowflake Native App graph target architecture decision
  - phase: 01-03
    provides: MDM graph projection contract and Phase 2 implementation checklist
provides:
  - Snowflake SQL renderer for canonical `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES`
  - Native App-compatible `GRAPH_NODE_*` and `GRAPH_EDGE_*` projection views
  - Credential-free tests for graph projection naming, metadata, validation, and governed output guidance
affects:
  - Phase 2 Plan 02 Snowflake graph sync executor
  - Phase 2 Plan 03 `edgar-warehouse mdm sync-graph` CLI wiring
  - Phase 3 hosted graph verification

tech-stack:
  added: []
  patterns:
    - Credential-free generated SQL contract tests
    - Canonical graph tables with compatibility projections

key-files:
  created:
    - .planning/workstreams/neo4j-snowflake/phases/02-snowflake-graph-sync-contract/02-01-SUMMARY.md
  modified:
    - edgar_warehouse/mdm/snowflake_graph.py
    - tests/mdm/test_snowflake_graph_migration.py

key-decisions:
  - "Use uppercase unquoted Snowflake identifiers `NODEID`, `SOURCENODEID`, and `TARGETNODEID` for compatibility with the live operator convention."
  - "Materialize `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES` as canonical tables, with `GRAPH_NODES`/`GRAPH_EDGES` retained as compatibility views."
  - "Expose `GRAPH_NODE_*` and `GRAPH_EDGE_*` as per-label and per-relationship projection views over the canonical tables."

patterns-established:
  - "Generated graph SQL remains deterministic and idempotent through `CREATE OR REPLACE` statements."
  - "Generated artifacts avoid external Neo4j credential dependencies and do not invoke Native App procedures during SQL generation."

requirements-completed: [SYNC-01, SYNC-02, SNOW-02, SNOW-04]

duration: 5min
completed: 2026-05-27
---

# Phase 2 Plan 01: Snowflake Graph Projection SQL Contract Summary

**Canonical MDM graph tables and Native App projection views rendered as credential-free Snowflake SQL**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-27T00:02:31Z
- **Completed:** 2026-05-27T00:07:25Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added a credential-free regression test that locks the Phase 2 graph projection contract around `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION`, `MDM_GRAPH_NODES`, `MDM_GRAPH_EDGES`, `GRAPH_NODE_*`, and `GRAPH_EDGE_*`.
- Updated `render_graph_tables` to create canonical node and edge graph tables from active MDM entities and relationships, preserving stable ids, labels/types, source metadata, timestamps, properties, and graph sync status.
- Added per-label and per-relationship Native App projection views while keeping `GRAPH_NODES` and `GRAPH_EDGES` as compatibility views over the canonical tables.
- Updated validation SQL for node counts, edge counts, active MDM relationship parity, and missing endpoint diagnostics.
- Updated generated README text to state that `NEO4J_GRAPH_ANALYTICS.GRAPH.*` procedures consume the generated tables but are not invoked by this SQL generation step, and that algorithm output tables require governed operator cleanup.

## Task Commits

Each task was committed atomically:

1. **Task 1: Lock the projection contract in SQL generation tests** - `c083a1c` (test)
2. **Task 2: Render idempotent Snowflake graph projection SQL** - `7da9cce` (feat)

## Files Created/Modified

- `tests/mdm/test_snowflake_graph_migration.py` - Added RED contract assertions for graph table naming, stable identifiers, metadata, sync status, validation text, README guidance, and no external Neo4j credential requirements.
- `edgar_warehouse/mdm/snowflake_graph.py` - Renders canonical graph tables, compatibility views, Native App projections, validation diagnostics, and governed output guidance.
- `.planning/workstreams/neo4j-snowflake/phases/02-snowflake-graph-sync-contract/02-01-SUMMARY.md` - Documents execution outcome and verification.

## Decisions Made

- Physical `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES` tables are the canonical Phase 2 SQL contract for this plan.
- `GRAPH_NODE_COMPANY`, `GRAPH_NODE_PERSON`, `GRAPH_NODE_SECURITY`, `GRAPH_NODE_ADVISER`, `GRAPH_NODE_FUND`, and seeded `GRAPH_EDGE_*` names are views over canonical tables.
- `GRAPH_SYNC_STATUS` is derived from `mdm_relationship_instance.graph_synced_at` as `PENDING` or `SYNCED`; later executor plans can decide whether to update that watermark during live materialization.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

None.

## Authentication Gates

None.

## Known Stubs

None.

## Verification

- RED gate: `uv run pytest tests/mdm/test_snowflake_graph_migration.py -q` failed before implementation with missing `MDM_GRAPH_NODES`.
- GREEN gate: `uv run pytest tests/mdm/test_snowflake_graph_migration.py -q` passed after implementation: `4 passed in 0.05s`.
- Final focused verification: `uv run pytest tests/mdm/test_snowflake_graph_migration.py -q` passed: `4 passed in 0.05s`.
- Whitespace check: `git diff --check` passed.

## Self-Check: PASSED

- Found `edgar_warehouse/mdm/snowflake_graph.py`.
- Found `tests/mdm/test_snowflake_graph_migration.py`.
- Found task commit `c083a1c`.
- Found task commit `7da9cce`.
- Required summary file exists.

## Next Phase Readiness

Plan 02-02 can build the reusable Snowflake graph sync executor against the SQL contract established here. Live Snowflake execution remains intentionally out of scope for this plan; no live credentials were used.

---
*Phase: 02-snowflake-graph-sync-contract*
*Completed: 2026-05-27*
