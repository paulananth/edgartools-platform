---
phase: 05-node-and-populated-relationship-graph-parity
plan: 02
subsystem: mdm
tags: [mdm, idempotency, node-resolution, real-db, pytest, sqlalchemy]

# Dependency graph
requires:
  - phase: 05-node-and-populated-relationship-graph-parity/05-01
    provides: "GRAPH_NODE_AUDITFIRM view + committed graph-sync (full-rebuild) idempotency regression test (sync half of GVER-03)"
provides:
  - "Committed real-DB node-resolution idempotency regression test covering the 5 silver-resolved MDM entity types (company, adviser, person, security, fund)"
  - "Committed real-DB idempotency assertion for the 6th, seeded (not silver-resolved) entity type (audit_firm)"
  - "GVER-03 fully satisfied: both the node/relationship-derivation side (this plan) and the graph-sync/full-rebuild side (05-01) now have committed regression tests"
affects: [05-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Node-idempotency proof: run each MDMPipeline.run_* method twice over an unchanged StubSilver, snapshot per-entity_type MdmEntity counts via select(MdmEntity.entity_type, func.count()).group_by(...), assert first==second for every type, with entity_type named in the failure message"
    - "MdmEntity has no is_active column (unlike MdmRelationshipInstance/MdmRelationshipType/MdmEntityTypeDefinition) -- resolvers upsert-by-identity rather than soft-delete, so is_quarantined.is_(False) is the correct 'live entity' filter for count-based idempotency assertions"
    - "Seeded-type idempotency proof (audit_firm): call the seeder function twice against the same real session, assert row counts stable and the second call's own summary dict reports zero new inserts"

key-files:
  created: []
  modified:
    - tests/mdm/test_pipeline_relationships.py

key-decisions:
  - "Seeded MdmSourcePriority rows (entity_type='all', source_system in edgar_cik/adv_filing/ownership_filing/derived, matching the canonical seed in edgar_warehouse/mdm/migrations/002_seed_data.sql) locally inside the new node-idempotency test rather than in the shared _seed_registry() fixture used by all other tests in the file -- run_companies/run_advisers/etc. were not previously exercised against a real session in this test file, so no prior test needed source-priority rules; adding them file-wide risked changing behavior for the 30+ existing relationship-side tests."
  - "Used a fresh session (not the fixture_world fixture) with unique CIKs (920001/920002/920102, distinct from fixture_world's 910001/910002/910101/910102) to avoid resolving into fixture_world's pre-seeded company/adviser/person rows, which would have made the idempotency counts ambiguous (can't tell resolver-idempotency from fixture-already-there)."
  - "Verified the new node-idempotency test actually catches a regression (not just a tautology) by temporarily injecting a broken _existing_candidates() lookup in CompanyResolver (impossible-CIK filter) and confirming the test fails hard via a UNIQUE constraint violation on mdm_company.cik, then reverting -- git diff confirms company.py is byte-identical to its pre-injection state."

patterns-established:
  - "Any future MDM node-resolver test that exercises MDMPipeline.run_* against a real session must independently seed MdmSourcePriority (entity_type='all') rows, since MDMRuleEngine.load() raises KeyError without them and the shared test fixture in this file does not provide them."

requirements-completed: [GVER-03]

coverage:
  - id: D1
    description: "Running MDM node resolution twice against unchanged silver rows produces zero net-new active entities for the 5 silver-resolved types (company, adviser, person, security, fund), proven by a real SQLAlchemy session (in-memory SQLite), not mocks"
    requirement: "GVER-03"
    verification:
      - kind: unit
        ref: "tests/mdm/test_pipeline_relationships.py::TestRunRelationships::test_node_resolution_is_idempotent_across_entity_types"
        status: pass
    human_judgment: false
  - id: D2
    description: "The 6th node type (audit_firm, seeded not silver-resolved) is proven idempotent: re-running seed_audit_firms() does not duplicate the 10 seeded firms and its own return summary reports zero new inserts on the second call"
    requirement: "GVER-03"
    verification:
      - kind: unit
        ref: "tests/mdm/test_pipeline_relationships.py::TestRunRelationships::test_audit_firm_seed_is_idempotent"
        status: pass
    human_judgment: false

# Metrics
duration: 25min
completed: 2026-07-08
status: complete
---

# Phase 5 Plan 2: Node-Resolution Idempotency for All 6 MDM Entity Types Summary

**Real-DB regression tests proving MDM node resolution is idempotent for all 6 entity types (5 silver-resolved + 1 seeded), completing the node half of GVER-03 to pair with 05-01's graph-sync half.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-08T06:07:00Z
- **Completed:** 2026-07-08T06:32:46Z
- **Tasks:** 2/2 completed
- **Files modified:** 1

## Accomplishments
- `test_node_resolution_is_idempotent_across_entity_types` proves running `run_companies`, `run_advisers`, `run_securities`, `run_persons`, `run_funds` a second time over unchanged `StubSilver` rows adds zero net-new `MdmEntity` rows per entity type, asserted via a real in-memory SQLite `Session` (not mocks) with the offending `entity_type` named in any failure message.
- `test_audit_firm_seed_is_idempotent` proves `seed_audit_firms()` is a lookup-before-insert no-op on a second call: `MdmAuditFirm` row count, active `audit_firm` `MdmEntity` count, and the seeder's own returned summary (`inserted: 0`, `skipped: 10`) are all asserted stable.
- Confirmed both new tests actually catch regressions (not tautologies) by temporarily injecting a broken company-dedup lookup and observing a hard failure (UNIQUE constraint violation), then reverting cleanly.
- Full `tests/mdm/test_pipeline_relationships.py` suite passes (40/40), all real-DB, zero live Snowflake/AWS connections.
- GVER-03 is now fully satisfied across both halves: node/relationship-derivation idempotency (this plan + prior relationship coverage) and graph-sync/full-rebuild idempotency (05-01).

## Task Commits

Both tasks landed in a single commit (see Decisions below for why they weren't split into separate RED/GREEN commits):

1. **Task 1 + Task 2: node-resolution and audit-firm-seed idempotency tests** - `c10aa42` (test)

## Files Created/Modified
- `tests/mdm/test_pipeline_relationships.py` - Added `func` import and `MdmSourcePriority` import; added `test_node_resolution_is_idempotent_across_entity_types` and `test_audit_firm_seed_is_idempotent` to `TestRunRelationships`.

## Decisions Made
- **Environment fix (Rule 3):** `MDMRuleEngine.load()` raises `KeyError: No source priority rule for company/edgar_cik` when resolving against a real session with no `MdmSourcePriority` rows -- the shared `_seed_registry()` fixture in this file seeds entity-type and relationship-type definitions but not source-priority rules, because no prior test in the file exercised `run_companies`/`run_advisers`/etc. against a real session. Seeded the canonical 4 rows (`entity_type='all'`, `edgar_cik`/`adv_filing`/`ownership_filing`/`derived` at priorities 1-4, matching `edgar_warehouse/mdm/migrations/002_seed_data.sql`) locally inside the new test rather than widening the shared fixture, to avoid any risk of changing behavior for the ~30 existing relationship-side tests in the file.
- **Fixture isolation:** Used a fresh `session` (no `fixture_world`) with unique CIKs so the idempotency counts measure only this test's own resolution passes, not pollution from `fixture_world`'s pre-seeded company/adviser/person rows sharing the same table.
- **"Active" entity definition:** `MdmEntity` has no `is_active` column (unlike `MdmRelationshipInstance`/`MdmRelationshipType`/`MdmEntityTypeDefinition`). Used `is_quarantined.is_(False)` as the "live entity" filter, since resolvers upsert-by-identity rather than soft-delete -- every non-quarantined row present is a live entity, and a net-new row on the second pass is exactly the duplicate the test guards against.
- **TDD framing:** Both tests passed on their first correct-code run (after fixing the environment issues above), the same pattern 05-01 documented for its graph-sync idempotency test -- these are regression tests proving already-correct structural behavior (resolver dedup-by-identity), not bugfixes, so a strict fail-then-pass cycle doesn't apply. Verified test effectiveness directly instead: temporarily broke `CompanyResolver._existing_candidates()`'s CIK filter, confirmed the test failed hard (UNIQUE constraint violation on `mdm_company.cik`), then reverted and confirmed `git diff` showed zero residual change.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing `func` import from sqlalchemy**
- **Found during:** Task 1 (first test run)
- **Issue:** New test used `func.count()` for the per-type grouped-count snapshot; `func` was not imported at module level (only `create_engine, select` were).
- **Fix:** Added `func` to the existing `from sqlalchemy import ...` import line.
- **Files modified:** `tests/mdm/test_pipeline_relationships.py`
- **Verification:** Test collection/import succeeds; test passes.
- **Committed in:** `c10aa42`

**2. [Rule 3 - Blocking] Missing MdmSourcePriority seed rows for real-session resolver runs**
- **Found during:** Task 1 (first test run, `run_companies()` call)
- **Issue:** `MDMRuleEngine.load()` raised `KeyError: No source priority rule for company/edgar_cik` -- the shared test fixture's `_seed_registry()` never populated `mdm_source_priority`, because no prior test in this file called `run_companies`/`run_advisers`/etc. against a real session (only `derive_relationships`, which doesn't hit survivorship's source-priority lookup the same way for company/adviser/person node resolution).
- **Fix:** Seeded the canonical 4 `MdmSourcePriority` rows (`entity_type='all'`) locally inside the new test, matching `edgar_warehouse/mdm/migrations/002_seed_data.sql`'s seed data exactly.
- **Files modified:** `tests/mdm/test_pipeline_relationships.py`
- **Verification:** `run_companies()`/`run_advisers()`/etc. execute without `KeyError`; both new tests pass.
- **Committed in:** `c10aa42`

**3. [Rule 1 - Bug] Initial test used MdmEntity.is_active, a nonexistent column**
- **Found during:** Task 1 drafting (caught before first test run by reading the `MdmEntity` model)
- **Issue:** Plan's `<action>` language ("active MdmEntity rows") suggested an `is_active` filter by analogy with `MdmRelationshipInstance`/`MdmRelationshipType`, but `MdmEntity` has no such column -- only `is_quarantined`.
- **Fix:** Used `MdmEntity.is_quarantined.is_(False)` as the "live" filter in both new tests, with an inline comment explaining the distinction.
- **Files modified:** `tests/mdm/test_pipeline_relationships.py`
- **Verification:** Tests pass against the real schema; no `AttributeError`.
- **Committed in:** `c10aa42`

---

**Total deviations:** 3 auto-fixed (2 Rule 3 blocking/environment, 1 Rule 1 bug caught pre-run) -- all necessary to make the plan's own test scenario executable; no scope creep, no source/production logic changed.
**Impact on plan:** None of the deviations touched application code (`edgar_warehouse/`) -- all were test-file-local fixes (imports, local seed data, correct column name) needed to exercise the plan's specified behavior against the real schema.

## Issues Encountered
None beyond the three deviations documented above, all resolved within the test file's own scope.

## User Setup Required
None - no external service configuration required. All verification used the in-memory SQLite `session` fixture; no live Snowflake or AWS connection was made anywhere in this plan's work.

## Next Phase Readiness
- GVER-03 is now fully satisfied (both node/relationship-derivation idempotency and graph-sync/full-rebuild idempotency have committed regression tests) -- 05-03 can build on this without re-deriving idempotency proof.
- No blockers identified for Plan 03.

---
*Phase: 05-node-and-populated-relationship-graph-parity*
*Completed: 2026-07-08*
