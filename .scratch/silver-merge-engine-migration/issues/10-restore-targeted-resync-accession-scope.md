# 10 — Restore targeted-resync accession scope

**Type:** task (verify live), then a decision

**Status:** resolved in code 2026-09-14 (answer below). Not yet run live.

## Question

`targeted-resync --scope accession` appears broken since duckdb-retirement-cutover Ticket 10
stopped hydrating local DuckDB. `_run_accession_resync` (`warehouse_orchestrator.py`) starts
with `db.get_filing(accession_number)` on a store the command opened empty in a fresh
container, so it should always raise "Unknown accession_number for targeted resync". Found
while grilling [Ticket 06d](06-submissions-and-artifact-tables-landing-only.md); a code
reading, not yet confirmed by a run.

1. **Verify live:** run one accession-scoped `targeted_resync` in prod against a known
   accession and capture the result. If it works, record why the code reading was wrong and
   close this ticket.
2. **If it is broken, decide the fix:**
   - read the filing row from Snowflake silver (`SnowflakeSilverReader`), then continue with
     the same-run artifact/text/parse steps; or
   - capture the accession's CIK submissions first (as the `cik` scope already does), so the
     in-run lookup 06d introduces holds the filing.

   The second reuses the existing capture path and costs one submissions fetch; the first
   adds a Snowflake read but keeps the scope narrow.

Not part of 06d: the in-run lookup answers "what did this run already record", and this
command's read is for a filing recorded by an earlier run.

**Blocked by:** none — frontier. The second fix option depends on 06d's in-run lookup landing.

## Answer (2026-09-14)

**1. Broken, confirmed without a live run** (user decision: a local repro is enough, since the
failure does not depend on data). Prod history has no accession-scoped `targeted_resync`
execution to check: the recent ones, including the one successful run after the cutover
(`ticket90-apple-backfill-1789242920`, 2026-09-12), all used `cik` scope. Running the real
accession branch of `_capture_bronze_raw` against a fresh `SilverDatabase` raises
`WarehouseRuntimeError: Unknown accession_number for targeted resync`. `get_filing` answers only
from `_in_run_lookup` (06d), and nothing earlier in an accession-scoped run records the filing.

**2. Fix: read the filing from Snowflake silver** (user decision, the first option).
- New `_filing_rows_snowflake(accession_number)` in `warehouse_orchestrator.py`, shaped like
  its neighbours `_company_identity_ciks_snowflake` / `_snowflake_distinct_values`. It selects
  `sec_company_filing`'s 17 DDL columns by name, so an extra column in the collapsed model never
  reaches `merge_filings`. The silver grain is (accession_number, cik), so a multi-CIK accession
  returns one row per CIK, lowest CIK first.
- The accession branch records every row with `db.merge_filings` (filling the in-run lookup),
  then calls the unchanged `_run_accession_resync`. No row: it fails closed, naming
  `EDGARTOOLS_SILVER` and pointing at `--scope-type cik` (silver can lag a new filing by hours).
- The cik branch is unchanged; its submissions capture records the filings in the same run.

**Tests:** `tests/unit/test_targeted_resync_accession_scope.py` runs the real
`_capture_bronze_raw` accession branch against a real `SilverDatabase` with the Snowflake read
patched: an earlier run's filing resyncs and both CIK rows land; no row fails closed;
parsers without artifacts fail closed; the cik branch never reads Snowflake; the column list is
pinned to the live DDL and the helper selects exactly it and closes the reader. The first four
were red before the fix, but through `patch.object`'s `AttributeError` (the helper did not exist);
the original error was reproduced separately by running the unpatched branch (above).
Full suite excluding `tests/integration`: 3487 passed, 5 skipped; the two tests and small fixes
added by the review below re-ran with the targeted-resync test files (14 passed). Ruff and mypy:
nothing new against the base. Integration tests and dbt compile were not run locally.

**Review (Standards, Spec, GoF).** GoF: no findings (the connect/fetch/close repeat is a 5-line
`try/finally`; an `__enter__` on `SnowflakeSilverReader` would be its own change). Fixed:
- parsers without artifacts: the parsers read this run's attachment rows, which only the
  artifact step records, so `--no-include-artifacts` with parsers on marked every parse run
  failed while the command succeeded. The accession branch now refuses that combination before
  reading Snowflake. (Text alone recovers: text extraction refreshes artifacts itself.)
- the rows recorded from Snowflake now count in `rows_inserted`, as the cik branch counts its
  capture;
- the column-list test compared against a hand-copied dict with substring checks; it is now
  pinned to `SilverDatabase._table_columns` and checks the exact select list;
- the fail-closed message now mentions retired filings, which the silver model also excludes;
- comments now say, deliberately: recording re-lands the rows with this run's sync stamp (as the
  old DuckDB upsert did; dbt collapses the copies, including `_run_accession_resync`'s own
  re-record of the first row), and `get_filing` returns the lowest CIK, since silver has no
  reliable issuer signal for a multi-CIK accession.

Follow-up, not done here: the cik branch has the same parsers-without-artifacts gap for
accessions whose attachments an earlier run captured; failing closed there would abort a whole
cik resync, so it needs its own decision.
