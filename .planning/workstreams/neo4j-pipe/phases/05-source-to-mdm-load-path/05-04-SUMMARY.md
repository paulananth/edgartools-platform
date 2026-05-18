---
phase: 05-source-to-mdm-load-path
plan: "04"
subsystem: mdm-entity-loading
tags: [fix, tdd, duckdb, mdm, silver, idempotency, sqlite, fund-resolver, docs]

requires:
  - phase: 05-source-to-mdm-load-path
    plan: "03"
    provides: sec_tracked_universe fix and MDM silver preflight

provides:
  - FundResolver date coercion: aum_as_of_date survivorship winning_value coerced from str to date
  - Green TestEntityLoadIdempotentForDomainCounts (2 tests) — all 15/15 tests passing
  - Operator documentation docs/aws-mdm-source-to-mdm.md covering local and S3-backed MDM_SILVER_DUCKDB paths
  - Phase 5 complete: all five MDM entity domain counts stable across repeated runs

affects:
  - Phase 6 (relationship derivation coverage)
  - Phase 7 (Neo4j graph synchronisation)

tech-stack:
  added: []
  patterns:
    - "Date-field coercion: convert str ISO date back to datetime.date before setattr on SQLAlchemy Date column"
    - "Operator runbook pattern: export examples + source diagnostics + phase boundary table"

key-files:
  created:
    - docs/aws-mdm-source-to-mdm.md
  modified:
    - edgar_warehouse/mdm/resolvers/fund.py

key-decisions:
  - "Fix placed in FundResolver.resolve_one() setattr loop, not in pipeline.py, to avoid silently dropping aum_as_of_date values"
  - "Only aum_as_of_date coerced; _DATE_FIELDS frozenset documents which Date columns flow through survivorship"
  - "MdmAdviser has no Date columns in ADVISER_FIELDS — AdviserResolver is unaffected"
  - "Survivorship engine type-erasure (str() for all field values) is a deferred architectural item, not fixed here"
  - "Phase 6/7 boundary explicitly stated in docs and SUMMARY: no relationship or Neo4j scope in Phase 5"

metrics:
  duration: ~25min
  completed: "2026-05-17"
  tasks: 2
  files_modified: 2
---

# Phase 5 Plan 04: Idempotent Entity Loading and Operator Documentation Summary

**FundResolver date coercion turns all 15 Phase 5 tests GREEN; operator runbook documents local/S3-backed MDM_SILVER_DUCKDB paths with source diagnostics and phase boundaries**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-17
- **Completed:** 2026-05-17
- **Tasks:** 2
- **Files modified:** 2 (1 fix, 1 new doc)

## Accomplishments

### Task 1: Prove stable all-domain MDM entity counts (GREEN)

Found and fixed SQLite `Date` type mismatch in `FundResolver` that was blocking `TestEntityLoadIdempotentForDomainCounts`:

- **Root cause:** `run_survivorship_for_entity()` stores all field values as `str()` (via `stage_candidate`). When the winning value for `aum_as_of_date` is applied via `setattr(row, 'aum_as_of_date', winning_value)`, SQLite rejects the string `'2024-01-01'` because `Date` columns require Python `datetime.date` objects.
- **Fix:** Added `_DATE_FIELDS: frozenset[str] = frozenset({"aum_as_of_date"})` and ISO string coercion before `setattr` in `FundResolver.resolve_one()`.
- **Scope confirmed:** `MdmAdviser` has no `Date` columns in `ADVISER_FIELDS`; only `MdmFund.aum_as_of_date` is affected.

Test results after fix:

| Class | Result |
|-------|--------|
| TestMissingSilverSourceFailsBeforeSession | 4 PASS |
| TestUnsupportedProtocolRejected | 2 PASS |
| TestS3BackedSilverSourceUsesObjectStorageReadBytes | 2 PASS |
| TestRequiredTableValidation | 2 PASS |
| TestMDMPipelineUsesCurrentSilverSchema | 3 PASS |
| TestEntityLoadIdempotentForDomainCounts | 2 PASS (previously FAIL) |

**Total: 15/15 passed. Full tests/mdm/ suite: 173 passed, 4 pre-existing Neo4j errors (unchanged).**

### Task 2: Document local and S3-backed source-to-MDM operations (DONE)

Created `docs/aws-mdm-source-to-mdm.md` with:

- Local `MDM_SILVER_DUCKDB=/path/to/silver.duckdb` export examples
- S3-backed `MDM_SILVER_DUCKDB=s3://...` path with `MDM_LOCAL_SILVER_DUCKDB` cache option
- `parse-ownership-bronze` command documentation with `--limit` and `--accession-list` options
- Required source table list with domain annotations
- DuckDB diagnostic snippet for verifying row counts per source table
- `sec_company_sync_state` diagnostic for tracking metadata
- `--skip-graph-sync` Phase 5 boundary documentation
- Phase 5/6/7 boundary table
- Isolation boundary: protected Codex workstream files listed (D-04/D-05, ISO-01/ISO-02)
- Idempotency guarantees and identity key documentation per domain

