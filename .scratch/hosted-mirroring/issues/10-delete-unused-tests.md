# 10: Delete unused tests

Status: resolved

The operator, 2026-11-20: "Delete all unused tests"; asked which count, chose "Never run + old engine (Recommended)":
the tests that never run, and the tests of the old engine's tables and code, each deleted with that code.

## Findings

- CI runs every test folder. The last green `main` run: unit and MDM 3,047 passed, 1 skipped; integration 336 passed;
  the skill adapters skip 127 on SQL Server, 10 on Postgres and 8 on MySQL.
- Every adapter skip is an engine condition ("Mastering runs on PostgreSQL and MySQL", "MySQL ... only"): each such test
  runs on another engine's job, so none is unused.
- The one unit skip is `test_database_file_tables_become_parts` (tests/unit/test_profiling_inputs.py): it needs a DuckDB
  sqlite extension download CI cannot make, so it never runs in CI.
- Four integration files collect no tests. Three are helpers named like test files and imported by other tests
  (`test_mdm_postgres.py` by 22 files, `test_run_pins_postgres.py`, `test_entity_context_postgres.py`); one,
  `test_name_matching.py`, is imported by nothing.
- The old engine is reached through the storage adapter and the `mdm` commands (`mdm rebuild` replays the old tables,
  which are empty); only `tests/storage_adapters/test_registration_authority.py` names its tables directly. Its tests go
  with its code in ticket 09.

## Checklist

- [x] Find the tests that never run: skips per engine, files that collect nothing, the unit skip (above) 2026-11-20 10:12 ET
- [x] Delete `tests/integration/test_name_matching.py` (imported by nothing) and `test_database_file_tables_become_parts` (never runs in CI); `tests/unit/test_profiling_inputs.py` 57 passed, integration still collects 336 2026-11-20 10:12 ET
- [x] The old engine's tests: deleted with the old engine's code and tables in ticket 09 (resolved); `tests/storage_adapters/test_registration_authority.py` no longer exists 2026-11-20 16:01 ET
- [x] Learning → skill: none (ticket 09 carries the old-engine lesson) 2026-11-20 16:01 ET

## Answer

Resolved 2026-11-20 16:01 ET. The tests that never run are deleted (PR 1947) and the old engine's tests went with its code in ticket 09.
