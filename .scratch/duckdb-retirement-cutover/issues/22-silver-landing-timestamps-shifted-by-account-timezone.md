# 22 — Silver-landing timestamps load 7–8 hours late (account time zone applied to UTC values)

**What was found:** while investigating [Ticket 19](19-sec-company-ticker-cross-store-divergence.md)
(2026-09-14). The landing Parquet files store correct UTC instants, but the Snowflake landing tables
hold the same clock time labelled with the account time zone, `America/Los_Angeles`. Every
landing timestamp is therefore 7 hours late in summer (PDT) and 8 hours late in winter (PST).

**Evidence (two tables, two runs):**

| Table / run | Parquet value (`timestamp[us, tz=UTC]`, `isAdjustedToUTC=true`) | Snowflake landing value | As UTC |
|---|---|---|---|
| `sec_company_ticker`, NVDA, `daily-incremental-verify-bookkeeping-fix-1788343855` | 2026-09-02 10:14:42.298 UTC | 2026-09-02 10:14:42.298 −0700 | 17:14:42 UTC |
| `sec_thirteenf_filing`, `0000354201-26-000002`, `ticket15-historical-backfill-2` | 2026-07-22 01:56:35.123 UTC | 2026-07-22 01:56:35.123 −0700 | 08:56:35 UTC |

The first run started 2026-09-02 10:10:55 UTC (06:10:55 ET, epoch in its run id), so the Parquet value is the
true time and the Snowflake value is 7 hours in the future. DuckDB's copy of the same row agrees
with the Parquet file.

**Mechanism (likely, not yet proven):** `LOAD_SILVER_LANDING()` in
`infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql` loads with
`COPY INTO ... FILE_FORMAT = (FORMAT_NAME = PARQUET_FORMAT) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE`.
`PARQUET_FORMAT` sets no logical-type option, so the Parquet timestamp arrives without its zone
and becomes `TIMESTAMP_TZ` in the session time zone. The account and session `TIMEZONE` parameter
is `America/Los_Angeles` (default).

**Scope:** 24 `TIMESTAMP*` columns in `EDGARTOOLS_SILVER_LANDING` load through the same path
(`last_synced_at`, `ingested_at`, `fetched_at`, `source_last_modified`, `accepted_at`,
`feed_published_at`, `extracted_at`, `processed_at`, `entity_facts_refreshed_at`, `retired_at`),
so all of `EDGARTOOLS_SILVER` and the gold models built on it likely carry the shift. Verified on
two tables only.

## Question

1. Confirm the mechanism with a one-row test file. Two levers, with different reach:
   `TIMEZONE = 'UTC'` scoped to `LOAD_SILVER_LANDING()` changes only how these timestamps are
   read; `USE_LOGICAL_TYPE = TRUE` on the shared `PARQUET_FORMAT` changes how every landing table
   reads every Parquet logical type (DECIMAL and DATE too), so it needs a wider check.
2. Decide the fix for new loads and what to do about rows already landed. For a correction,
   prefer relabelling the stored clock time as UTC, e.g.
   `to_timestamp_tz(to_varchar(col, 'YYYY-MM-DD HH24:MI:SS.FF9') || ' +0000')`, over subtracting
   7 or 8 hours by date: it does not depend on daylight saving.
3. Find consumers that compare these timestamps with a real clock, a date, or a timestamp from
   another store, where the shift changes an answer. Comparisons between two landing timestamps
   are unaffected. Candidates to check: MDM relationship watermarks on `ingested_at`
   (`mdm/pipeline.py`), the entity-facts refresh check `filing_date > entity_facts_refreshed_at`
   (`infrastructure/silver_once.py`), freshness checks on `data_timestamp`, `table-reconcile`'s
   `max_authority_value` watermark (a shifted Snowflake value compared with unshifted DuckDB
   values), and any gold column shown to users.

**Blocked by:** none.

## Diagnosis (2026-09-14)

