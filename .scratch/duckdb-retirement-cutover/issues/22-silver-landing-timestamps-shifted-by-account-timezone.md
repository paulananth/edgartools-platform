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

**Still open:**
1. Deploy: apply `13_silver_landing_ingest.sql` and the `native_pull` Terraform to prod (needs
   operator go-ahead), then confirm with the loop and one real landing load that new rows carry
   the true UTC time.
2. Correct rows already loaded in `EDGARTOOLS_SILVER_LANDING` and `EDGARTOOLS_SOURCE` (needs
   explicit operator go-ahead; prod data). Only after step 1, so no shifted row lands after the
   correction.
3. Question 3 above: consumers that mix these timestamps with a real clock or another store.
