# LOAD_SILVER_LANDING_TASK Suspended Since 2026-08-13 — Landing Zone Has Zero Rows

Status: resolved

## Summary

Found while checking prod readiness for the mdm-ahead-of-silver map's Phase C
(task #134): the entire silver-landing zone pipeline has never actually
loaded a row in production.

- `EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.LOAD_SILVER_LANDING_TASK`
  (the 5-minute scheduled `COPY INTO` task, `13_silver_landing_ingest.sql`)
  is `state: suspended`, `last_suspended_reason: SUSPENDED_DUE_TO_ERRORS`,
  suspended at `2026-08-13 20:03:34-07:00` — about 2h25m after being
  created (`2026-08-13 17:38:26-07:00`).
- `TASK_HISTORY` shows it failed every 5-minute run leading up to
  suspension with the identical error: `"NULL result in a non-nullable
  column"` at `Statement.execute, line 30 position 22`. This is the exact
  symptom `13_silver_landing_ingest.sql`'s own comments (lines 109-130)
  describe as already found-and-fixed live during Ticket 07 (`COPY INTO
  ... MATCH_BY_COLUMN_NAME` doesn't invoke a column's `DEFAULT` for a column
  absent from the source Parquet, so `parse_sequence` arrives NULL and the
  procedure must explicitly backfill it after each `COPY`). Either that fix
  never actually reached the deployed procedure, or a different
  non-nullable column hits the same gap.
- Consequence: `EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.SEC_COMPANY`
  (and, by the same task, every other landing table) has **zero rows**
  (`SELECT COUNT(*) = 0`), despite `SILVER_LANDING_EXPORT_ROOT` being
  correctly wired into the live `edgartools-prod-medium` task definition
  since task #115 — so Parquet exports may well be landing in S3 (not
  checked in this pass), but nothing has been copied into Snowflake since
  the task suspended.
- Downstream consequence: `EDGARTOOLS_PROD.EDGARTOOLS_SILVER` (the schema
  the 31 generated dbt silver models materialize into) has **zero tables
  and zero views** — `dbt run` for the silver layer has apparently never
  been executed against prod at all, separately from the landing-load
  failure above.

## Found while

