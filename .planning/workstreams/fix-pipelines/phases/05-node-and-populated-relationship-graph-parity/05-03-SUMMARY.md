---
phase: 05-node-and-populated-relationship-graph-parity
plan: 03
subsystem: mdm
tags: [mdm, graph, snowflake, verify-graph, node-parity, edge-parity, cli]

# Dependency graph
requires:
  - phase: 05-node-and-populated-relationship-graph-parity/05-01
    provides: "GRAPH_NODE_AUDITFIRM view emitted by render_graph_tables(), closing the NODE-06 declared-but-absent view gap"
provides:
  - "verify-graph named_checks.node_parity: one named parity check per expected node type (adviser, audit_firm, company, fund, person, security), folded into the passed/exit-code gate (NODE-01..06)"
  - "verify-graph named_checks.relationship_parity: one named parity check per already-populated relationship type (COMPANY_HOLDS, HOLDS, ISSUED_BY, IS_INSIDER), folded into the passed/exit-code gate (EDGE-01..04)"
  - "POPULATED_RELATIONSHIP_TYPES constant documenting the 4-of-11 relationship-type scope for this milestone"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Named per-type gate check: build a dict keyed by type from the already-computed aggregate parity payload, iterate the authoritative expected-type tuple, and fail closed (present=False -> status=failed) for any type contributing no row -- closes FULL-OUTER-JOIN silent-omission gaps without adding new SQL"

key-files:
  created: []
  modified:
    - edgar_warehouse/mdm/snowflake_graph.py
    - tests/mdm/test_cli_snowflake_graph.py

key-decisions:
  - "Two pre-existing 'ok'-path verify-graph tests (test_verify_graph_reports_strict_snowflake_parity, test_verify_graph_skip_native_app_is_explicit_offline_only) used the shared _strict_parity_results() default fixture, which only covers 2 of 6 node types and 2 of 4 populated relationship types. Under the new named-check gate this default fixture is no longer sufficient to report overall status 'ok', so both tests now pass explicit full-coverage node_rows/relationship_rows (via new _all_6_node_rows_at_parity()/_all_4_populated_relationship_rows_at_parity() test helpers) while their aggregate/native_app assertions are preserved unchanged in intent."
  - "Node and relationship named-check helpers (_named_node_parity_checks, _named_relationship_parity_checks) and their verify() wiring were implemented together in a single GREEN commit covering both Task 1 (NODE-01..06) and Task 2 (EDGE-01..04), since both check families share the exact same structural pattern and are folded into the same passed-gate boolean in one edit to verify()."

patterns-established:
  - "Any future per-type CLI parity/health check in this file should follow the _named_*_parity_checks(...) pattern: dict-key the existing aggregate payload by type, iterate the authoritative expected-type tuple, and emit present/status/remediation per type -- no new SQL render function needed."

requirements-completed: [NODE-01, NODE-02, NODE-03, NODE-04, NODE-05, NODE-06, EDGE-01, EDGE-02, EDGE-03, EDGE-04]

