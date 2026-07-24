# 05 — Reconcile Ticket 21 and the Adviser-Fund Source Contract

Type: task
Status: open
Blocked by: 02
Blocks: none

## Task

Formally reconcile the release-readiness tracker with ticket 02's decision,
per this map's explicit ownership of that reconciliation (2026-07-24):

- Update or supersede
  [`docs/release-readiness/adviser-fund-source-contract.md`](../../docs/release-readiness/adviser-fund-source-contract.md)
  to reflect the real current SEC bulk format and the private-fund-detail
  strategy ticket 02 chose (it currently documents the old relational
  archive and forbids name-only fund identity — language that may no longer
  be satisfiable if bulk data truly only offers aggregate counts).
- Reopen or annotate
  `.scratch/release-readiness/issues/21-implement-authoritative-form-adv-private-fund-ingestion.md`
  (currently `Status: resolved`) to reflect that its implementation
  (`adv_bulk_ingest.py` as of commits `ddc24d3`/`846d648`/`4f4e1a9`) does not
  match the live SEC format — link back to this map and ticket 02's
  decision as the superseding record.
- Note the outcome in `docs/release-readiness/adv-bulk-ingest-format-change-2026-07-24.md`
  (append, don't rewrite) so that blocker doc's history stays intact.

## Answer

(pending)