**Mechanism confirmed.** Not caused by the 2026-09-04 change to US/Eastern business dates in the
bookkeeping store: that change converts stored UTC instants to an Eastern date for a comparison and
writes nothing; the shift is Los Angeles (−07:00), not Eastern; and it is already present on the
first ticker load (2026-08-22). Snowflake's `TIMEZONE` was never set at account, user or task level
(`America/Los_Angeles` is Snowflake's default).

Loop: a one-row Parquet file holding 2026-09-02 10:14:42.298138 UTC (`timestamp[us, tz=UTC]`),
loaded with `PUT` + `COPY INTO ... MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE` into a temporary
`TIMESTAMP_TZ` table (session-scoped temporary stage and table; nothing persists), then read back
as UTC. Scratch script, not committed.

| Variant | Stored (as UTC) | Result |
|---|---|---|
| Production `PARQUET_FORMAT`, default session (`America/Los_Angeles`) — run 3 times | 17:14:42.298138 | RED (deterministic) |
| Same, session `TIMEZONE = 'America/New_York'` | 14:14:42.298138 | RED (+4 h: shift follows the session zone) |
| Same, session `TIMEZONE = 'UTC'` | 10:14:42.298138 | GREEN |
| Inline format `TYPE = PARQUET USE_LOGICAL_TYPE = TRUE`, default session | 10:14:42.298138 | GREEN |
| Source layer's `EDGARTOOLS_SOURCE_EXPORT_FILE_FORMAT`, default session | 17:14:42.298138 | RED |

So with `USE_LOGICAL_TYPE = FALSE` (both file formats' live value) the Parquet timestamp is read as a
zone-less clock time and labelled with the session `TIMEZONE`.

**Scope is wider than landing.** The source layer loads the same way:
`LOAD_EXPORTS_FOR_RUN`/`LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN`, called from
`PROCESS_RUN_MANIFEST_STREAM` by `SNOWFLAKE_RUN_MANIFEST_TASK` (task `TIMEZONE` also
`America/Los_Angeles`), copy Parquet with `EDGARTOOLS_SOURCE_EXPORT_FILE_FORMAT`
(`USE_LOGICAL_TYPE = false`) and `MATCH_BY_COLUMN_NAME`. `EDGARTOOLS_SOURCE` has 15 `TIMESTAMP_TZ`
columns.

**Lever chosen: pin each loading task's session to UTC.**
- Reaches the load: `LOAD_SILVER_LANDING()` and `PROCESS_RUN_MANIFEST_STREAM` are
  `EXECUTE AS OWNER`; Snowflake documents `TIMEZONE` as one of the caller session parameters an
  owner's-rights procedure uses, and a task supports every session parameter
  (`ALTER TASK ... SET TIMEZONE`). The Terraform provider (`snowflakedb/snowflake` 2.14.1) exposes it
  as `snowflake_task.timezone`, an in-place update.
- Safe for the rest of each procedure: `LOAD_SILVER_LANDING()` uses no date or clock function. The
  source-side procedures use `CURRENT_TIMESTAMP()` (an instant; only its label changes),
  `TO_DATE(<business_date string>)` (zone-independent), and one
  `TO_TIMESTAMP_TZ(TO_VARCHAR(CURRENT_TIMESTAMP()))` round trip that keeps its offset.
- `USE_LOGICAL_TYPE = TRUE` also works but is rejected as the fix: on the shared file formats it
  changes how 28 `DATE` and 10 scaled `NUMBER` landing columns are read too.
- Residual gap: a manual `CALL` from an operator session keeps that session's zone. No repo script
  calls `LOAD_SILVER_LANDING()` by hand; `scripts/test/smoke-test-single-cik.sh` and
  `scripts/test/ownership-neo4j-e2e-quick.sh` call `LOAD_EXPORTS_FOR_RUN`, and
  `scripts/verify-pr1/04_smoke_merge_proc.sh` calls `LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN`, from a
  `snow sql` session, and would still load shifted rows.
- The manifest Snowpipe (`SNOWFLAKE_RUN_MANIFEST_PIPE`) is not affected: it loads JSON and parses
  `completed_at` with `TO_TIMESTAMP_TZ` from a string that carries `Z` or `+00:00`.

## Fix for new loads (2026-09-14, not deployed)

`TIMEZONE = 'UTC'` is pinned on every definition of both loading tasks:

- `LOAD_SILVER_LANDING_TASK` (`13_silver_landing_ingest.sql`): in `CREATE TASK IF NOT EXISTS`, and
  as `ALTER TASK ... SET TIMEZONE = 'UTC'` between the existing `SUSPEND` and `RESUME` (the create
  is a no-op on an installed task).
- `SNOWFLAKE_RUN_MANIFEST_TASK`, which has three definitions and whichever runs last replaces the
  task: Terraform `snowflake_task.manifest_processor` (`timezone = "UTC"`, an in-place update in
  provider 2.14.1), `deploy-snowflake-stack.sh`'s `deploy_manifest_task`, and
  `04_refresh_wrapper.sql`. Clause order checked against Snowflake's `CREATE TASK` syntax (session
  parameters after `SCHEDULE`, before `COMMENT` and `WHEN`).

Regression test: `tests/unit/test_loader_task_timezone_sql.py` (5 tests, red before the fix, green
after). Full suite excluding `tests/integration`: 3444 passed, 5 skipped. Reviewed on three axes
(Standards, Spec, GoF); fixes applied: the test bounds each definition by its `CALL` body (a `;`
inside a `COMMENT` had cut it short), a stray whitespace change reverted, a comment added to the
deploy script, one more manual-`CALL` script listed above.

Follow-up filed: [Ticket 23](23-consolidate-snowflake-run-manifest-task-definitions.md), one
definition for `SNOWFLAKE_RUN_MANIFEST_TASK` (the three copies already disagree on `SCHEDULE`).

Merged in PR #629 (`ec5be53c`, 2026-09-14 18:59 ET). **Not deployed:** both tasks still show
`TIMEZONE = America/Los_Angeles` in prod (checked 2026-09-14).

## Rollout plan (2026-09-14, draft — every prod step needs operator go-ahead)

Deploy, correction of loaded rows, and the MDM marker fix are one change. Doing only part of it
skips MDM rows (see "MDM relationship markers").

### Dry run (read-only, 2026-09-14)

**The offset identifies the shifted rows.** `TIMESTAMP_TZ` stores an offset with each value. In
every column to correct, every non-null value is `-07:00`. No value is UTC or `-08:00` yet (the
oldest value is 2026-07-05, all summer time). After the deploy, new rows land as UTC, which
Snowflake prints as offset `Z` (not `+00:00`). So each correction statement filters on
`to_varchar(col, 'TZH:TZM') IN ('-07:00', '-08:00')`. The filter is idempotent (a corrected value is `Z` and
is not selected again) and needs no cutoff by `parse_sequence` or load time.

**The offset alone is not enough.** Five `EDGARTOOLS_SOURCE` columns are written by Snowflake, not
loaded from Parquet. They already hold correct instants. **Do not correct them:**

| Column | Rows | Offset | Written by |
|---|---|---|---|
| `SNOWFLAKE_REFRESH_STATUS.UPDATED_AT` | 36 | `-07:00` | `CURRENT_TIMESTAMP()` (`03_source_load_wrapper.sql`, `04_refresh_wrapper.sql`, `06_fundamentals_load_wrapper.sql`) |
| `SNOWFLAKE_REFRESH_STATUS.LAST_SUCCESSFUL_REFRESH_AT` | 32 | `-07:00` | `CURRENT_TIMESTAMP()` (same files) |
| `SNOWFLAKE_RUN_MANIFEST_INBOX.RECEIVED_AT` | 37 | `-07:00` | `DEFAULT CURRENT_TIMESTAMP()` (`01_source_stage.sql`) |
| `SNOWFLAKE_REFRESH_STATUS.MANIFEST_COMPLETED_AT` | 36 | `Z` | `TO_TIMESTAMP_TZ` of a string ending in `Z` |
| `SNOWFLAKE_RUN_MANIFEST_INBOX.COMPLETED_AT` | 37 | `Z` | Snowpipe JSON, same |

`CURRENT_TIMESTAMP()` in a Los Angeles session gives the correct instant with a Los Angeles
label. Relabelling those values would move them 7 hours into the past.

**Correction list:** all 24 `TIMESTAMP_TZ` columns in `EDGARTOOLS_SILVER_LANDING` and the 10
`INGESTED_AT` columns in `EDGARTOOLS_SOURCE`. None has a column default; all are loaded by
`COPY INTO` from Parquet. Values to correct now:

| Schema | Table | Column | Values at `-07:00` |
|---|---|---|---|
| landing | `SEC_COMPANY` | `LAST_SYNCED_AT` | 157,992 |
| landing | `SEC_COMPANY_ADDRESS` | `LAST_SYNCED_AT` | 105,556 |
| landing | `SEC_COMPANY_FILING` | `LAST_SYNCED_AT` | 6,398,260 |
| landing | `SEC_COMPANY_SUBMISSION_FILE` | `LAST_SYNCED_AT` | 3,950 |
| landing | `SEC_COMPANY_TICKER` | `LAST_SYNCED_AT` | 166,280 |
| landing | `SEC_EARNINGS_RELEASE` | `INGESTED_AT` | 918 |
| landing | `SEC_EMPLOYMENT_EVENT` | `INGESTED_AT` | 7,379 |
| landing | `SEC_ENTITY_FACTS_REFRESH_WATERMARK` | `ENTITY_FACTS_REFRESHED_AT` | 1 |
| landing | `SEC_EXECUTIVE_RECORD` | `INGESTED_AT` | 14,755 |
| landing | `SEC_FINANCIAL_DERIVED` | `INGESTED_AT` | 5,056 |
| landing | `SEC_FINANCIAL_FACT` | `INGESTED_AT` | 434,805 |
| landing | `SEC_FUNDAMENTALS_PROCESSED_ACCESSION` | `PROCESSED_AT` | 15 |
| landing | `SEC_RAW_OBJECT` | `FETCHED_AT` | 400,446 |
| landing | `SEC_THIRTEENF_FILING` | `INGESTED_AT` | 14,364 |
| landing | `SEC_THIRTEENF_HOLDING` | `INGESTED_AT` | 6,799,919 |
| source | `EARNINGS_RELEASE` | `INGESTED_AT` | 918 |
| source | `EXECUTIVE_RECORD` | `INGESTED_AT` | 14,755 |
| source | `SEC_FINANCIAL_DERIVED` | `INGESTED_AT` | 5,056 |
| source | `SEC_FINANCIAL_FACT` | `INGESTED_AT` | 434,805 |
| source | `SEC_THIRTEENF_HOLDING` | `INGESTED_AT` | 6,799,919 |

Total: 14,509,696 landing values in 15 tables and 7,255,453 source values in 5 tables. The other
columns in the list have no non-null value today:
- Landing: `SEC_ACCOUNTING_FLAG`, `SEC_GUIDANCE_FACT` and `SEC_GUIDANCE_FACT_REJECT` `.INGESTED_AT`,
  `SEC_CURRENT_FILING_FEED` (3 columns), `SEC_FILING_TEXT.EXTRACTED_AT`,
  `SILVER_LANDING_RETIREMENT.RETIRED_AT`, and `SEC_RAW_OBJECT.SOURCE_LAST_MODIFIED` (all NULL).
- Source: `ACCOUNTING_FLAG`, `CONSENSUS_ESTIMATES`, `EARNINGS_CALENDAR`, `GUIDANCE_FACTS`,
  `TRANSCRIPT_EVENTS`.

Keep a statement for each of these columns anyway: the offset filter makes it a no-op today, and
it covers any row that lands before the window.

**Formula checked** on `SEC_COMPANY_TICKER` (166,280 rows, `SELECT` only):
`to_timestamp_tz(to_varchar(col, 'YYYY-MM-DD HH24:MI:SS.FF9') || ' +0000', 'YYYY-MM-DD HH24:MI:SS.FF9 TZHTZM')`
keeps every clock digit (0 changed), moves every value exactly 7 hours earlier (0 exceptions), and
gives offset `Z`. For example, `2026-09-02 10:15:29.021 -0700` (17:15 UTC, wrong) becomes
`2026-09-02 10:15:29.021 Z`.

**No direct change needed downstream:**
- `EDGARTOOLS_SILVER` (32 dynamic tables, `TARGET_LAG = 6 hours`) and `EDGARTOOLS_GOLD` (21 dynamic
  tables) recompute from the corrected base tables.
- Silver keeps the latest row by `parse_sequence desc` (the `silver_not_retired` macro and each
  model), never by a timestamp. So neither the correction nor a period of mixed offsets changes
  which row silver keeps.
- Gold `earnings_calendar`, `guidance_facts` and `consensus_estimates` sort by `ingested_at` only
  after `as_of`. A uniform shift keeps their order, and their source tables are empty today.
- No stream reads a table in the correction list. The only stream, `SNOWFLAKE_RUN_MANIFEST_STREAM`,
  reads the excluded inbox table.
- Gold refresh lag: 20 of 21 gold tables are `TARGET_LAG = DOWNSTREAM`. They show corrected values
  only after the next `REFRESH_AFTER_LOAD` or a manual refresh.

**Time Travel is 1 day** (`RETENTION_TIME = 1` on every table in both schemas). That is too short
to undo a rewrite of this size, so the plan takes clones first (decision D2).

### MDM relationship markers

`mdm_relationship_derivation_checkpoint` (MDM Postgres) stores `watermark_value` and, since
migration 022, `pending_watermark_value` as TEXT. Three checkpoint keys have
`watermark_column = 'ingested_at'`: executive-record `EMPLOYED_BY`, employment-event
`EMPLOYED_BY` and `INSTITUTIONAL_HOLDS` (`edgar_warehouse/mdm/pipeline.py` lines 3854, 4004, 4583).
Each value is `datetime.isoformat()` of a shifted Snowflake value, so it should end in `-07:00`.
The stored values have not been read (reading needs the MDM Postgres credential); read them in
step 0.

Two hazards if the rows are corrected and the markers are not:
1. **Rows skipped.** The filter `ingested_at > <marker>` compares instants. A corrected row is 7
   hours earlier than before. Any row not yet processed that lies within 7 hours after the marker
   drops behind it and is skipped until the monthly reconciliation pass
   (`_relationship_watermark` returns None only in `reconciliation_pass`).
2. **Text comparisons break.** `_track_watermark` takes a text max, and
   `advance_relationship_watermark` only advances when `watermark_value < excluded.watermark_value`
   (text). If `-07:00` and `+00:00` strings are mixed, those comparisons use the clock digits, not
   the instants. So the markers must have one offset before MDM runs again.

Fix: relabel the stored strings the same way as the rows, keeping the digits and writing `+00:00`:

```sql
UPDATE mdm_relationship_derivation_checkpoint
SET watermark_value = regexp_replace(watermark_value, '-0[78]:00$', '+00:00'),
    pending_watermark_value = regexp_replace(pending_watermark_value, '-0[78]:00$', '+00:00')
WHERE watermark_column = 'ingested_at';
```

After this, the markers and the rows are the same UTC instants. New values from Snowflake come back
as `+00:00`, so the text comparisons are consistent again.

### Other consumers (question 3)

- `get_ciks_with_new_qualifying_filing` (`infrastructure/silver_once.py`) compares
  `filing_date > entity_facts_refreshed_at`. Today that is 1 shifted row; the landing correction
  fixes it.
- `table-reconcile`'s `max_authority_value` compares a shifted Snowflake value with DuckDB. It
  leaves with DuckDB (Tickets 09, 21), so it is not corrected separately.
- The earlier audit found no other Python comparison with a real clock and no dbt filter on these
  columns. The 14 gold model files that expose them use them for display only.

### Runbook (after go-ahead; run in one window)

0. **Before.** Confirm no Step Functions execution is running that loads warehouse data or runs
   MDM (`daily_incremental`, `load_history`, MDM utility). Save the three checkpoint rows
   (`SELECT *` with `watermark_column = 'ingested_at'`). Re-run the offset count, because rows may
   have landed since this dry run.
1. **Suspend both tasks:** `ALTER TASK ... SUSPEND` on `LOAD_SILVER_LANDING_TASK` and
   `SNOWFLAKE_RUN_MANIFEST_TASK`. Confirm no run is `EXECUTING` in `TASK_HISTORY`.
2. **Pin UTC:** `ALTER TASK ... SET TIMEZONE = 'UTC'` on both. This matches the merged code.
   - Do **not** run `deploy-snowflake-stack.sh`: it would also set the manifest task's schedule
     to 1 minute (Ticket 23).
   - Do not re-apply `13_silver_landing_ingest.sql` either: it resumes the task at once.
   - Afterwards, `terraform plan` on `snowflake/accounts/prod` should show no change for
     `manifest_processor`.
3. **Clone** each of the 20 tables in the correction table into a separate backup schema (D2),
   e.g. `EDGARTOOLS_PROD.T22_TIMESTAMP_BACKUP`, so no loader or reconciler reads the clones.
   `EDGARTOOLS_PROD_LOADER` has `CREATE SCHEMA` on `EDGARTOOLS_PROD` (checked 2026-09-14).
4. **Correct:** one statement per column in the correction list, run as `EDGARTOOLS_PROD_LOADER`.
   All 60 tables in both schemas are owned by `ACCOUNTADMIN`. The loader has `UPDATE` on the two
   tables checked (landing `SEC_COMPANY_TICKER`, source `SEC_THIRTEENF_HOLDING`). In step 0,
   confirm it has `UPDATE` on the other 18 as well.
   ```sql
   UPDATE EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.SEC_COMPANY_TICKER
   SET last_synced_at = to_timestamp_tz(
         to_varchar(last_synced_at, 'YYYY-MM-DD HH24:MI:SS.FF9') || ' +0000',
         'YYYY-MM-DD HH24:MI:SS.FF9 TZHTZM')
   WHERE to_varchar(last_synced_at, 'TZH:TZM') IN ('-07:00', '-08:00');
   ```
   Each statement's updated-row count must equal the step 0 count for that column.
5. **Relabel the MDM markers** with the Postgres statement above (D3).
6. **Verify:**
   - The offset count shows 0 values at `-07:00`/`-08:00` in the correction list.
   - The five excluded columns are unchanged.
   - `SHOW PARAMETERS LIKE 'TIMEZONE' IN TASK` returns `UTC` for both tasks.
   - Refresh the affected silver and gold dynamic tables (D4).
7. **Resume both tasks.** On the next landing load, new rows show offset `Z` with a time close to
   the run id's epoch. Re-run the one-row loop as a second check.
8. **Drop the clones** after the retention period chosen in D2.

**Rollback:**
- Before step 7: `ALTER TASK ... UNSET TIMEZONE`.
- To restore data, copy rows back from the clones with `INSERT OVERWRITE INTO <table> SELECT * FROM <clone>`.
  `SELECT *` is safe here only because a clone has the same column order as its table. `INSERT`
  maps columns by position, so any other source needs named column lists.
  Do not use `CREATE OR REPLACE ... CLONE`: replacing a table drops its grants and breaks the
  dynamic tables that read it.
- Restore the checkpoint rows from the step 0 copy.

### Decisions for the operator

**Accepted 2026-09-14:** the operator took the recommended option for all five (D1–D5). The
window itself has not run and still needs its own go-ahead. D5 is a separate small change, not
yet made.

- **D1 — One window.** Recommended: suspend the tasks, pin UTC, correct, relabel, then resume.
  Alternative: deploy now and correct later. That leaves mixed offsets, which MDM compares as
  text.
- **D2 — Backup.** Recommended: zero-copy clones in a separate schema, dropped after 7 days.
  Alternative: Time Travel only (1 day).
- **D3 — MDM markers.** Recommended: relabel the stored strings. Alternatives:
  - Clear the three markers. The next run then re-scans those relationship types in full,
    including `INSTITUTIONAL_HOLDS` over 6.8 million holdings. That is idempotent but slow.
  - Wait for the monthly reconciliation pass, which leaves skipped rows until then.
- **D4 — Downstream refresh.** Recommended: refresh the silver dynamic tables for the 15 corrected
  landing tables right after step 4, then the gold tables. Alternative: wait. Silver catches up
  within 6 hours; gold only on the next manifest run.
- **D5 — Manual `CALL` scripts.** Recommended: add `ALTER SESSION SET TIMEZONE = 'UTC'` before the
  `CALL`s in `scripts/test/smoke-test-single-cik.sh`, `scripts/test/ownership-neo4j-e2e-quick.sh`
  and `scripts/verify-pr1/04_smoke_merge_proc.sh` (a small, separate change). Alternative: leave
  the gap documented here.
