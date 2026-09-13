# 04 — Make the per-filing fundamentals tables landing-only

**Type:** task

**Status:** resolved (2026-09-13). Not yet live-verified.

## Question

`bootstrap-fundamentals --mode per-filing` writes `sec_earnings_release`, `sec_executive_record`,
`sec_employment_event`, `sec_guidance_fact` and `sec_guidance_fact_reject` through DuckDB
`merge_*` methods whose local write nothing reads back (confirmed 2026-09-13: this mode only
ever writes via `db.merge_*`; every read goes through `source`, the Snowflake reader). Same
shape as [Ticket 02](02-delete-merge-financial-facts-local-write.md).

**What to build:** each writer becomes a `_record_landing_passthrough` call (the helper
Tickets 02/03 introduced) — old `values_fn` defaults as `defaults`, `ingested_at` as `stamp`
(these tables have `ingested_at DEFAULT NOW()` and no validity trio), NOT NULL enforced by
raising. Drop the `@track_landing_rows` decorators they replace. Keep the DuckDB DDL. Confirm
the dbt silver models' collapse keys match each table's old `ON CONFLICT` key before
switching (the entity-facts trio matched; assume nothing).

**Explicitly not this ticket:** `mark_fundamentals_accession_processed` and its read in
`fundamentals_ingest._get_processed_accessions` — that marker's move stays on the
bootstrap-fundamentals-crash-resume map.

**Done:** rewritten tests (same "update, don't delete coverage" bar as 02/03), full suite
green, 3-axis `/code-review`, and a live prod per-filing run showing landing rows.

**Blocked by:** none — frontier.

## Answer

- `merge_earnings_releases`, `merge_guidance_facts`, `merge_guidance_fact_rejects`,
  `merge_executive_records`, `merge_employment_events` now call `_record_landing_passthrough`;
  their `@track_landing_rows` decorators, `_merge_rows` SQL and `values_fn` lambdas are gone.
  `stamp=self._ingested_at_stamp()` (new; `_current_row_stamp` now builds on it). DuckDB DDL
  kept (the helper reads its NOT NULL set).
- Old `values_fn` coercions that replaced a *present* value are applied at the call site
  before the passthrough, since `defaults` only fills absent keys: `bool()` on
  `has_non_gaap`/`has_guidance`/`is_non_gaap`, `accession_number or ""` on guidance facts and
  rejects. `confidence` defaults to `"medium"` when absent. Every old `r["key"]` lookup is a
  NOT NULL column, so it now raises `ValueError` before recording (was `KeyError`/DuckDB
  constraint error).
- **A real fix, not just parity:** `@track_landing_rows` recorded the caller's raw rows — no
  `ingested_at`, no coercions. So landing `ingested_at` was NULL for all five tables, and
  MDM's EMPLOYED_BY derivation (`pipeline.py`, `WHERE ingested_at > ?` on
  `sec_executive_record`/`sec_employment_event`) could not see those rows through its
  incremental watermark; a guidance row with `accession_number=None` could also fail the
  Snowflake NOT NULL load for its whole Parquet file.
- **Collapse keys verified:** all five dbt silver models partition on exactly the old
  `ON CONFLICT` key (`sec_guidance_fact_reject` had none; its model is a plain view). Three
  columns the old `DO UPDATE SET` never touched — first-insert-wins in DuckDB, last-seen in
  dbt — are `sec_earnings_release.filing_date`, `sec_executive_record.fiscal_year`,
  `sec_employment_event.cik`. Pre-existing (landing already received every raw write and dbt
  already took the latest), not introduced here; none varies per key in practice.
- Second production caller `warehouse_orchestrator._parse_item_502_accession` (scheduled
  Branch A path) only uses the returned count; nothing on it reads `sec_employment_event`
  back. `mark_fundamentals_accession_processed` untouched, as scoped.
- Tests: per-filing cases added to `test_fundamentals_landing_passthrough.py` (landing-only +
  `ingested_at`, `ingested_at` advances per write, each coercion, NOT NULL raising); the four
  DuckDB bump tests removed from `test_silver_store_ingested_at_bump.py`; the ShardedSilverReader
  allowlist tests and the schema-migration tests now share `tests/support/silver_rows.py`.

**Still owed:** a live prod `bootstrap-fundamentals --mode per-filing` run showing landing rows
with `ingested_at` populated.
