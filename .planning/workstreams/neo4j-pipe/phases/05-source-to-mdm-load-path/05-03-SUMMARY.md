---
phase: 05-source-to-mdm-load-path
plan: "03"
subsystem: mdm-cli
tags: [tdd, duckdb, mdm, silver, preflight, pytest, sec-edgar, d11, d12, pipe-03]

requires:
  - phase: 05-source-to-mdm-load-path
    plan: "01"
    provides: RED test contract for MDM silver preflight (D-11, D-12)

provides:
  - Shared MDM silver-source preflight before any MDM mutation (_require_silver_reader)
  - Entity-type-aware required-table allowlist (_ENTITY_TYPE_REQUIRED_TABLES)
  - D-12 relationship-readiness table policy (_REQUIRED_TABLES_RELATIONSHIP_READINESS)
  - Fixed sec_tracked_universe -> sec_company_sync_state in MDMPipeline.run_companies()
  - GREEN tests for TestMissingSilverSourceFailsBeforeSession (4 tests)
  - GREEN tests for TestRequiredTableValidation (2 tests)
  - GREEN tests for TestS3BackedSilverSourceUsesObjectStorageReadBytes (2 tests)
  - GREEN tests for TestMDMPipelineUsesCurrentSilverSchema (3 tests, D-12)

affects:
  - 05-04 (entity load idempotency — TestEntityLoadIdempotentForDomainCounts deferred)

tech-stack:
  added: []
  patterns:
    - "Preflight-before-session: _require_silver_reader() runs before _session() in all mutation paths"
    - "Fixed allowlist: table names in _validate_silver_tables come only from module-level constants"
    - "Entity-type policy mapping: _ENTITY_TYPE_REQUIRED_TABLES maps entity type to required tables"

key-files:
  created: []
  modified:
    - edgar_warehouse/mdm/cli.py
    - edgar_warehouse/mdm/pipeline.py
    - tests/mdm/test_source_to_mdm_load_path.py

key-decisions:
  - "_require_silver_reader() returns (reader, exit_code) tuple and prints actionable stderr naming MDM_SILVER_DUCKDB before any _session() call"
  - "_validate_silver_tables() validates against a fixed module-level allowlist; user-provided identifiers are never interpolated into SQL (T-05-14)"
  - "sec_tracked_universe in pipeline.py:100 replaced with sec_company_sync_state to match current silver DDL (D-12)"
  - "Test _seed_registry() extended with MdmSourcePriority rows so resolver chain can stage attributes without KeyError"
  - "TestEntityLoadIdempotentForDomainCounts deferred to 05-04 (SQLite Date type mismatch in fund resolver)"

metrics:
  duration: "~30min"
  tasks: 2
  files_modified: 3
  completed: "2026-05-17"
---

# Phase 5 Plan 03: MDM Silver-Source Preflight Summary

**Shared MDM silver-source preflight guards all mutation paths; sec_tracked_universe binder error fixed in MDMPipeline.run_companies()**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-17T09:45:00Z
- **Completed:** 2026-05-17T10:18:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

### Task 1: Add fixed-table silver preflight helpers (GREEN)

Added to `edgar_warehouse/mdm/cli.py`:

- `_validate_silver_tables(reader, required_tables)` — queries `information_schema.tables` to check existence then COUNT per table; all table names come from module-level frozenset constants only (T-05-14 SQL injection prevention)
- `_require_silver_reader(required_tables, command_name)` — opens `_silver_reader()`, catches open/protocol errors, prints actionable stderr naming `MDM_SILVER_DUCKDB`, returns `(reader, exit_code)` without calling `_session()` (T-05-15 pre-session gate)
- Five allowlist constants: `_REQUIRED_TABLES_COMPANY`, `_REQUIRED_TABLES_ADVISER`, `_REQUIRED_TABLES_FUND`, `_REQUIRED_TABLES_PERSON`, `_REQUIRED_TABLES_SECURITY`
- `_REQUIRED_TABLES_RELATIONSHIP_READINESS` for D-12 (`sec_company`, `sec_company_filing`, `sec_ownership_reporting_owner`)
- `_ENTITY_TYPE_REQUIRED_TABLES` mapping from entity-type string to applicable frozenset

### Task 2: Wire preflight into mutating MDM handlers (GREEN)

Refactored in `edgar_warehouse/mdm/cli.py`:

- `_handle_run`: calls `_require_silver_reader(required_tables, ...)` before `_session()`, wraps session in `finally` block
- `_handle_derive_relationships`: calls `_require_silver_reader(_REQUIRED_TABLES_RELATIONSHIP_READINESS, ...)` before `_session()`
- `_handle_load_relationships`: calls `_require_silver_reader(_REQUIRED_TABLES_RELATIONSHIP_READINESS, ...)` before `_session()`
- `_safe_arguments()` and `_logged_handler()` remain unchanged (T-05-16)

Fixed in `edgar_warehouse/mdm/pipeline.py`:

- `run_companies()` line 100: `sec_tracked_universe` → `sec_company_sync_state` (D-12 schema correction)

