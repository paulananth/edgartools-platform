---
phase: 05-node-and-populated-relationship-graph-parity
plan: 01
subsystem: mdm
tags: [mdm, graph, snowflake, node-parity, idempotency, pytest]

# Dependency graph
requires: []
provides:
  - "GRAPH_NODE_AUDITFIRM view emitted by render_graph_tables(), closing the NODE-06 declared-but-absent view gap"
  - "Committed graph-sync (full-rebuild) idempotency regression test satisfying the sync half of GVER-03"
affects: [05-02, 05-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-entity-type GRAPH_NODE_* view: CREATE OR REPLACE VIEW selecting the fixed 8-column list from MDM_GRAPH_NODES, filtered WHERE ENTITY_TYPE = '<type>'"
    - "Graph-sync idempotency proof: two independent FakeGraphConnection runs of SnowflakeGraphSyncExecutor.sync compared for byte-identical executed-SQL sequences and stable node_count/edge_count, with a leading-verb allowlist (CREATE/SELECT/--) proving full-rebuild semantics (no INSERT/MERGE/UPDATE/DELETE)"

key-files:
  created: []
  modified:
    - edgar_warehouse/mdm/snowflake_graph.py
    - tests/mdm/test_snowflake_graph_migration.py

key-decisions:
  - "Used 'mdm' extra (not just 's3'+'snowflake') for uv sync/pytest invocations because tests/mdm/conftest.py imports sqlalchemy, which only the mdm/mdm-runtime extras provide — the plan's literal verify command omitted it."
  - "test_graph_sync_is_idempotent_full_rebuild passed on first run (not RED then GREEN) because it proves already-correct structural idempotency (CREATE OR REPLACE full rebuild, no mutable state) rather than fixing a bug — consistent with the plan's own framing of graph-sync idempotency as 'structural by construction'."

patterns-established:
  - "New per-type node/edge views land immediately after their nearest sibling view block, preserving single-line-per-view formatting for minimal diffs."

requirements-completed: [NODE-06, GVER-03]

coverage:
  - id: D1
    description: "render_graph_tables() emits a GRAPH_NODE_AUDITFIRM view identical in shape to the five existing per-type node views, filtered on ENTITY_TYPE = 'audit_firm'"
    requirement: "NODE-06"
    verification:
      - kind: unit
        ref: "tests/mdm/test_snowflake_graph_migration.py::test_generated_sql_exposes_phase_2_graph_projection_contract"
        status: pass
    human_judgment: false
  - id: D2
    description: "Graph-sync (full-rebuild) idempotency is proven by a committed regression test: two sync() runs against unchanged config produce identical SQL and stable node/edge counts, with no row-level accumulation verbs"
    requirement: "GVER-03"
    verification:
      - kind: unit
        ref: "tests/mdm/test_snowflake_graph_migration.py::test_graph_sync_is_idempotent_full_rebuild"
        status: pass
    human_judgment: false

# Metrics
duration: 20min
completed: 2026-07-08
status: complete
---

# Phase 5 Plan 1: GRAPH_NODE_AUDITFIRM View Emission and Graph-Sync Idempotency Summary

**Closed the NODE-06 GRAPH_NODE_AUDITFIRM view gap in render_graph_tables() and added a committed regression test proving graph-sync full-rebuild idempotency (GVER-03, sync side).**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-08T06:09:07Z
- **Completed:** 2026-07-08 (same session)
- **Tasks:** 2/2 completed
- **Files modified:** 2

## Accomplishments
- `render_graph_tables()` now emits a `GRAPH_NODE_AUDITFIRM` view matching the shape of the five existing per-type node views (`GRAPH_NODE_COMPANY`, `_PERSON`, `_SECURITY`, `_ADVISER`, `_FUND`), filtered `WHERE ENTITY_TYPE = 'audit_firm'`.
- `test_generated_sql_exposes_phase_2_graph_projection_contract` now asserts `GRAPH_NODE_AUDITFIRM` is present in generated graph SQL alongside the other five node views, plus a focused assertion on the `ENTITY_TYPE = 'audit_firm'` WHERE clause.
- New `test_graph_sync_is_idempotent_full_rebuild` proves two independent `SnowflakeGraphSyncExecutor.sync()` runs against the same `SnowflakeGraphSyncConfig` produce byte-identical executed-SQL sequences, equal `node_count`/`edge_count`, and exclusively `CREATE`/`SELECT`/comment statements (no `INSERT`/`MERGE`/`UPDATE`/`DELETE`) — satisfying GVER-03's sync-side committed-regression requirement (replacing the earlier ad-hoc manual live verification per D-04/D-05).
- Full `tests/mdm/test_snowflake_graph_migration.py` suite passes (10/10), with zero live Snowflake/AWS connections used anywhere in the file.

## Task Commits

Each task was committed atomically (TDD RED/GREEN split for Task 1; single commit for Task 2, see Decisions):

1. **Task 1 (RED): failing test for GRAPH_NODE_AUDITFIRM view** - `899b875` (test)
2. **Task 1 (GREEN): emit GRAPH_NODE_AUDITFIRM view in render_graph_tables()** - `3e23ba1` (feat)
3. **Task 2: graph-sync full-rebuild idempotency regression test** - `4be1123` (test)

## Files Created/Modified
- `edgar_warehouse/mdm/snowflake_graph.py` - Added `CREATE OR REPLACE VIEW ... GRAPH_NODE_AUDITFIRM` block immediately after `GRAPH_NODE_FUND`, identical column list/structure to sibling views, `WHERE ENTITY_TYPE = 'audit_firm'`.
- `tests/mdm/test_snowflake_graph_migration.py` - Added `GRAPH_NODE_AUDITFIRM` to the per-type view membership loop + WHERE-clause assertion; added `test_graph_sync_is_idempotent_full_rebuild`.

## Decisions Made
- **Environment fix (Rule 3):** The plan's literal verify command (`uv run --extra s3 --extra snowflake pytest ...`) failed with `ModuleNotFoundError: No module named 'sqlalchemy'` because `tests/mdm/conftest.py` imports sqlalchemy, which is only provided by the `mdm`/`mdm-runtime` extras, not `s3`/`snowflake`. Added `--extra mdm` to all `uv run`/`uv sync` invocations for this plan. No source or test logic was changed to work around this — it's purely an invocation-flag fix.
- **Broken venv repair (Rule 3):** The pre-existing `.venv` had a corrupted `lib64` symlink (Windows/POSIX venv mismatch) causing `uv sync` to fail with `Access is denied`. Removed `.venv` and let `uv sync` recreate it cleanly. No project files affected.
- **Test-ordering nuance for Task 2:** `test_graph_sync_is_idempotent_full_rebuild` passed on its very first run rather than following a strict fail-then-pass TDD cycle, because it's a regression test proving already-correct structural behavior (full-rebuild `CREATE OR REPLACE`, no accumulating state) rather than a bugfix — exactly as the plan's own read_first pointer at `snowflake_graph.py:128` frames it ("graph-sync side is structural idempotency by construction"). This is consistent with the TDD fail-fast guard, which applies to bug-driven RED/GREEN cycles, not proof-of-existing-correctness regression tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing `mdm` extra for pytest/uv invocations**
- **Found during:** Task 1 (first RED test run)
- **Issue:** `tests/mdm/conftest.py` imports `sqlalchemy`, not installed by the plan's specified `--extra s3 --extra snowflake` flags.
- **Fix:** Added `--extra mdm` to all `uv sync`/`uv run` commands for this plan's verification.
- **Files modified:** None (invocation-only, no repo files changed).
- **Verification:** `uv run --extra s3 --extra snowflake --extra mdm pytest tests/mdm/test_snowflake_graph_migration.py -q` passes.
- **Committed in:** N/A (not a code change; documented here per deviation tracking).

**2. [Rule 3 - Blocking] Corrupted local `.venv` blocked `uv sync`**
- **Found during:** Pre-Task-1 environment setup
- **Issue:** `.venv/lib64` was a dangling/inaccessible symlink causing `uv sync` to fail with `Access is denied (os error 5)` on Windows.
- **Fix:** Removed `.venv` directory; `uv sync` recreated it cleanly from `uv.lock`.
- **Files modified:** None (local venv only, not tracked in git).
- **Verification:** Subsequent `uv sync --extra s3 --extra snowflake --extra mdm` succeeded; tests ran.
- **Committed in:** N/A (no repo files changed).

---

**Total deviations:** 2 auto-fixed (both Rule 3, blocking, environment/invocation-only — no source or test logic changes beyond what the plan specified)
**Impact on plan:** Both fixes were necessary to run the plan's own verification commands; neither changed scope, added functionality, or touched application/test code beyond the plan's specified tasks.

## Issues Encountered
None beyond the two environment deviations documented above, both resolved without touching plan-scoped files.

## User Setup Required
None - no external service configuration required. All verification used `FakeGraphConnection`/`FakeGraphCursor` mocks; no live Snowflake or AWS connection was made.

## Next Phase Readiness
- `GRAPH_NODE_AUDITFIRM` view now exists, unblocking Plan 03's NODE-06 per-type parity check (which needs the view to exist before it can assert parity against it).
- Graph-sync idempotency is now a committed, automated regression test rather than an undocumented manual observation — Plan 03's GVER-03 work can build on this sync-side proof rather than re-deriving it.
- No blockers identified for Plans 02/03.

---
*Phase: 05-node-and-populated-relationship-graph-parity*
*Completed: 2026-07-08*
