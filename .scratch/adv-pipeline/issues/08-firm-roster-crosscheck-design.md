# 08 — Design the Firm Roster CSV Completeness Cross-Check

Type: grilling
Status: open
Blocked by: none
Blocks: none

## Question

Ticket 02 decided the Firm Roster CSV (sec.gov's true full-universe snapshot,
aggregate-only private-fund counts — e.g. `Count of Private Funds - 7B(1)`,
`Total number of Hedge funds`) gets ingested alongside the richer `advFilingData` feed, as
a parallel completeness cross-check: flag firms where the `advFilingData`-derived fund
count doesn't match the Firm Roster's aggregate count.

Not yet decided — this ticket resolves:

1. **Where does the cross-check live?** A new silver table populated by a new parser
   (mirroring `adv_bulk_ingest.py`'s shape), a dbt/gold-layer reconciliation view over
   existing silver tables plus a new raw Firm Roster table, or something else?
2. **What happens on a mismatch?** Ticket 02's map Notes carry a hard requirement that
   entity resolution/graph sync must not be gated on private-fund-detail fidelity — so a
   mismatch should not block MDM/graph sync for that firm. Does it become a queryable flag
   an operator checks later, a logged warning, a dashboard metric, or something else?
3. **Cadence.** The Firm Roster CSV is monthly per ticket 01's research — does the
   cross-check run every time a Firm Roster file is fetched, or on a different cadence?
4. **Scope of the 448-column registered-adviser CSV / 171-column exempt-adviser CSV.**
   Only the aggregate private-fund columns are needed for this cross-check (per ticket
   01's Q3 findings) — does the parser extract only those ~8 columns plus firm identity
   (CRD), or the full row for potential future use? Narrower scope is less to build and
   maintain; full-row parsing front-loads work for uses not yet identified.

## Answer

(pending)