Fixed in `tests/mdm/test_source_to_mdm_load_path.py`:

- `_seed_registry()` extended with `MdmSourcePriority` rows (source priority seed required by `MDMRuleEngine` during resolver `_stage_attrs` calls)

## Task Commits

1. **Tasks 1+2: Add MDM silver-source preflight and fix sec_tracked_universe** - `2010313`

## Test Results

| Class | Before | After |
|-------|--------|-------|
| TestMissingSilverSourceFailsBeforeSession | 4 FAIL | 4 PASS |
| TestUnsupportedProtocolRejected | 2 PASS | 2 PASS (unchanged) |
| TestS3BackedSilverSourceUsesObjectStorageReadBytes | 1 PASS, 1 FAIL | 2 PASS |
| TestRequiredTableValidation | 2 FAIL | 2 PASS |
| TestMDMPipelineUsesCurrentSilverSchema | 3 FAIL | 3 PASS |
| TestEntityLoadIdempotentForDomainCounts | 2 FAIL | 2 FAIL (deferred to 05-04) |

**Total: 13 passed, 2 deferred-failing (explicitly out of scope)**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] MdmSourcePriority rows missing from test fixture**
- **Found during:** Task 2 (attempting to turn TestMDMPipelineUsesCurrentSilverSchema green)
- **Issue:** The test's `_seed_registry()` seeded entity types and relationship types but not `MdmSourcePriority` rows. `MDMRuleEngine.load()` populates `_source_priority` from the DB; when empty, `resolver._stage_attrs()` raises `KeyError: 'No source priority rule for person/ownership_filing'`.
- **Fix:** Added 4 `MdmSourcePriority` rows to `_seed_registry()` in the test file (`all/edgar_cik/1`, `all/adv_filing/2`, `all/ownership_filing/3`, `all/derived/4`), matching `seed_defaults()` in `migrations/runtime.py`.
- **Files modified:** `tests/mdm/test_source_to_mdm_load_path.py`
- **Commit:** `2010313`

**2. [Rule 1 - Bug] sec_tracked_universe does not exist in current silver DDL**
- **Found during:** Task 1 (running TestMDMPipelineUsesCurrentSilverSchema after preflight fix)
- **Issue:** `MDMPipeline.run_companies()` line 100 queries `sec_tracked_universe` which is a stale table name; the current silver DDL uses `sec_company_sync_state`. This caused DuckDB `CatalogException` for all run_companies-dependent tests.
- **Fix:** Changed `"SELECT tracking_status FROM sec_tracked_universe WHERE cik = ?"` → `"SELECT tracking_status FROM sec_company_sync_state WHERE cik = ?"` in pipeline.py.
- **Files modified:** `edgar_warehouse/mdm/pipeline.py`
- **Commit:** `2010313`

## Deferred Items

`TestEntityLoadIdempotentForDomainCounts` (2 tests) — these tests call `run_funds()` which triggers a SQLite `StatementError` because `aum_as_of_date='2024-01-01'` is a string, not a Python `date` object. This is a separate FundResolver/SQLite compatibility issue unrelated to this plan's preflight scope. Per plan 05-03 instructions, these are deferred to plan 05-04.

## Known Stubs

None. All code paths added implement real validation behavior. No placeholder text, hardcoded empty UI values, or TODO stubs exist in the modified files.

## Threat Flags

No new network endpoints, auth paths, or schema changes at trust boundaries were introduced.

| Flag | File | Description |
|------|------|-------------|
| threat_flag: T-05-14 (mitigated) | edgar_warehouse/mdm/cli.py | _validate_silver_tables uses fixed allowlist constants; no user-provided table names interpolated |
| threat_flag: T-05-15 (mitigated) | edgar_warehouse/mdm/cli.py | _require_silver_reader runs before _session() in all three mutation handlers |
| threat_flag: T-05-16 (preserved) | edgar_warehouse/mdm/cli.py | _safe_arguments() unchanged; no new env var values printed in logs |

## Self-Check

- [x] `edgar_warehouse/mdm/cli.py` exists and contains `_require_silver_reader` — FOUND
- [x] `edgar_warehouse/mdm/pipeline.py` exists and contains `sec_company_sync_state` — FOUND
- [x] `tests/mdm/test_source_to_mdm_load_path.py` exists and contains `MdmSourcePriority` — FOUND
- [x] Commit `2010313` exists in git log — FOUND
- [x] All 4 TestMissingSilverSourceFailsBeforeSession tests PASS — CONFIRMED
- [x] All 2 TestRequiredTableValidation tests PASS — CONFIRMED
- [x] All 2 TestS3BackedSilverSourceUsesObjectStorageReadBytes tests PASS — CONFIRMED
- [x] All 3 TestMDMPipelineUsesCurrentSilverSchema tests PASS — CONFIRMED
- [x] 13 passed, 2 deferred-failing in full test file — CONFIRMED
- [x] 158 passed, 4 pre-existing Neo4j errors in full tests/mdm/ suite — CONFIRMED (no regressions)

## Self-Check: PASSED

---
*Phase: 05-source-to-mdm-load-path*
*Completed: 2026-05-17*
