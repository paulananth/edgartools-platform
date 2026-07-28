# 05 — Reconcile Ticket 21 and the Adviser-Fund Source Contract

Type: task
Status: resolved
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

Ticket 02 found two real gaps, so all three reconciliation steps did real work (none
were no-ops):

1. **`adviser-fund-source-contract.md` updated** — added an "Addendum: rolling-window
   acquisition and Firm Roster completeness control" section documenting (a) the
   release source is a monthly filing-activity delta feed requiring a 13-month rolling
   union with latest-per-CRD dedup, not a single full-universe snapshot, and (b) the
   Firm Roster CSV is adopted as a parallel completeness cross-check, explicitly scoped
   out of the applicability ledger/graph contract/GO acceptance. The contract's core
   identity/resolution/graph rules (CRD/PFID, no name-only matching, `MANAGES_FUND`
   shape) are unchanged — confirmed correct by ticket 01/02, not superseded.
2. **Ticket 21 annotated** (not reopened — its implementation was correct, only the
   2026-07-24 blocker doc's diagnosis was wrong) with a pointer to ticket 01's finding
   and this map, so future readers don't mistake the corrected blocker doc for evidence
   ticket 21's implementation was broken.
3. **Blocker doc corrected via append** — `adv-bulk-ingest-format-change-2026-07-24.md`
   now has a "Correction (2026-07-27)" section at the top stating the format-change
   premise was wrong (wrong SEC product staged, not a real SEC change), while leaving
   the original diagnosis text below it untouched as a historical record.
