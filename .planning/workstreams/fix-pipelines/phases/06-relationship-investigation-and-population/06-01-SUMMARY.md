---
phase: 06-relationship-investigation-and-population
plan: 01
subsystem: mdm
tags: [mdm-pipeline, sqlite, duckdb, cik-batching, sql-parameterization, tdd]

# Dependency graph
requires:
  - phase: 05-node-and-populated-relationship-graph-parity
    provides: INSTITUTIONAL_HOLDS deriver (unbatched), sibling EMPLOYED_BY/AUDITED_BY
      derivers, _fetch_optional_relationship_rows/_bounded_relationship_sql helpers
provides:
  - CIK-range batched, parameterized read for _derive_institutional_holds
  - "_INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE module constant (default 1000 CIKs/batch)"
  - Regression coverage proving batched output == single-query output
affects: [06-03-full-universe-load-history-run, 06-05-graph-sync-and-verify]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CIK-range batched read: one cheap MIN(cik)/MAX(cik) bounds query (still
      routed through the missing-source-table graceful skip), then a loop of
      parameterized WHERE cik BETWEEN ? AND ? reads in fixed-size CIK chunks"

key-files:
  created: []
  modified:
    - edgar_warehouse/mdm/pipeline.py
    - tests/mdm/test_pipeline_relationships.py

key-decisions:
  - "CIK bounds are always passed via silver.fetch(sql, params=[lo, hi]) — never
    string-formatted into the SQL body (T-06-01)"
  - "Batch-equivalence test compares edges by (adviser CIK, security CUSIP) not
    raw entity_id, since entity_ids are freshly-generated UUIDs per independent
    test session and never match across separate single-batch/multi-batch runs"
  - "_INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE left at 1000 (TODOS.md's example value)
    per plan's Claude's Discretion — real tuning deferred to 06-03 once actual
    sec_thirteenf_holding row density is observed in dev"

patterns-established:
  - "Sibling derivers (_derive_employed_by, _derive_audited_by) are unaffected —
    only INSTITUTIONAL_HOLDS needed batching per D-03/TODOS.md's OOM risk analysis"

requirements-completed: [EDGE-11]

coverage:
  - id: D1
    description: "_derive_institutional_holds reads sec_thirteenf_holding in bounded
      CIK-range chunks (WHERE cik BETWEEN ? AND ?) instead of one unbounded fetch"
    requirement: "EDGE-11"
    verification:
      - kind: unit
        ref: "tests/mdm/test_pipeline_relationships.py::TestInstitutionalHoldsBatching::test_batch_equivalence_single_vs_multi_batch"
        status: pass
      - kind: unit
        ref: "tests/mdm/test_pipeline_relationships.py::TestInstitutionalHoldsBatching::test_accumulation_across_batches"
        status: pass
    human_judgment: false
  - id: D2
    description: "CIK-range bounds are passed as bound query parameters, never
      string-interpolated into SQL (T-06-01 mitigation)"
    requirement: "EDGE-11"
    verification:
      - kind: unit
        ref: "tests/mdm/test_pipeline_relationships.py::TestInstitutionalHoldsBatching::test_batch_equivalence_single_vs_multi_batch"
        status: pass
    human_judgment: false
  - id: D3
    description: "Cross-batch early-exit (target_per_type) and counter accumulation
      behave identically to the pre-batching version; missing-table skip fires
      exactly once, not per batch; second run is idempotent"
    requirement: "EDGE-11"
    verification:
      - kind: unit
        ref: "tests/mdm/test_pipeline_relationships.py::TestInstitutionalHoldsBatching::test_cross_batch_early_exit"
        status: pass
      - kind: unit
        ref: "tests/mdm/test_pipeline_relationships.py::TestInstitutionalHoldsBatching::test_missing_source_table_single_skip"
        status: pass
      - kind: unit
        ref: "tests/mdm/test_pipeline_relationships.py::TestInstitutionalHoldsBatching::test_batching_idempotent_on_rerun"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-08
status: complete
---

# Phase 06 Plan 01: INSTITUTIONAL_HOLDS CIK-Range Batching Summary

**`_derive_institutional_holds` now reads `sec_thirteenf_holding` via a MIN/MAX CIK
bounds lookup plus a `WHERE cik BETWEEN ? AND ?` batch loop (default 1000 CIKs/batch,
bound params only) instead of one unbounded `silver.fetch()`, proven equivalent to the
prior single-query behavior by 5 new regression tests.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2/2 completed
- **Files modified:** 2

