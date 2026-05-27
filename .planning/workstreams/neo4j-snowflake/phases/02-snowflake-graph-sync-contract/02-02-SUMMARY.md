---
phase: 02-snowflake-graph-sync-contract
plan: 02
subsystem: snowflake-graph-sync
tags: [snowflake, neo4j, mdm, graph-sync, executor, tdd]

requires:
  - phase: 02-01
    provides: Canonical Snowflake graph projection SQL contract
provides:
  - Shared Snowflake connection settings for MDM export and graph sync
  - Credential-free Snowflake graph sync executor with fail-closed filter validation
  - Bounded graph materialization SQL for entity types, relationship types, global limit, and per-type limit
affects:
  - Phase 2 Plan 03 `edgar-warehouse mdm sync-graph` CLI wiring
  - Phase 3 hosted graph verification

tech-stack:
  added: []
  patterns:
    - Shared environment-backed Snowflake connector settings
    - Fake cursor/connection tests for Snowflake execution behavior
    - Fail-closed SQL filter validation before materialization

key-files:
  created:
    - .planning/workstreams/neo4j-snowflake/phases/02-snowflake-graph-sync-contract/02-02-SUMMARY.md
  modified:
    - edgar_warehouse/mdm/export.py
    - edgar_warehouse/mdm/snowflake_graph.py
    - tests/mdm/test_export.py
    - tests/mdm/test_snowflake_graph_migration.py

key-decisions:
  - "Reuse existing `MDM_SNOWFLAKE_*` and `DBT_SNOWFLAKE_*` settings for graph sync instead of adding any `NEO4J_*` credential path."
  - "Validate entity and relationship filters against fixed allowed values before acquiring a cursor or executing Snowflake SQL."
  - "Keep graph materialization deterministic through `CREATE OR REPLACE` graph tables and stable `GRAPH_NODE_*` / `GRAPH_EDGE_*` views."

patterns-established:
  - "Snowflake graph sync tests use fake connections and assert SQL text/order without live credentials."
  - "Executor result payloads include target schema, applied filters, table names, and node/edge counts for operator logs."

requirements-completed: [SYNC-01, SYNC-02, SYNC-03, SNOW-02, SNOW-04]

duration: 6min
completed: 2026-05-27
---

# Phase 2 Plan 02: Snowflake Graph Sync Executor Summary

**Reusable Snowflake graph sync executor with shared connection settings and fail-closed bounded filters**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-27T00:10:36Z
- **Completed:** 2026-05-27T00:16:25Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Extracted `SnowflakeConnectionSettings` from `SnowflakeConnectorWriter.from_env()` so graph sync can reuse the existing `MDM_SNOWFLAKE_*` / `DBT_SNOWFLAKE_*` connection model without duplicating environment parsing.
- Added `SnowflakeGraphSyncConfig`, `SnowflakeGraphSyncResult`, `SnowflakeGraphValidationError`, and `SnowflakeGraphSyncExecutor` for credential-free graph materialization over a connector-style connection.
- Added fail-closed validation for entity filters (`adviser`, `company`, `fund`, `person`, `security`) and seeded relationship filters before any Snowflake cursor execution.
- Added deterministic bounded materialization SQL for entity type, relationship type, global `limit`, and `limit_per_type`, while preserving `MDM_GRAPH_NODES`, `MDM_GRAPH_EDGES`, `GRAPH_NODE_*`, `GRAPH_EDGE_*`, `NODEID`, `SOURCENODEID`, and `TARGETNODEID`.

## Task Commits

Each TDD task was committed through RED and GREEN gates:

1. **Task 1 RED: Shared Snowflake settings tests** - `25a6a7f` (test)
2. **Task 1 GREEN: Shared Snowflake settings implementation** - `d3c41be` (feat)
3. **Task 2 RED: Graph sync executor tests** - `7add35a` (test)
4. **Task 2 GREEN: Graph sync executor implementation** - `9faf57e` (feat)

## Files Created/Modified

- `edgar_warehouse/mdm/export.py` - Adds reusable Snowflake connection settings/factory while preserving writer merge behavior.
- `edgar_warehouse/mdm/snowflake_graph.py` - Adds graph sync config/result/executor, filter validation, count result collection, and bounded SQL generation.
- `tests/mdm/test_export.py` - Covers settings extraction, DBT fallbacks, error names, and unchanged merge SQL behavior.
- `tests/mdm/test_snowflake_graph_migration.py` - Covers executor SQL contract, bounded filters, result payloads, validation errors, and zero execution on invalid filters.
- `.planning/workstreams/neo4j-snowflake/phases/02-snowflake-graph-sync-contract/02-02-SUMMARY.md` - Documents execution outcome and verification.

## Decisions Made

- `SnowflakeGraphSyncExecutor.from_env()` uses `SnowflakeConnectionSettings.from_env()` and does not introduce a new secret-management path.
- Unknown entity or relationship filters raise `SnowflakeGraphValidationError` before cursor creation or `execute()` calls.
- The executor returns counts from `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES` after materialization so the later CLI can log concrete sync results.

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

## Threat Flags

None - the new Snowflake connection and SQL mutation surfaces were already covered by the plan threat model and mitigated through shared settings plus fail-closed filter validation.

## Verification

- Task 1 RED: `uv run pytest tests/mdm/test_export.py -q` failed before implementation with missing `SnowflakeConnectionSettings`.
- Task 1 GREEN: `uv run pytest tests/mdm/test_export.py -q` passed after implementation: `4 passed in 0.05s`.
- Task 2 RED: `uv run pytest tests/mdm/test_snowflake_graph_migration.py -q` failed before implementation with missing graph sync executor types.
- Task 2 GREEN: `uv run pytest tests/mdm/test_snowflake_graph_migration.py tests/mdm/test_export.py -q` passed after implementation: `11 passed in 0.36s`.
- Final focused verification: `uv run pytest tests/mdm/test_snowflake_graph_migration.py tests/mdm/test_export.py -q` passed: `11 passed in 0.09s`.
- Whitespace check: `git diff --check` passed.
- Credential-free check: `rg "snowflake\\.connector" tests/mdm/test_snowflake_graph_migration.py edgar_warehouse/mdm/snowflake_graph.py` returned no matches.

## Self-Check: PASSED

- Found `edgar_warehouse/mdm/export.py`.
- Found `edgar_warehouse/mdm/snowflake_graph.py`.
- Found `tests/mdm/test_export.py`.
- Found `tests/mdm/test_snowflake_graph_migration.py`.
- Found task commit `25a6a7f`.
- Found task commit `d3c41be`.
- Found task commit `7add35a`.
- Found task commit `9faf57e`.
- Required summary file exists.

## Next Phase Readiness

Plan 02-03 can wire `edgar-warehouse mdm sync-graph` to `SnowflakeGraphSyncExecutor` and surface the result payload through CLI/operator logs. Live Snowflake execution remains intentionally out of scope for this plan; no live credentials were used.

---
*Phase: 02-snowflake-graph-sync-contract*
*Completed: 2026-05-27*
