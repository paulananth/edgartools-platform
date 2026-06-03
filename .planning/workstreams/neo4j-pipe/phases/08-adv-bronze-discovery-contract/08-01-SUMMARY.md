---
phase: 08-adv-bronze-discovery-contract
plan: "08-01"
subsystem: application
tags: [adv, bronze, silver, registry, object-storage]

requires:
  - phase: v1.1 Phase 5 live checkpoint
    provides: Live evidence that ownership silver exists while ADV silver tables are empty
provides:
  - ADV bronze artifact discovery/read contract
  - Structured registry, explicit-input, missing-artifact, and unreadable-path issue rows
affects: [phase-09-parse-adv-bronze, mdm-adviser-fund-backfill]

tech-stack:
  added: []
  patterns: [frozen dataclass result contracts, registry-backed artifact reads, injected storage reads]

key-files:
  created:
    - edgar_warehouse/application/adv_bronze_discovery.py
    - tests/application/test_adv_bronze_discovery.py
  modified: []

key-decisions:
  - "Discovery remains separate from parsing and silver merges; Phase 9 owns CLI wiring."
  - "Registry rows are preferred, while explicit artifact records provide a bounded fallback."
  - "Missing and unreadable artifacts are returned as structured issues instead of aborting the batch."

patterns-established:
  - "ADV bronze discovery uses a fixed form allowlist and fixed sec_company_filing query."
  - "Storage reads flow through object_storage.read_bytes or an injected test double."

requirements-completed: [ADV-01, ADV-02, ADV-03, ISO-01, ISO-02, ISO-03]

duration: 35min
completed: 2026-06-03
---

# Phase 8: ADV Bronze Discovery Contract Summary

**Registry-backed and explicit-path ADV bronze discovery with structured artifact issues and storage-adapter reads**

## Performance

- **Duration:** 35 min
- **Started:** 2026-06-03T05:55:00-04:00
- **Completed:** 2026-06-03T06:30:10-04:00
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments

- Added a pure ADV bronze discovery helper with immutable candidate, payload, and issue contracts.
- Implemented registry-first selection through `sec_company_filing`, `sec_filing_attachment`, and `sec_raw_object`, plus bounded explicit artifact input.
- Added focused tests proving filtering, limit behavior, missing issue rows, unreadable-path handling, and no SEC fetch helper usage.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add ADV bronze discovery/read helper** - `f9744ec` (feat)
2. **Task 2: Add focused discovery contract tests** - `1742fd0` (test)

**Plan metadata:** committed with this summary.

## Files Created/Modified

- `edgar_warehouse/application/adv_bronze_discovery.py` - ADV bronze discovery/read helper and result dataclasses.
- `tests/application/test_adv_bronze_discovery.py` - Contract tests for registry discovery, explicit fallback, issue handling, storage reads, and no SEC fetch calls.

## Decisions Made

- Followed the planned Phase 8 boundary: no CLI command, no ADV parsing, and no silver merges.
- Kept the helper independent from `warehouse_orchestrator` so it cannot enter SEC fetch or artifact-refresh paths.
- Applied `limit` to selected candidates after accession filtering, so missing artifacts do not consume candidate slots.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

- `gsd-sdk query init.execute-phase 8` resolves the historical root Phase 8 instead of the workstream Phase 8. Execution used `.planning/active-workstream` and the workstream phase directory as the source of truth.

## Verification

- `uv run python -m py_compile edgar_warehouse/application/adv_bronze_discovery.py` - passed
- `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py -q` - 5 passed
- `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py tests/application/test_parse_ownership_bronze.py -q` - 18 passed, 3 warnings from upstream `edgar` deprecations
- `rg -n "def discover_adv_bronze_artifacts|def read_adv_bronze_artifacts" edgar_warehouse/application/adv_bronze_discovery.py` - passed
- `bash -lc '! rg -n "download_sec_bytes|refresh_filing_artifacts|fsspec\\.filesystem" edgar_warehouse/application/adv_bronze_discovery.py'` - passed

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 9 can wire `parse-adv-bronze` to `discover_adv_bronze_artifacts` and `read_adv_bronze_artifacts`, then feed payloads into `edgar_warehouse.parsers.adv` and existing `SilverDatabase.merge_adv_*` methods.

## Self-Check: PASSED

- Key files exist.
- Source assertions passed.
- Focused and regression tests passed.
- No SEC fetch, artifact refresh, S3 listing, generated deployment JSON, gold/dbt, Snowflake graph sync, or Step Functions edits were introduced.

---
*Phase: 08-adv-bronze-discovery-contract*
*Completed: 2026-06-03*