## Accomplishments
- `_derive_institutional_holds` issues a single cheap `SELECT MIN(cik), MAX(cik) ...`
  bounds query (still governed by the existing missing-source-table graceful skip),
  then steps through the CIK range in `_INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE` (1000)
  chunks, each read via `self.silver.fetch(sql, params=[cik_lo, cik_hi])`.
- CIK bounds are always bound query parameters — never string-formatted into the SQL
  text (T-06-01 mitigated).
- All counters (`inserted`, `skipped_corporate`, `skipped_unresolved_source`,
  `skipped_unresolved_target`, `skipped_existing`) and the `remaining`-based
  early-exit accumulate across all batches, not per batch — verified by a
  regression test that would fail if counters reset inside the batch loop.
- 5 new tests added: batch-equivalence (+ params-not-interpolated assertion),
  cross-batch accumulation, cross-batch early-exit, missing-table single-skip,
  and second-run idempotency. Extended `StubSilver` to emulate the aggregate
  MIN/MAX bounds query and BETWEEN-bounded batch reads, keeping all pre-existing
  tests (which use plain substring-matched fixtures) passing unchanged.
- Full `tests/mdm/` suite: 254 passed (45 in `test_pipeline_relationships.py`).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add failing CIK-range batching tests for _derive_institutional_holds (RED)** - `3268dc6` (test)
2. **Task 2: Implement CIK-range batched read in _derive_institutional_holds (GREEN, D-03)** - `decf6c9` (feat)

_Note: Task 2's commit also includes a small test-file fix (see Deviations) discovered
while getting the batch-equivalence test to pass correctly._

## Files Created/Modified
- `edgar_warehouse/mdm/pipeline.py` - `_INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE` constant
  added; `_derive_institutional_holds` rewritten with MIN/MAX bounds lookup + CIK-range
  batch loop, parameterized `BETWEEN ? AND ?` reads, cross-batch counter accumulation
  and early-exit.
- `tests/mdm/test_pipeline_relationships.py` - `StubSilver` extended to emulate
  aggregate MIN/MAX bounds queries and BETWEEN-bounded batch reads (records
  `(sql, params)` call history); new `TestInstitutionalHoldsBatching` class with
  5 regression tests.

## Decisions Made
- CIK-range bounds are always passed as bound params (`fetch(sql, params=[lo, hi])`),
  never interpolated into the SQL string — directly enforced by a test assertion
  (T-06-01).
- Batch-equivalence test compares edges by `(adviser CIK, security CUSIP)` rather
  than raw entity_id UUIDs, since each of the two compared runs uses its own
  independent in-memory session (entity_ids are freshly generated per session and
  never coincide across sessions even for logically identical edges).
- Batch size left at the TODOS.md example value of 1000 CIKs per batch — this
  plan's `<context>` explicitly leaves exact tuning to Claude's Discretion, to be
  revisited once 06-03's real `load_history` run shows actual
  `sec_thirteenf_holding` row density in dev.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a bug in my own Task 1 test (batch-equivalence entity_id comparison)**
- **Found during:** Task 2 (running the new tests against the real implementation)
- **Issue:** `test_batch_equivalence_single_vs_multi_batch` compared raw
  `(source_entity_id, target_entity_id)` pairs between two *independent* sessions
  (single-batch run and multi-batch run each build their own fresh in-memory
  SQLite session/adviser fixtures). Adviser `entity_id`s are `uuid.uuid4()`-generated
  per session, so they never match across the two runs even when the underlying
  logical edge (same CIK holding the same CUSIP) is identical — the test would have
  failed even against a correct implementation.
- **Fix:** Changed the edge comparison to resolve `entity_id` back to
  `(MdmAdviser.cik, MdmSecurity.cusip)` before comparing sets — CUSIP-derived
  security IDs are deterministic (UUID5) so those already matched; only the
  adviser-side lookup needed the translation.
- **Files modified:** `tests/mdm/test_pipeline_relationships.py`
- **Verification:** Full suite green (45/45 in the file, 254/254 in `tests/mdm/`).
- **Committed in:** `decf6c9` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (test bug found and fixed while validating the
implementation, Rule 1). No production-code scope creep — `_derive_institutional_holds`
matches the plan's design exactly.

## Issues Encountered
None beyond the test-comparison bug documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- EDGE-11's batching prerequisite for the bounded 06-03 `load_history` run is
  in place — `_derive_institutional_holds` will no longer risk an ECS OOM on a
  full `sec_thirteenf_holding` scan.
- No blockers for 06-02 (next planned plan in this phase's wave sequence).

---
*Phase: 06-relationship-investigation-and-population*
*Completed: 2026-07-08*
