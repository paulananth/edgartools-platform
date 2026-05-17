---
phase: 06-relationship-derivation-coverage
plan: 01
subsystem: testing
tags: [mdm, pipeline, relationships, neo4j, tdd, pytest, sqlalchemy]

# Dependency graph
requires:
  - phase: 05-mdm-entity-loading
    provides: MDMPipeline.derive_relationships() and all 6 relationship deriver methods
provides:
  - Full test coverage for all 6 MDM relationship types (IS_INSIDER, HOLDS, ISSUED_BY, MANAGES_FUND, IS_ENTITY_OF, IS_PERSON_OF)
  - 5-counter skip decomposition in derive_relationships() summary dict (D-02)
  - D-03 structured stderr JSON-line events for IS_INSIDER and HOLDS skip reasons
  - D-04 all-6-types idempotency test enforcing second run inserts 0 rows
affects: [mdm-cli, mdm-backfill, mdm-verify, operator-runbook]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "5-tuple return from all relationship derivers: (inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing)"
    - "Structured JSON-line skip events to stderr (mdm_relationship_skip) for IS_INSIDER + HOLDS only"
    - "source-before-target unresolved check order in _derive_is_insider and _derive_holds"

key-files:
  created: []
  modified:
    - tests/mdm/test_pipeline_relationships.py
    - edgar_warehouse/mdm/pipeline.py

key-decisions:
  - "D-01: MANAGES_FUND and ISSUED_BY covered by integration tests against in-memory SQLite, not Neo4j"
  - "D-02: Summary dict exposes 5 skip sub-counters; backward-compat skipped == sum of all 4"
  - "D-03: Structured stderr events emitted only for IS_INSIDER and HOLDS (the two silver-query derivers); entity-only derivers have no skip reasons worth logging"
  - "D-04: Idempotency enforced across all 6 types in a single test; second run must insert 0"
  - "Rule 1 fix: test_returned_count_matches_inserts updated 4->6 because fixture_world now includes MdmFund+MdmSecurity, adding MANAGES_FUND and ISSUED_BY to run_relationships() output"

patterns-established:
  - "TDD RED/GREEN: write failing tests, implement pipeline changes, extend fixture to pass"
  - "fixture_world is the canonical source of MDM domain data for pipeline relationship tests"
  - "Entity-only derivers (no silver query) do not emit stderr events; silver-query derivers do"

requirements-completed: [REL-01, REL-02, REL-03, REL-04]

# Metrics
duration: 15min
completed: 2026-05-17
---

# Phase 06 Plan 01: Relationship Derivation Coverage Summary

**5-counter skip decomposition + D-03 stderr events for all 6 MDM relationship types, with MANAGES_FUND and ISSUED_BY integration tests and full idempotency verification**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-05-17T20:30:00Z
- **Completed:** 2026-05-17T20:44:27Z
- **Tasks:** 3 (RED, IMPL, GREEN)
- **Files modified:** 2

## Accomplishments

- Added 3 failing RED tests for MANAGES_FUND, ISSUED_BY, D-02 counter shape, and D-04 all-types idempotency
- Rewrote all 6 relationship derivers in pipeline.py to return 5-tuples with broken-down skip counters
- Added D-03 structured JSON-line stderr events for IS_INSIDER and HOLDS (all 4 reason codes: corporate, unresolved_source, unresolved_target, existing)
- Extended fixture_world with MdmFund + MdmSecurity to make all 3 new tests GREEN
- All 24 tests pass (up from 21 before this plan)

## Task Commits

Each task was committed atomically:

1. **Task 1: RED tests** - `f88f420` (test)
2. **Task 2: IMPL - 5-tuple counters + D-03 stderr** - `cf8f1d5` (feat)
3. **Task 3: GREEN - fixture_world extension** - `7193b57` (test)

_TDD plan: test -> feat -> test (GREEN)_

## Files Created/Modified

- `tests/mdm/test_pipeline_relationships.py` - Added MdmFund import, 3 new test methods, extended fixture_world with MdmFund+MdmSecurity, updated 2 existing tests (written==4->6, len==4->6)
- `edgar_warehouse/mdm/pipeline.py` - Added json/sys/datetime imports; rewrote derive_relationships() 5-counter unpacking; rewrote _derive_is_insider and _derive_holds with 5-tuples and 4-reason-code stderr events; updated 4 entity-only derivers to 5-tuples

## Decisions Made

- D-01: MANAGES_FUND and ISSUED_BY covered by in-memory SQLite integration tests alongside other rel types (no separate test file needed)
- D-02: Backward-compat: `skipped` key retained in summary dict as sum of all 4 sub-counters
- D-03: Only IS_INSIDER and HOLDS emit structured stderr events - they have meaningful per-row skip reasons (corporate owner, unresolved person/company/security). The 4 entity-only derivers only skip on existing rows, which is low-signal noise.
- D-04: test_all_six_types_idempotent exercises all 6 types in a single test to prevent regressions where one type escapes idempotency

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_returned_count_matches_inserts assertion 4 -> 6**
- **Found during:** Task 3 (GREEN - fixture_world extension) via advisor review
- **Issue:** The plan only mentioned updating test_relationship_derivation_is_idempotent. But test_returned_count_matches_inserts also asserts `written == 4` and calls `run_relationships()` with no filter. After fixture_world gains MdmFund + MdmSecurity, run_relationships() derives MANAGES_FUND (1) + ISSUED_BY (1) on top of the existing 4, producing 6.
- **Fix:** Updated assertion and comment from 4 to 6 to reflect the new total
- **Files modified:** tests/mdm/test_pipeline_relationships.py
- **Verification:** All 24 tests pass
- **Committed in:** 7193b57 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - correctness bug: test would fail after fixture extension)
**Impact on plan:** Essential for correctness. The plan's fixture extension would have broken this pre-existing test without this fix.

## TDD Gate Compliance

- RED gate: `f88f420` - `test(06-01): add RED tests...` - 3 tests failing as expected
- GREEN gate: `7193b57` - `test(06-01): extend fixture_world...` - 24 tests passing
- IMPL gate: `cf8f1d5` - `feat(06-01): add 5-tuple skip counters...` - pipeline changes

## Final Verification Results

```
uv run pytest tests/mdm/test_pipeline_relationships.py -v
# 24 passed in 10.87s

grep -v '^[[:space:]]*#' edgar_warehouse/mdm/pipeline.py | grep -c 'skipped_corporate'
# 18 (>= 6 expected)

grep -v '^[[:space:]]*#' edgar_warehouse/mdm/pipeline.py | grep -c 'mdm_relationship_skip'
# 8 (4 per method x 2 methods: IS_INSIDER + HOLDS)

grep -c 'test_writes_manages_fund_relationship\|test_writes_issued_by_relationship\|test_all_six_types_idempotent' tests/mdm/test_pipeline_relationships.py
# 3

grep -v '^[[:space:]]*#' edgar_warehouse/mdm/pipeline.py | grep -c 'inserted, skipped = '
# 0 (old 2-tuple pattern fully replaced)
```

## Issues Encountered

None - plan executed cleanly. Pre-existing 4 Neo4j errors in test_graph.py are environment-level (NEO4J_URI not set) and unrelated to this plan.

## Next Phase Readiness

- All 6 relationship types have integration test coverage
- D-02 skip counter shape is stable for operator tooling
- D-03 stderr events enable log-based skip monitoring in production
- Ready for Phase 07 (graph sync or operator runbook enhancements)

---
*Phase: 06-relationship-derivation-coverage*
*Completed: 2026-05-17*
