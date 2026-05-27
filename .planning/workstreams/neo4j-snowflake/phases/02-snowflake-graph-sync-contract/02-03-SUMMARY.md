---
phase: 02-snowflake-graph-sync-contract
plan: 03
subsystem: snowflake-graph-sync
tags: [snowflake, neo4j, mdm, cli, graph-sync, tdd]

requires:
  - phase: 02-02
    provides: Reusable Snowflake graph sync executor and shared Snowflake connection settings
provides:
  - `edgar-warehouse mdm sync-graph` wiring to Snowflake graph materialization
  - Credential-free CLI tests for Snowflake graph sync and load-relationships defaults
  - Explicit `load-relationships --graph-sync` opt-in for post-derivation graph materialization
affects:
  - Phase 3 hosted graph verification
  - AWS MDM e2e cutover from external Neo4j credentials

tech-stack:
  added: []
  patterns:
    - CLI handlers build narrow Snowflake graph sync configs and return secret-safe JSON payloads
    - `load-relationships` derives relationships by default and gates graph materialization behind `--graph-sync`

key-files:
  created:
    - tests/mdm/test_cli_snowflake_graph.py
    - .planning/workstreams/neo4j-snowflake/phases/02-snowflake-graph-sync-contract/02-03-SUMMARY.md
  modified:
    - edgar_warehouse/mdm/cli.py

key-decisions:
  - "`sync-graph` now uses `SnowflakeGraphSyncExecutor.from_env()` and no longer calls `_neo4j_client()`."
  - "`load-relationships` remains derivation-only by default; post-derivation graph materialization requires explicit `--graph-sync`."
  - "`--skip-graph-sync` remains accepted and forces the no-write path even if graph sync would otherwise be requested."

patterns-established:
  - "CLI JSON reports graph materialization counts, target database/schema, node/edge table names, and applied filters without printing credentials."
  - "Credential-free CLI tests monkeypatch executor/session/pipeline boundaries instead of opening live Snowflake, Neo4j, AWS, or MDM connections."

requirements-completed: [SYNC-01, SYNC-02, SYNC-03, SNOW-02, SNOW-04]

duration: 5min
completed: 2026-05-27
---

# Phase 2 Plan 03: Snowflake Graph Sync CLI Wiring Summary

**Existing MDM graph sync command now materializes Snowflake graph-ready state with credential-free CLI coverage**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-27T00:19:48Z
- **Completed:** 2026-05-27T00:24:12Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added CLI tests proving `sync-graph` forwards repeated relationship/entity filters, total row limit, per-type limit, and target/source schema overrides to the Snowflake graph sync executor.
- Replaced the `sync-graph` Neo4j Bolt dependency with `SnowflakeGraphSyncExecutor`, returning sorted JSON with materialized node/edge counts, target schema, table lists, and applied filters.
- Changed `load-relationships` so it derives relationships without graph writes by default and only constructs the Snowflake executor for explicit `--graph-sync`.
- Preserved `--skip-graph-sync` as an accepted no-write path and kept Phase 3-owned `verify-graph` behavior unchanged.

## Task Commits

Each TDD task was committed atomically:

1. **Task 1 RED: Add CLI tests for Snowflake sync-graph behavior** - `3b5418d` (test)
2. **Task 2 GREEN: Replace sync-graph Bolt dependency with Snowflake graph sync** - `314d9d2` (feat)

## Files Created/Modified

- `tests/mdm/test_cli_snowflake_graph.py` - Adds credential-free CLI behavior tests for Snowflake `sync-graph`, absent `NEO4J_*` credentials, default no-write relationship loading, `--skip-graph-sync`, and explicit `--graph-sync`.
- `edgar_warehouse/mdm/cli.py` - Wires `sync-graph` to `SnowflakeGraphSyncExecutor`, adds bounded entity filters and target overrides, and gates post-derivation graph materialization behind `load-relationships --graph-sync`.
- `.planning/workstreams/neo4j-snowflake/phases/02-snowflake-graph-sync-contract/02-03-SUMMARY.md` - Documents execution outcome and verification.

## Decisions Made

- `sync-graph` catches executor/configuration errors as nonzero CLI exits while avoiding external Neo4j credential checks.
- CLI output keeps backward-compatible `graph_nodes_synced` and `graph_edges_synced` fields alongside explicit `graph_nodes_materialized` and `graph_edges_materialized` fields.
- `load-relationships --skip-graph-sync` wins as a no-write path, preserving operator repair safety.

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

None - the CLI target override, credential, and unbounded execution surfaces were covered by the plan threat model and mitigated with narrow arguments, executor validation, credential-free tests, and bounded filters.

## Verification

- Task 1 RED: `uv run pytest tests/mdm/test_cli_snowflake_graph.py -q` failed before implementation with unrecognized `sync-graph`/`load-relationships` flags and missing `graph_sync` output.
- Task 2 GREEN: `uv run pytest tests/mdm/test_cli_snowflake_graph.py -q` passed: `4 passed in 1.41s`.
- Final focused verification: `uv run pytest tests/mdm/test_cli_snowflake_graph.py tests/mdm/test_snowflake_graph_migration.py tests/mdm/test_export.py tests/mdm/test_pipeline_relationships.py -q` passed: `42 passed in 3.08s`.
- Whitespace check: `git diff --check` passed.

## Self-Check: PASSED

- Found `edgar_warehouse/mdm/cli.py`.
- Found `tests/mdm/test_cli_snowflake_graph.py`.
- Found task commit `3b5418d`.
- Found task commit `314d9d2`.
- Required summary file exists.

## Next Phase Readiness

Phase 2 is complete. Phase 3 can move hosted `verify-graph` and AWS MDM e2e validation onto the Snowflake-hosted Native App path without depending on external `NEO4J_*` credentials for graph sync.

---
*Phase: 02-snowflake-graph-sync-contract*
*Completed: 2026-05-27*
