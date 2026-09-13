# 06 — Make the submissions/artifact-path tables landing-only

**Type:** task (likely splits once started — this is the largest remaining set)

## Question

Everything left in `silver_store.py` after Tickets 02–05: `merge_company`, `merge_addresses`,
`merge_former_names`, `merge_submission_files`, `merge_filings`, `merge_current_filing_feed`,
`replace_company_tickers`, `upsert_raw_object`, `merge_filing_attachments`, `upsert_filing_text`,
the ownership trio, the ADV five, `merge_subsidiary_evidence`, `merge_auditor_report_evidence`,
`merge_pcaob_firm_identities`. These are `daily_incremental`/`load_history`'s own write path
(`_execute_warehouse_bronze_capture`), so unlike 02–05 this touches the scheduled pipeline.

**Before switching any of them, the exhaustive-reader grep Ticket 01 learned the hard way:**
`warehouse_orchestrator.py:4688` (`parse-ownership-bronze` reads `sec_company_filing` locally —
wired into the deploy script, a live no-op today since the table is always empty),
`reference_catalog_silver_acceptance.py` (three local reads, the same read-back-verify shape
Ticket 02 deleted), `mdm/adv_bulk.py` (which reader is `silver` there?), and the five
`drive-*-discovery` drivers (they call these writers; they are NOT to be deleted — the
change-propagation map owns their future, see the map's Notes).

**Notes from Ticket 04's GoF review (2026-09-13), for whoever picks this up:**

- None of this ticket's tables has `ingested_at`; they stamp `last_sync_run_id` (and company,
  filings and tickers also `last_synced_at = now`). That stamp depends on `sync_run_id`, so it
  is a method taking an argument (e.g. `_sync_run_stamp(sync_run_id)`), not a staticmethod;
  `merge_company`'s `first_sync_run_id` fallback goes in per-call `defaults`. The helper's
  signature needn't change.
- None of these writers' `values_fn`s replace a present value (no `bool()`/`or ""`), so no
  call-site coercion comprehensions are expected.
- `merge_filing_attachments` and `merge_current_filing_feed` reject any *falsy* required value,
  including `""`; the helper's NOT NULL check only rejects `None`. Decide parity (call-site
  pre-check vs. a stricter helper check) explicitly, don't lose it silently.

**Done:** as Ticket 04, per table or per group; a live `daily_incremental` run showing landing
rows for every table in the group.

**Blocked by:** [Ticket 04](04-per-filing-tables-landing-only.md).
