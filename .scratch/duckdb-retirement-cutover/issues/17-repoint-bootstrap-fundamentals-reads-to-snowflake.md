# 17 — Repoint bootstrap-fundamentals's local-DuckDB reads to Snowflake

**What was found:** live during fundamentals-daily-integration map Tickets
02/03's live-AWS verification (2026-09-11), a real `bootstrap-fundamentals
--mode per-filing` run against a CIK with a real, confirmed 8-K on file
(CIK 908311) returned `filings_scanned: 0` and completed in 0.61s. A real
`--mode entity-facts` run against a CIK that already has 17,909
`sec_financial_fact` rows at the current parser version (CIK 75288) still
re-fetched the full companyfacts JSON from SEC (`network_fetches: 1,
silver_skips: 0`) instead of skipping.

**Root cause:** Ticket 10 (`10-atomic-write-path-cutover.md`) removed local-
DuckDB hydration from the production write path and repointed two read call
sites to Snowflake (`_company_identity_ciks_snowflake`,
`_snowflake_distinct_values` in `warehouse_orchestrator.py`) before flipping
the write path off DuckDB. It missed a third and fourth: `edgar_warehouse/
application/commands/bootstrap_fundamentals.py` sets `source = db` (the
per-filing/thirteenf case) and `edgar_warehouse/application/workflows/
fundamentals_ingest.py`'s `has_companyfacts_at_version` (the entity-facts
case) both still read from the local `db` — a fresh, empty DuckDB every
single task run, since nothing hydrates it anymore. Confirmed live in prod
since the Ticket 10 deploy (2026-09-07, image `sha-0d7b73eb7bb3`,
`edgartools-prod-large:293`/`edgartools-prod-medium:298`):

- `per-filing`/`thirteenf` have processed **zero filings on every run**,
  silently (`exit 0`, no error).
- `entity-facts`'s existing "already have it at this parser_version, skip"
  gate has been a **permanent no-op** — every CIK's full companyfacts JSON
  is re-fetched from SEC on every single run.

**Ruled out:** bookkeeping (Postgres, `BOOKKEEPING_TABLES` in
`edgar_warehouse/bookkeeping/models.py`) is not the fix — it holds exactly
10 operational tables (sync-state, checkpoints, leases, run/parse audit,
daily-index staging), never `sec_company_filing`/`sec_filing_attachment`/
`sec_raw_object`/`sec_financial_fact`, which are real content, not run
metadata.

**Confirmed the fix target is live and populated** (queried
`EDGARTOOLS_PROD.EDGARTOOLS_SILVER` directly, 2026-09-11):
`SEC_COMPANY_FILING` (6,773,967 rows; CIK 908311 has 1,006 real filings
there), `SEC_FINANCIAL_FACT` (434,805 rows; CIK 75288 has 17,909 rows at
`parser_version=1`), `SEC_FILING_ATTACHMENT` (436,287), `SEC_RAW_OBJECT`
(372,225), `SEC_THIRTEENF_HOLDING` (6,799,919) — all real, all populated.
`edgar_warehouse/silver_support/snowflake_reader.py`'s `SnowflakeSilverReader`
already exposes the exact `.fetch(sql, params) -> list[dict]` duck-type
these read call sites already expect (same interface `SilverDatabase.fetch`
provides), and is already used in production by MDM's reader.

## What to build

1. `bootstrap_fundamentals.py`: for `per-filing`/`thirteenf`, build a
   `SnowflakeSilverReader` connected against `EDGARTOOLS_SILVER` (mirroring
   `_mdm_silver_reader_settings`'s pattern — likely needs its own role, not
   necessarily `EDGARTOOLS_PROD_MDM_SILVER_READER`, since this is a
   warehouse-role task, not MDM) and pass it as `source` instead of `db`.
   `db` (local DuckDB) stays the write target, unchanged.
2. `fundamentals_ingest.py`: `has_companyfacts_at_version` (existing) and
   `get_ciks_with_new_qualifying_filing` (fundamentals-daily-integration
   Ticket 03) both need to read via the same Snowflake reader, not local
   `db`, for their skip/trigger checks to mean anything in production.
3. fundamentals-daily-integration Tickets 02/03's own two new tables
   (`sec_fundamentals_processed_accession`, `sec_entity_facts_refresh_
   watermark`) need real Snowflake persistence: track their writes via
   `LandingExportBuffer`/`@track_landing_rows` (the existing mechanism
   `merge_accounting_flags` etc. already use to reach the Snowflake landing
   zone) and read their skip-check state back from Snowflake, not local
   DuckDB — the local tables/methods stay as the write-side staging
   mechanism, just no longer double as the read source of truth.
4. Confirm (do not assume) which Snowflake role `bootstrap-fundamentals`
   should connect as — least-privilege read-only, scoped appropriately for
   a warehouse-role ECS task, not necessarily reusing MDM's dedicated role.

## Blocked by

None — can start immediately. (Blocks: fundamentals-daily-integration
Tickets 02/03's own "verified live" acceptance criteria, since neither can
be meaningfully verified in production until this lands.)

## Acceptance

- [ ] A live `bootstrap-fundamentals --mode per-filing` run against a real
      CIK with a known filing on file (e.g. CIK 908311) processes it
      (`filings_scanned > 0`, `filings_parsed > 0`), not `filings_scanned: 0`.
- [ ] A live `bootstrap-fundamentals --mode entity-facts` run against a CIK
      that already has facts at the current parser_version and no new
      qualifying filing skips the network call (`silver_skips: 1,
      network_fetches: 0`).
- [ ] A live `bootstrap-fundamentals --mode thirteenf` run against a real
      13F-HR filer CIK processes it.
- [ ] fundamentals-daily-integration Ticket 02's skip-already-processed
      behavior and Ticket 03's new-qualifying-filing trigger both verified
      live end-to-end (first run processes/fetches, second run skips, and
      the skip state is confirmed to have actually persisted to Snowflake,
      not just the local task's own disk).
- [ ] `/gof-refactor-reviewer` consulted before editing
      `bootstrap_fundamentals.py`/`fundamentals_ingest.py`/`silver_store.py`
      (repo hard rule).
- [ ] `/code-review` (Standards, Spec, GoF) run before this ticket's PR is
      considered ready.