## Task Commits

1. **Task 1: FundResolver date coercion** — `4deb039` (fix)
2. **Task 2: Operator runbook** — `0eee315` (docs)

## Files Created/Modified

- `/Users/aneenaananth/projects/edgartools-platform/edgar_warehouse/mdm/resolvers/fund.py` — Added `_DATE_FIELDS` frozenset and ISO string-to-date coercion in `resolve_one()` setattr loop
- `/Users/aneenaananth/projects/edgartools-platform/docs/aws-mdm-source-to-mdm.md` — New operator runbook for Phase 5 MDM source-to-entity load path

## Decisions Made

- Fix placed in `FundResolver.resolve_one()`, not in `pipeline.py`, because the mismatch is between what survivorship stores (strings) and what `MdmFund.aum_as_of_date` requires (Python date). Fixing at the write point is more precise than stripping values from the staged dict upstream.
- `_DATE_FIELDS` frozenset documents the contract explicitly; future date columns in `MdmFund` only need to be added here.
- Survivorship engine type-erasure (all values as `str()`) is not fixed here — that is an architectural change spanning all resolvers. Noted as a deferred item.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SQLite Date column rejects string from survivorship winning_value**
- **Found during:** Task 1 (running TestEntityLoadIdempotentForDomainCounts)
- **Issue:** `FundResolver` writes `MergeResult.winning_value` (a str like `'2024-01-01'`) directly to `MdmFund.aum_as_of_date` (a SQLAlchemy `Date` column). PostgreSQL accepts ISO date strings; SQLite requires `datetime.date` objects and raises `StatementError`.
- **Fix:** Detect when field name is in `_DATE_FIELDS` and value is a str; call `date.fromisoformat(value)` before `setattr`.
- **Files modified:** `edgar_warehouse/mdm/resolvers/fund.py`
- **Commit:** `4deb039`

## Known Stubs

None. All implementation is complete and functional. The documentation does not contain placeholder text or unresolved TODOs.

## Deferred Items

- **Survivorship string type-erasure:** `stage_candidate` converts all field values to `str()`. Date, Numeric, and Integer domain columns all receive strings as `winning_value`. Currently only `aum_as_of_date` surfaces as a test failure because SQLite is strict; PostgreSQL silently coerces. A proper fix would preserve Python types through `MdmEntityAttributeStage.field_value` or add per-field type coercion in `run_survivorship_for_entity`. Deferred to a future refactor plan.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries were introduced.

| Flag | File | Status |
|------|------|--------|
| T-05-18 (idempotency) | edgar_warehouse/mdm/resolvers/fund.py | MITIGATED — domain counts stable across two runs |
| T-05-19 (current schema) | edgar_warehouse/mdm/pipeline.py | MITIGATED in 05-03 (sec_company_sync_state) |
| T-05-20 (operator docs) | docs/aws-mdm-source-to-mdm.md | MITIGATED — variable names only, no secret values |
| T-05-21 (graph sync scope) | docs/aws-mdm-source-to-mdm.md | MITIGATED — --skip-graph-sync documented as Phase 5 boundary |
| T-05-22 (artifact readiness) | docs/aws-mdm-source-to-mdm.md | MITIGATED — bounded readiness checks documented |

## Self-Check

- [x] `edgar_warehouse/mdm/resolvers/fund.py` exists and contains `_DATE_FIELDS` — FOUND
- [x] `docs/aws-mdm-source-to-mdm.md` exists — FOUND
- [x] Commit `4deb039` exists in git log — FOUND
- [x] Commit `0eee315` exists in git log — FOUND
- [x] All 15 tests pass: `pytest tests/mdm/test_source_to_mdm_load_path.py` → 15 passed
- [x] Combined test run: `pytest tests/mdm/test_source_to_mdm_load_path.py tests/application/test_parse_ownership_bronze.py` → 28 passed
- [x] `rg sec_tracked_universe pipeline.py` returns no active production dependency
- [x] Documentation contains all required terms: MDM_SILVER_DUCKDB, MDM_LOCAL_SILVER_DUCKDB, parse-ownership-bronze, --skip-graph-sync, sec_ownership_reporting_owner, sec_filing_attachment, sec_raw_object
- [x] Static check: only `edgar_warehouse/mdm/resolvers/fund.py` and `docs/aws-mdm-source-to-mdm.md` changed; Codex files untouched

## Self-Check: PASSED

---
*Phase: 05-source-to-mdm-load-path*
*Completed: 2026-05-17*