coverage:
  - id: D1
    description: "mdm verify-graph emits a named parity check per expected node type (company, adviser, person, security, fund, audit_firm); a type missing entirely from the parity rows is a hard failure (present=False) that flips the exit code, even when the pre-existing aggregate node_parity status would have stayed ok"
    requirement: "NODE-01"
    verification:
      - kind: unit
        ref: "tests/mdm/test_cli_snowflake_graph.py::test_verify_graph_named_node_checks_all_6_types_present_and_ok"
        status: pass
      - kind: unit
        ref: "tests/mdm/test_cli_snowflake_graph.py::test_verify_graph_named_node_check_fails_when_type_missing_entirely"
        status: pass
      - kind: unit
        ref: "tests/mdm/test_cli_snowflake_graph.py::test_verify_graph_named_node_check_fails_on_present_type_count_mismatch"
        status: pass
    human_judgment: false
  - id: D2
    description: "NODE-02..05 (adviser, person, security, fund) each get their own named check via the same ALLOWED_ENTITY_TYPES-driven loop as NODE-01/06 -- proven by the same all-6-types test asserting all 6 entity_type names appear with individual status/present/count fields"
    requirement: "NODE-02"
    verification:
      - kind: unit
        ref: "tests/mdm/test_cli_snowflake_graph.py::test_verify_graph_named_node_checks_all_6_types_present_and_ok"
        status: pass
    human_judgment: false
  - id: D3
    description: "NODE-06: audit_firm named check exists and fails closed when its GRAPH_NODE_AUDITFIRM-backed parity row is absent, completing the per-type assertion for the view 05-01 emitted"
    requirement: "NODE-06"
    verification:
      - kind: unit
        ref: "tests/mdm/test_cli_snowflake_graph.py::test_verify_graph_named_node_check_fails_when_type_missing_entirely"
        status: pass
    human_judgment: false
  - id: D4
    description: "mdm verify-graph emits a named parity check per already-populated relationship type (IS_INSIDER, HOLDS, COMPANY_HOLDS, ISSUED_BY); a type missing entirely from the parity rows is a hard failure that flips the exit code even when the aggregate relationship_parity status would have stayed ok"
    requirement: "EDGE-01"
    verification:
      - kind: unit
        ref: "tests/mdm/test_cli_snowflake_graph.py::test_verify_graph_named_relationship_checks_all_4_populated_types_present_and_ok"
        status: pass
      - kind: unit
        ref: "tests/mdm/test_cli_snowflake_graph.py::test_verify_graph_named_relationship_check_fails_when_type_missing_entirely"
        status: pass
      - kind: unit
        ref: "tests/mdm/test_cli_snowflake_graph.py::test_verify_graph_named_relationship_check_fails_on_present_type_count_mismatch"
        status: pass
    human_judgment: false
  - id: D5
    description: "EDGE-02/03/04 (HOLDS, COMPANY_HOLDS, ISSUED_BY) each get their own named check via the same POPULATED_RELATIONSHIP_TYPES-driven loop; the 7 not-yet-populated relationship types never appear as named checks this phase, preventing a false-fail on legitimately-zero types"
    requirement: "EDGE-02"
    verification:
      - kind: unit
        ref: "tests/mdm/test_cli_snowflake_graph.py::test_verify_graph_named_relationship_checks_exclude_unpopulated_types"
        status: pass
    human_judgment: false

# Metrics
duration: 25min
completed: 2026-07-08
status: complete
---

# Phase 5 Plan 3: Named Per-Type Node And Populated-Relationship Parity Checks Summary

**verify-graph now emits a named, individually-failable parity check for each of the 6 node types and 4 already-populated relationship types, closing the FULL-OUTER-JOIN silent-omission gap that previously let a missing per-type view/row pass the aggregate gate.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-08T06:39:00Z
- **Completed:** 2026-07-08T06:57:42Z
- **Tasks:** 2/2 completed
- **Files modified:** 2

## Accomplishments
- Added `_named_node_parity_checks()`: iterates `ALLOWED_ENTITY_TYPES` (adviser, audit_firm, company, fund, person, security) against the already-computed `node_parity["by_entity_type"]` rows, emitting a `node_parity_<type>` check with `present`/`status`/counts for each — satisfying NODE-01..06.
- Added `_named_relationship_parity_checks()` and the `POPULATED_RELATIONSHIP_TYPES = ("COMPANY_HOLDS", "HOLDS", "ISSUED_BY", "IS_INSIDER")` constant: iterates only the 4 already-populated relationship types against `relationship_parity["by_relationship_type"]`, emitting a `relationship_parity_<type>` check for each — satisfying EDGE-01..04, while intentionally excluding the 7 not-yet-populated types (documented T-05-05 false-positive guard).
- `verify()` now folds both named-check families into its `passed` boolean and exposes them under `payload["named_checks"]["node_parity"]` / `payload["named_checks"]["relationship_parity"]`, so a type entirely absent from the parity rows fails the CLI exit code even when the pre-existing aggregate `node_parity["status"]`/`relationship_parity["status"]` would have stayed `ok`.
- No new SQL render function was added — `grep -n "def _render_verify" edgar_warehouse/mdm/snowflake_graph.py | wc -l` is unchanged at 2, confirming D-01's "named assertions over existing data, not new queries."
- 7 new tests cover: all-6-node-types-ok, missing-audit_firm (silent-omission), present-but-mismatched node type, all-4-relationship-types-ok, missing-ISSUED_BY (silent-omission), present-but-mismatched relationship type, and unpopulated-relationship-type exclusion.
- Full `tests/mdm/` suite passes (249/249), zero live Snowflake/AWS connections anywhere in this plan's tests.

## Task Commits

Each task followed TDD RED/GREEN; both tasks' GREEN implementations landed in one commit since they share the same `verify()` wiring edit:

1. **Task 1 + Task 2 (RED): failing tests for named node/relationship parity checks** - `ce77957` (test)
2. **Task 1 + Task 2 (GREEN): implement named per-type node/relationship parity checks** - `05d80cf` (feat)

