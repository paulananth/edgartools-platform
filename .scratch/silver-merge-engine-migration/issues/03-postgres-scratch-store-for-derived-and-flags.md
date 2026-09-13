# 03 — Build the Postgres-backed scratch store for `merge_accounting_flags`/`merge_financial_derived`

**Type:** task

## Question

[Ticket 01](01-choose-replacement-engine-and-migration-order.md)'s Final Answer decided:
`sec_accounting_flag`/`sec_financial_derived`'s local DuckDB merge writes move to a new,
dedicated Postgres-backed scratch store (not `BookkeepingStore` itself, not an in-process
Python accumulator), reusing the same Postgres connection/instance/DSN convention as
`BookkeepingStore` (the `bookkeeping` database on the `EDGARTOOLS_PROD_MDM` Snowflake-hosted
Postgres instance). Rows are upserted by business key, never purged.

**What to build:**

- A new store class (name/module location not pre-decided — natural candidates: alongside
  `edgar_warehouse/bookkeeping/store.py` as a sibling, or colocated with
  `fundamentals_ingest.py`; consult `/gof-refactor-reviewer` before deciding, per this map's
  Notes) exposing at minimum:
  - An upsert for `sec_financial_derived` rows (mirrors `merge_financial_derived`'s current
    column set — see `silver_store.py:3358`'s staging DDL for the full 33-column shape —
    keyed the same way DuckDB's `ON CONFLICT` clause is, business-key not surrogate).
  - An upsert for `sec_accounting_flag` rows (mirrors `merge_accounting_flags`'s current
    shape, `silver_store.py:3599`).
  - A read matching `backfill_accounting_flags`'s existing query shape: `sec_financial_derived`
    rows for one CIK, `fiscal_period = 'FY'`, ordered by `fiscal_year` — same columns that
    function's cross-period Beneish/Altman/Piotroski math reads today.
  - An update matching `update_accounting_flag_scores`'s existing contract: matched by
    `(cik, accession_number)`, COALESCEs `None` against the existing stored value (preserve
    this exact semantic — `accounting_flags.py`'s own comment explains why: a `None` for an
    earlier fiscal year must not clobber a previously-computed score).
- Migration/schema DDL for the new table(s), following this repo's existing Postgres migration
  conventions (see `edgar_warehouse/bookkeeping/migrations/` or `mdm/migrations/` for the
  pattern to mirror) — idempotent, populated-table-tested per the migration-010/011 lesson in
  CLAUDE.md (test against a table that already has rows, not just an empty one).
- Rewire `fundamentals_ingest.run_bootstrap_entity_facts` to call the new store's upserts
  instead of `db.merge_accounting_flags`/`db.merge_financial_derived`, and rewire
  `bootstrap_fundamentals.py`'s `backfill_accounting_flags` call site (and
  `accounting_flags.backfill_accounting_flags` itself) to read from the new store instead of
  `silver.fetch(...)` against local DuckDB.
- `landing_export.record(...)` calls for both tables must be preserved exactly as they are
  today (unaffected by the storage-engine swap — they already receive the same Python row
  dicts before/independent of any DuckDB write).
- Confirm no other caller reads `sec_accounting_flag`/`sec_financial_derived` from local DuckDB
  within the same process before removing those DuckDB writes — repeat the same
  exhaustive-grep discipline Ticket 01's investigation used (the gap that caused this whole
  ticket's back-and-forth was checking known callers instead of grepping every table for every
  reader before declaring something dead).

**"Done" bar** (per Ticket 01): equivalent regression coverage to the existing tests exercising
`merge_accounting_flags`/`merge_financial_derived`/`backfill_accounting_flags`/
`update_accounting_flag_scores` (update for the new store, don't delete the coverage), a
Postgres-backed integration test proving the upsert/read/update round trip against a real
(not SQLite-mocked) Postgres instance — per CLAUDE.md's repeated lesson that SQLite can't model
real constraint-timing/upsert semantics — plus a live-verified production write.

## Blocked by: [Ticket 02](02-delete-merge-financial-facts-local-write.md) is not a hard
dependency (the two tickets touch different tables), but doing 02 first is recommended per
Ticket 01's migration order (simpler, lower-risk, ships first, and de-risks the shared
`_merge_rows_bulk` code path before touching the harder pairing here).
