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