## Files Created/Modified
- `edgar_warehouse/mdm/snowflake_graph.py` - Added `POPULATED_RELATIONSHIP_TYPES` constant; added `_named_node_parity_checks()` and `_named_relationship_parity_checks()` helpers; wired both into `verify()`'s `passed` gate and `payload["named_checks"]`.
- `tests/mdm/test_cli_snowflake_graph.py` - Added `_all_6_node_rows_at_parity()`, `_all_6_node_rows_at_parity_payload()`, `_all_4_populated_relationship_rows_at_parity()` fixture helpers; added 7 new tests for the named-check behavior; updated 2 pre-existing "ok"-path tests to supply full 6-node/4-relationship coverage under the new stricter gate.

## Decisions Made
- **Fixture completeness (Rule 1 — bug in test coverage, not implementation):** `test_verify_graph_reports_strict_snowflake_parity` and `test_verify_graph_skip_native_app_is_explicit_offline_only` both relied on `_strict_parity_results()`'s default rows (company+person only, HOLDS+IS_INSIDER only) to assert an overall `status: "ok"` result. Under the new named-check gate, an "ok" result now correctly requires full coverage of all 6 node types and all 4 populated relationship types — the previous default fixture was masking exactly the kind of partial-coverage gap NODE-01..06/EDGE-01..04 exist to catch. Both tests were updated to pass explicit full-coverage rows via the new `_all_6_node_rows_at_parity()`/`_all_4_populated_relationship_rows_at_parity()` helpers; their original aggregate/native_app assertions are otherwise unchanged in intent (counts updated from 3/3 to 6/4 to match the new fixture size).
- **Single GREEN commit for both tasks:** Task 1 (node) and Task 2 (relationship) named-check helpers were implemented together in one commit because both are structurally identical (dict-key the aggregate payload by type, iterate an authoritative expected-type tuple, fail closed on absence) and both fold into the exact same `passed` boolean in one edit to `verify()` — splitting them would have required either an intermediate broken state or artificial file-level separation not present in the actual diff.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pre-existing "ok"-path tests used a now-insufficient default fixture**
- **Found during:** Task 1/2 GREEN verification (full test suite run after implementing named checks)
- **Issue:** `test_verify_graph_reports_strict_snowflake_parity` and `test_verify_graph_skip_native_app_is_explicit_offline_only` asserted `payload["status"] == "ok"` while relying on `_strict_parity_results()`'s default rows, which only cover 2 of 6 node types and 2 of 4 populated relationship types. The new named-check gate correctly fails these partial-coverage fixtures, since an entirely-absent expected type is now a hard failure by design (this is the exact silent-omission gap NODE-01..06/EDGE-01..04 close).
- **Fix:** Updated both tests to pass explicit full-coverage `node_rows`/`relationship_rows` (all 6 node types, all 4 populated relationship types, all at parity) via new test helpers, preserving each test's original aggregate/native_app assertion intent.
- **Files modified:** `tests/mdm/test_cli_snowflake_graph.py`
- **Verification:** `uv run --extra s3 --extra snowflake --extra mdm pytest tests/mdm/test_cli_snowflake_graph.py -q` — 16/16 pass.
- **Committed in:** `05d80cf` (Task 1+2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (Rule 1, test-fixture completeness gap surfaced by the new gate itself — not a production code bug)
**Impact on plan:** No scope creep; the fix only updates test input fixtures to match the new, correctly-stricter gate behavior. No application logic outside `edgar_warehouse/mdm/snowflake_graph.py`'s plan-scoped changes was touched.

## Issues Encountered
None beyond the one deviation documented above.

## User Setup Required
None — no external service configuration required. All verification used the existing `FakeSnowflakeConnection`/`build_parser` mocked harness in `tests/mdm/test_cli_snowflake_graph.py`; no live Snowflake or AWS connection was made anywhere in this plan's work.

## Next Phase Readiness
- Phase 5 is now fully complete: all of NODE-01..06, EDGE-01..04, and GVER-03 (05-01/05-02) are satisfied.
- `mdm verify-graph` remains the single atomic gate consumed by Step Functions' `mdm_verify_graph` state and `go-live.sh`'s local preflight (D-01) — no new command was introduced.
- Per CONTEXT.md D-06, replicating this dev-verified fix into `EDGARTOOLS_PRODB` is a follow-on operator deploy+verify action outside this phase's plan set, not a blocker for Phase 5 completion.
- No blockers identified for Phase 6 (Relationship Investigation And Population).

---
*Phase: 05-node-and-populated-relationship-graph-parity*
*Completed: 2026-07-08*
