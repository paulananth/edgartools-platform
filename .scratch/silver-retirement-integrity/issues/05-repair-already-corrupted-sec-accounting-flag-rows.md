# 05 — Repair already-corrupted `sec_accounting_flag` rows in Snowflake

**What to build:** A one-off backfill sweep that repairs
`EDGARTOOLS_SILVER.SEC_ACCOUNTING_FLAG` rows that already lost their
`auditor_name`/`auditor_pcaob_id`/`auditor_location`/`icfr_attestation`/
`auditor_changed`/`fiscal_year`/`period_end`/`form_type`/`parser_version`/
`ingested_at`/`valid_from`/`valid_to`/`is_current` columns to the thin-row
collapse bug fixed in
[Ticket 04](04-thin-backfill-nulls-other-columns.md).

**Blocked by:** None — can start immediately (Ticket 04's write-side fix is
independent of this repair; this ticket only cleans up rows already written
before that fix shipped).

**Status:** open

## Question

Ticket 04 fixed `update_accounting_flag_scores` so it stops *writing* thin
landing-zone rows going forward, but the fix is forward-only — any row whose
forensic-score backfill happened before this fix deployed is still sitting
in `EDGARTOOLS_SILVER.SEC_ACCOUNTING_FLAG` (and anything gold/dbt builds on
top of it) with those columns silently NULLed, per Ticket 04's own
"Impact" section: "Live in production today... not a hypothetical risk, an
actual data-quality gap for however many rows this backfill has already
touched."

This is candidate fix (C) from Ticket 04, explicitly deferred there rather
than attempted inline.

What needs deciding:

1. **Detect the corrupted set.** The local DuckDB `sec_accounting_flag`
   table was never corrupted (Ticket 04's own "Reproduction" section
   confirmed this — a plain SQL `UPDATE` only touches the columns named in
   its `SET` clause, so local canonical was always safe). The authoritative,
   uncorrupted values for every affected row already exist in local silver
   — the repair is a right-side-only backfill, not a "reconstruct lost
   data" problem.
2. **Detect which Snowflake rows are actually affected.** Likely: any
   `SEC_ACCOUNTING_FLAG` row where a forensic score is non-NULL but
   `auditor_name`/`fiscal_year`/`form_type`/etc. are NULL despite the
   underlying filing plausibly having them (a `10-K` accession should
   always have a `form_type`, so any NULL `form_type` row with a non-NULL
   score is a strong, cheap signal).
3. **Repair mechanism.** Simplest: re-run the full-row landing export for
   every already-backfilled `(cik, accession_number)` pair (a full re-read
   of local silver's `sec_accounting_flag` for those keys, emitted through
   the same landing-export path Ticket 04's fix now uses) — the newest
   `parse_sequence` after the repair write wins the dbt `QUALIFY` collapse
   with a full row, self-healing without needing a one-off SQL `UPDATE`
   against Snowflake directly. Watch the interaction with Ticket 03's
   retirement-conflict-resolution policy once that lands — a repair write
   for an already-retired (`is_current = FALSE`) row needs to not
   accidentally reinstate it.
4. **Verification.** Confirm live in `EDGARTOOLS_SILVER.SEC_ACCOUNTING_FLAG`
   (or the equivalent gold table) that a sample of previously-NULL columns
   are populated again after the repair, for a few known-affected
   `(cik, accession_number)` pairs.

## Answer

Not yet answered.
