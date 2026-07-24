# 05 — Reconcile Ticket 21 and the Adviser-Fund Source Contract

Type: task
Status: open
Blocked by: 02
Blocks: none

## Task

**Lighter than originally scoped, per ticket 01's correction (2026-07-24):**
the parser and contract were never actually broken — last session's
"zero rows" finding came from fetching the wrong SEC product
(`sec.gov`'s Firm Roster CSV) instead of the correct one
(`adviserinfo.sec.gov`'s monthly `advFilingData` feed, which
`adv_bulk_ingest.py`'s existing regexes already match). Formally reconcile
the release-readiness tracker with ticket 02's decision:

- Update `adviser-fund-source-contract.md` only if ticket 02 finds a real
  gap (e.g. the rolling-window mechanics for a monthly-delta feed, or
  whether the Firm Roster CSV's aggregate columns get adopted as a
  cross-check) — otherwise the contract's core assumptions (relational
  format, PFID identity, no name-only matching) stand as originally
  approved and this step may be a no-op.
- Annotate (not necessarily reopen)
  `.scratch/release-readiness/issues/21-implement-authoritative-form-adv-private-fund-ingestion.md`
  (currently `Status: resolved`) with a pointer to this map and ticket 01's
  finding, so future readers don't mistake last session's now-corrected
  "blocker" doc for evidence Ticket 21's implementation was wrong — it
  wasn't; it was fed the wrong file in a debugging session, never in
  production.
- Note the outcome in `docs/release-readiness/adv-bulk-ingest-format-change-2026-07-24.md`
  (append, don't rewrite) so that blocker doc's history stays intact —
  including the correction itself, since that doc currently states the
  format changed, which ticket 01 found to be false.

## Answer

(pending)