Checking whether the mdm-ahead-of-silver map's Phase B code (commits
`47fe8fb5`..`5aad528e`) is ready to deploy (task #134). It isn't, and not
for a reason that map's own tickets control: the new
`backfill-mdm-entity-ids` sweep reads pending rows directly from
`EDGARTOOLS_SILVER.*` dynamic tables — which don't exist yet, on top of
which the `mdm_entity_id` column itself hasn't been applied to the landing
schema either (a separate, in-scope gap — see the mdm-ahead-of-silver
map's own Phase A follow-up).

## Impact

Independent of mdm-ahead-of-silver entirely. Any consumer expecting
`EDGARTOOLS_SILVER.*` dynamic tables to reflect real data (dashboards,
future gold models built on top, this map's new sweep) will find them
missing or empty in prod today.

## Root cause (confirmed live)

Not the `parse_sequence` gap `13_silver_landing_ingest.sql`'s comments
describe (that fix is live and correct — `parse_sequence` is nullable and
gets backfilled by the deployed procedure exactly as documented). A
different, single table.

- `QUERY_HISTORY` for the exact failure window (`2026-08-13 19:43-19:44`)
  shows the failing statement is always the same: `COPY INTO
  sec_company_ticker FROM @LANDING_STAGE/sec_company_ticker/ ...
  ON_ERROR = ABORT_STATEMENT`. Since the JS procedure has no try/catch
  around `copyStmt.execute()`, this one table's failure aborts the whole
  procedure every run — which is why *every* table shows 0 rows, not just
  this one.
- Downloaded the actual stuck file
  (`s3://edgartools-prod-snowflake-export-690839588395/warehouse/artifacts/
  silver_landing/sec_company_ticker/business_date=2026-08-14/
  run_id=ticket42-task35-fulluniverse-retry7-1786673391/sec_company_ticker.parquet`,
  20,796 rows) and inspected its schema directly: only 3 columns —
  `cik`, `ticker`, `exchange`. `sec_company_ticker`'s Snowflake schema has
  a 4th `NOT NULL` column, `source_name`, entirely absent from the file —
  `MATCH_BY_COLUMN_NAME` leaves it unmapped, `COPY INTO` doesn't invoke its
  default for a column missing from the source, and it lands `NULL`
  against a `NOT NULL` constraint. Exactly the "NULL result in a
  non-nullable column" error, on every retry, because a stage file that
  fails `ON_ERROR = ABORT_STATEMENT` is never marked loaded and gets
  retried on every subsequent `COPY INTO` call.
- Traced to the actual bug: `replace_company_tickers`
  (`edgar_warehouse/silver_store.py`, called from
  `warehouse_orchestrator.py:5072`) was decorated
  `@track_landing_rows("sec_company_ticker")`. That decorator records
  whatever the caller passed as the `rows` argument — correct for every
  *other* decorated method in this file, because their callers already
  pass fully-shaped rows. `replace_company_tickers` is the one exception:
  its caller passes bare `{cik, ticker, exchange}` dicts straight from
  `company_tickers_exchange.json`, and the method itself only adds
  `source_name`, `source_rank`, `last_sync_run_id`, `last_synced_at`
  *inside its own loop*, per row, right before the DuckDB `INSERT`. The
  decorator captured the 3-column pre-enrichment shape, not the 7-column
  row actually written to DuckDB — a structural bug, reproducible on
  every single run, not stale or one-off data.

## Fix (committed, not yet deployed)

Removed `@track_landing_rows("sec_company_ticker")` from
`replace_company_tickers`; the method now builds the enriched row inline
during its existing loop and calls `self.landing_export.record(...)`
manually with the same 7 columns the DuckDB `INSERT` uses — matching the
precedent `track_landing_accounting_flag_scores` already established in
this file for a method whose landing shape doesn't match its raw input.
Two new regression tests in `tests/unit/test_silver_landing_export.py`
cover the enriched-row shape and the cik/ticker-missing skip path.

## Next step

Not deployed. Needs: (1) build+push a warehouse image containing this fix
(bundle with mdm-ahead-of-silver task #134's own image rebuild — same
image, same deploy), (2) manually clear/replace the stuck
`sec_company_ticker` Parquet file in S3 (the old 3-column file will still
fail even after the code fix, since it's already sitting in the stage) or
delete+reprocess it, (3) `ALTER TASK LOAD_SILVER_LANDING_TASK RESUME`,
(4) verify a clean run loads all 30 tables, (5) a first `dbt run` against
prod for the silver layer once landing data exists (this issue's original
"zero tables in EDGARTOOLS_SILVER" finding is a separate, subsequent step
past just unblocking the load task).

## Answer (2026-08-19)

**Resolved.** All of this held even through the intervening account
rebuild (`pijjxma-ppb32800` → `PRJEDJU-QJB05385`, 2026-08-17/18 — see the
map's own note on this) and Ticket 11's reprovisioning pass. Checked live,
not assumed:

- `SHOW TASKS LIKE 'LOAD_SILVER_LANDING_TASK'`: `state: started`,
  `schedule: 5 MINUTE`, `last_suspended_reason: null`, owned by
  `EDGARTOOLS_PROD_LOADER`.
- `TASK_HISTORY` over the last 2 days: 44 `SUCCEEDED`, 2 `FAILED`. Both
  failures landed at `14:22` and `14:27` PDT, 5 and 10 minutes after the
  task's own `created_on` (`14:17:11`) — right when Ticket 11 re-created
  it on the rebuilt account — with the identical old error ("NULL result
  in a non-nullable column"). Every run since `14:32` (4+ hours, 44
  consecutive) has succeeded.
- Source fix confirmed live in the deployed image, not just committed:
  `silver_store.py:1403-1410` shows `replace_company_tickers` with the
  `@track_landing_rows` decorator deliberately removed (commit `11f81229`).
  The currently-registered `edgartools-prod-medium` task def (revision
  204, registered `2026-08-18T14:43:11-04:00`) runs image digest
  `sha256:13ba01c5...`, tagged `warehouse-sha-97a93a617b6b` —
  `git merge-base --is-ancestor 11f81229 97a93a617b6b` confirms the fix
  commit is an ancestor of what's actually deployed.
- Landing/silver row counts are still near-zero (`SEC_COMPANY_TICKER`:
  0, `SEC_COMPANY`: 0) — expected, not a symptom: the only non-zero table
  is `SEC_EMPLOYMENT_EVENT` (1,506 rows), which is Ticket 11's known
  manual-`REFRESH` test data, not a real bulk load. No bulk export has run
  against this account yet (Stage 14 / task #159 pending).

**One inference, flagged as such, not verified:** why the two failures
stopped after `14:27` isn't directly confirmed. The task's own retry
semantics mean a still-stuck stage file should keep failing every run
indefinitely — so something cleared it (most likely the S3 lifecycle rule
from task #124, or a leftover effect of Ticket 11's own manual test run),
but that clearing event itself wasn't observed directly, only its absence
of further failures. This does not weaken the resolution (the code bug
that *caused* the original symptom is confirmed fixed and deployed), but
the real at-scale proof point — a fresh `sec_company_ticker` export
landing clean once Stage 14 actually runs — is still pending, tracked
under Ticket 12's own Stage 14 blocker rather than reopened here.
