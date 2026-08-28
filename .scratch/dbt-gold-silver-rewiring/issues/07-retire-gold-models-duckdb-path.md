# 07 — Retire the Orphaned Dimensional Builders in source_dimensional_export.py

**Corrected 2026-08-28** — this ticket's original text (written 2026-08-16,
the same day as Tickets 01-06) referenced `edgar_warehouse/serving/
gold_models.py`, `_gold_table_builders()`, `iter_gold_tables()`, and
`build_gold()`. None of those names exist anymore: the file was renamed to
`edgar_warehouse/serving/source_dimensional_export.py` on 2026-08-19
(`docs+refactor: fix stale CLAUDE.md pointers, rename gold_models.py off its
misleading name`) because it was never a gold-layer builder — it builds
`EDGARTOOLS_SOURCE`'s Python dimensional export, which CLAUDE.md and
change-propagation's own Ticket 07 both describe as "legitimate/permanent."
The original text, if followed literally, would send an agent hunting for
deleted function names — or worse, risk deleting the wrong scope in a file
that mixes genuinely-orphaned functions with genuinely-still-live ones.
Corrected in place after checking live code and the current dbt SQL
directly, not just re-reading the original ticket's premise.

**What to build:** `_source_export_table_builders()`
(`source_dimensional_export.py:1355`) registers 28 builder entries. Of
those, **23 are safe to delete** — confirmed via a full grep of
`infra/snowflake/dbt/edgartools_gold/models/` for
`source("edgartools_source", ...)`: exactly 4 hits remain
(`EARNINGS_CALENDAR`, `TRANSCRIPT_EVENTS`, `CONSENSUS_ESTIMATES`,
`SERVING_REFRESH_STATUS`), and none of them are fed by the 23 builders
below — every dbt gold model that used to read them now `ref()`s dbt
silver directly (Tickets 02-06).

Delete these 23 `_build_*` functions and their entries in
`_source_export_table_builders()`: `_build_dim_company`, `_build_dim_form`,
`_build_dim_date`, `_build_dim_filing`, `_build_fact_filing_activity`,
`_build_dim_party`, `_build_dim_security`, `_build_dim_ownership_txn_type`,
`_build_dim_geography`, `_build_dim_disclosure_category`,
`_build_dim_private_fund`, `_build_fact_ownership_transaction`,
`_build_fact_ownership_holding_snapshot`, `_build_fact_adv_office`,
`_build_fact_adv_disclosure`, `_build_fact_adv_private_fund`,
`_build_sec_financial_fact`, `_build_sec_thirteenf_holding`,
`_build_sec_financial_derived`, `_build_fact_earnings_release`,
`_build_fact_guidance`, `_build_fact_executive_record`,
`_build_fact_accounting_flag`. All 23 take a live DuckDB `conn` parameter
threaded from `SilverDatabase`/`ShardedSilverReader` — this is the actual
"DuckDB-reading" dependency this ticket exists to retire.

**Explicitly preserve — do not delete:**
- `build_earnings_calendar_table_from_rows`, `build_consensus_estimates_table_from_rows`,
  `build_transcript_events_table_from_rows` — feed 3 of the 4 still-live
  `source()` references above (the fourth, `SERVING_REFRESH_STATUS`, isn't
  built by this file at all). No DuckDB dependency (take plain `rows`, not
  `conn`).
- `_build_sec_subsidiary_evidence`, `_build_sec_auditor_report_evidence`,
  `_build_sec_employment_event`, `_build_sec_adv_firm_roster`,
  `_build_sec_adv_private_fund_passthrough` — the 5 entries the file's own
  comment (`source_dimensional_export.py:1384-1388`) documents as already
  reading `EDGARTOOLS_SILVER` directly (Ticket 06, already resolved). No
  DuckDB dependency, no `conn` argument passed to any of them.
- **Left unresolved, out of scope for this ticket:** `build_ticker_reference_table`.
  Its dbt consumer (`ticker_reference.sql`) has moved to
  `ref("sec_company_ticker")` (confirmed live), no longer
  `source("edgartools_source", "TICKER_REFERENCE")` — suggesting it may
  also be dead, but this ticket does not audit whether anything outside
  dbt still reads `EDGARTOOLS_SOURCE.TICKER_REFERENCE` directly. Leave the
  function and its `warehouse_orchestrator.py:907` `seed-universe` call
  site untouched; a future ticket should confirm before deleting it.

**Follow-on signature simplification:** once only the 5 Snowflake-reading
builders remain, none of them use the `conn` argument
`_source_export_table_builders(conn)` threads through — drop that
parameter, and drop the now-pointless `get_connection(db)` call in
`iter_source_export_tables(db)`/`build_source_export(db)`
(`source_dimensional_export.py:1402-1419`), so these two functions no
longer accept a `SilverDatabase`/`ShardedSilverReader` argument at all.
Update the call site in `warehouse_orchestrator.py` (~line 666-667,
`for table_name, table in iter_source_export_tables(db): ...`) to match the
new signature.

**`validate_data_quality.py` needs a real rewrite, not just a rename.**
`_check_gold_vs_silver` (`validate_data_quality.py:222-266`) calls
`build_source_export(db)` and diffs row counts against
`_DIRECT_GOLD_SILVER_TABLES` — every table that mapping checks is one of
the 23 builders being deleted here, so after this ticket lands
`build_source_export(db)` returns none of them and this check would
silently validate nothing. Convert it to query live Snowflake
`EDGARTOOLS_GOLD` tables directly (via the existing Snowflake connection
this command already has) instead of materializing the Python dict — this
was the original ticket's stated intent; it just didn't have the "current
check would go silently empty, not error" mechanism spelled out.

**Blocked by:** 02, 03, 04, 05, 06 (all resolved)

**Status:** ready-for-agent

- [ ] The 23 orphaned DuckDB-coupled builder functions and their
      `_source_export_table_builders()` entries are deleted
- [ ] `build_earnings_calendar_table_from_rows`,
      `build_consensus_estimates_table_from_rows`,
      `build_transcript_events_table_from_rows`, the 5 Ticket-06
      Snowflake-reading builders, and `build_ticker_reference_table` all
      still exist and are unmodified
- [ ] `_source_export_table_builders`/`iter_source_export_tables`/
      `build_source_export` no longer take a `conn`/`db` argument; the
      `warehouse_orchestrator.py` call site is updated to match
- [ ] `validate_data_quality.py`'s `_check_gold_vs_silver` validates
      against live Snowflake `EDGARTOOLS_GOLD` tables directly, not
      `build_source_export()`'s output
- [ ] The dead `build_gold`-re-exporting shim `edgar_warehouse/gold.py` is
      deleted (confirmed zero importers repo-wide; note
      `application/workflows/serving_publish.py`, named in this ticket's
      original text, no longer exists at all — already gone, nothing to do
      there)
- [ ] No remaining `import duckdb` reference anywhere in
      `edgar_warehouse/serving/`
- [ ] Full test suite green
