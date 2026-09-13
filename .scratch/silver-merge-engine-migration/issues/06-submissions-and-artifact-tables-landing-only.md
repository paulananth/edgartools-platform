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

**Done:** as Ticket 04, per table or per group; a live `daily_incremental` run showing landing
rows for every table in the group.

**Blocked by:** [Ticket 04](04-per-filing-tables-landing-only.md).
