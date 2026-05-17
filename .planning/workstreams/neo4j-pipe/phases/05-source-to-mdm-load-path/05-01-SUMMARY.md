---
phase: 05-source-to-mdm-load-path
plan: "01"
subsystem: testing
tags: [tdd, duckdb, mdm, silver, ownership, pytest, sec-edgar]

requires:
  - phase: 04-operational-readiness
    provides: operator diagnostics for silver readiness gaps

provides:
  - RED test contract for parse-ownership-bronze schema and artifact-registry reads (D-01..D-10)
  - RED test contract for MDM silver preflight before _session() (D-11..D-12)
  - DuckDB silver fixture with all five entity domains (company, adviser, person, security, fund)
  - Idempotency baseline for MDM domain table counts

affects:
  - 05-02 (repair parse-ownership-bronze)
  - 05-03 (repair MDM silver preflight and pipeline schema)
  - 05-04 (operator documentation)

tech-stack:
  added: []
  patterns:
    - "RED-before-GREEN: test files encode known current defects before any repair is written"
    - "FakeSilverDB with fetch_calls list for SQL assertion without hitting DuckDB"
    - "Real DuckDB fixture (not CSV/mock) for CLI and pipeline integration tests"
    - "monkeypatch + session spy to assert _session() ordering relative to preflight"

key-files:
  created:
    - tests/application/test_parse_ownership_bronze.py
    - tests/mdm/test_source_to_mdm_load_path.py
  modified: []

key-decisions:
  - "Tests anchor to current defects: form_type/period_of_report in orchestrator line 1258-1261, _session() before _silver_reader() in cli.py lines 278/480/503, sec_tracked_universe in pipeline.py line 101"
  - "FakeSilverDB records raw SQL strings so tests assert column names without needing a live DuckDB"
  - "Real DuckDB fixture used for CLI source-preflight tests to exercise the actual _silver_reader() code path"
  - "3 tests in test_source_to_mdm_load_path.py intentionally pass (existing correct behaviors: ftp/http rejection, s3 read_bytes delegation)"
  - "parse_ownership patched at edgar_warehouse.parsers.ownership (function-local import target)"

requirements-completed:
  - PIPE-01
  - PIPE-02
  - PIPE-03
  - ISO-01
  - ISO-02

duration: 35min
completed: "2026-05-17"
---

# Phase 5 Plan 01: Source-to-MDM Load Path — Wave 0 RED Tests Summary

**RED test contract locking silver schema column names, artifact-registry reads, MDM_SILVER_DUCKDB preflight ordering, and entity-load idempotency before any Phase 5 repair is written**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-05-17T00:00:00Z
- **Completed:** 2026-05-17T00:35:00Z
- **Tasks:** 2
- **Files modified:** 2 (both new test files)

## Accomplishments

- Created `tests/application/test_parse_ownership_bronze.py` with 13 tests across 5 test classes; 12 fail RED against current implementation, 1 passes (skip-check already queries correct table)
- Created `tests/mdm/test_source_to_mdm_load_path.py` with 15 tests across 6 test classes; 12 fail RED against current implementation, 3 pass (existing correct object_storage protocol behaviors)
- Built a real DuckDB silver fixture helper (`_create_silver_fixture`) seeding all five entity domains: company, adviser, person, security, fund — anchored to current `silver_store.py` DDL column names
- Confirmed both verify commands exit nonzero, validating the Wave 0 RED acceptance criterion

## Task Commits

1. **Tasks 1+2: Create parse-ownership-bronze RED tests + MDM source-to-load RED tests** - `ffc9ad8` (test)

## Files Created/Modified

- `/Users/aneenaananth/projects/edgartools-platform/tests/application/test_parse_ownership_bronze.py` - RED tests for D-01..D-10: schema column names, artifact-registry reads via sec_filing_attachment+sec_raw_object, skip-already-parsed, missing-artifact metric, no SEC API calls
- `/Users/aneenaananth/projects/edgartools-platform/tests/mdm/test_source_to_mdm_load_path.py` - RED tests for D-11..D-12: MDM_SILVER_DUCKDB preflight before _session(), protocol allowlist, required-table validation, sec_company_sync_state vs sec_tracked_universe, entity-load idempotency

## Decisions Made

- Used `FakeSilverDB.fetch_calls` list to assert SQL column names without DuckDB execution — this is the cleanest way to test the D-07 schema-name defect without rewriting orchestrator imports
- `parse_ownership` patched at `edgar_warehouse.parsers.ownership` (not at orchestrator module attribute) because the function-local import `from edgar_warehouse.parsers.ownership import parse_ownership` inside `_run_parse_ownership_bronze` resolves through sys.modules
- Three tests in `test_source_to_mdm_load_path.py` intentionally pass against current code (ftp/http rejection, s3 URI delegation): these verify security behaviors that are ALREADY correct and should remain passing after the repair
- Real DuckDB fixture chosen over StubSilver for CLI tests so `_silver_reader()` code path is exercised end-to-end

## Deviations from Plan

None — plan executed as written. The two test files were created with the required source assertions, behavior assertions, and security assertions as specified in D-01 through D-12.

## Issues Encountered

- `patch.object(warehouse_orchestrator, "parse_ownership", ...)` failed with `AttributeError` because `parse_ownership` is a function-local import inside `_run_parse_ownership_bronze`. Fixed by patching at source module `edgar_warehouse.parsers.ownership.parse_ownership` instead.
- `uv run` absorbs pytest exit code in some bash wrapper contexts. Verified exit code 1 using `uv run ... python -m pytest` which propagates it correctly.

## TDD Gate Compliance

This plan is `type: tdd` Wave 0 (RED phase only). The gate requires:

1. RED gate: test commits exist — CONFIRMED (`ffc9ad8` is the `test(05-01):` commit)
2. GREEN gate: not yet applicable — repair happens in 05-02 and 05-03
3. REFACTOR gate: not yet applicable

Plans 05-02 and 05-03 will produce the GREEN gate commits.

## Known Stubs

None. Both test files contain no placeholder text, hardcoded empty UI values, or unresolved stubs. They are complete RED test contracts.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries were introduced. These are test files only.

## Self-Check

- [x] `tests/application/test_parse_ownership_bronze.py` exists — FOUND
- [x] `tests/mdm/test_source_to_mdm_load_path.py` exists — FOUND
- [x] Commit `ffc9ad8` exists in git log — FOUND
- [x] All required source terms present in test_parse_ownership_bronze.py: form, report_date, sec_filing_attachment, sec_raw_object, read_bytes, sec_ownership_reporting_owner
- [x] All required source terms present in test_source_to_mdm_load_path.py: MDM_SILVER_DUCKDB, _session, sec_company_sync_state, sec_ownership_reporting_owner, sec_ownership_non_derivative_txn, mdm_company, mdm_adviser, mdm_person, mdm_security, mdm_fund, s3://, object_storage.read_bytes
- [x] Task 1 verify: 12 failed, 1 passed — exit nonzero
- [x] Task 2 verify: 12 failed, 3 passed — exit nonzero

## Self-Check: PASSED

---
*Phase: 05-source-to-mdm-load-path*
*Completed: 2026-05-17*
