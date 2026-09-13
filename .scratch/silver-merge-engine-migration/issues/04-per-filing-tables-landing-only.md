# 04 — Make the per-filing fundamentals tables landing-only

**Type:** task

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
