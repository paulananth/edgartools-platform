# 08 — Design the Firm Roster CSV Completeness Cross-Check

Type: grilling
Status: resolved
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

Grilled with the user 2026-07-27, one question at a time. All four settled:

1. **Cross-check layer: new raw silver table + dbt gold-layer reconciliation view.** A
   narrow new parser (mirroring `adv_bulk_ingest.py`'s shape) writes a new silver table,
   `sec_adv_firm_roster` (CRD, `dataset_period`, aggregate private-fund columns). A new
   dbt gold model, `adv_fund_count_reconciliation`, joins it against the existing
   `advFilingData`-derived fund counts (from `sec_adv_private_fund`) and computes the
   mismatch. Keeps the comparison declarative and in the same layer as the platform's
   other gold-layer reconciliations, rather than duplicating comparison logic in a new
   Python step.
2. **On mismatch: the gold view itself, plus a Streamlit dashboard panel.** No alerting,
   no blocking — `adv_fund_count_reconciliation` is queryable
   (`WHERE mismatch`), and a summary panel ("Firm Roster cross-check: N firms mismatched
   (X%)") surfaces it in the existing dashboard without requiring a manual query. Per
   ticket 02's map-level hard requirement, this is purely additive visibility — MDM entity
   resolution and graph sync are never gated on it.
3. **Cadence: fetch monthly, cross-check recomputes on every fetch.** Firm Roster fetch
   mirrors `daily_incremental`'s existing local-check-first pattern from ticket 06 — a
   daily invocation that no-ops on every day the current month's roster is already
   ingested, and only does real work on the ~1 day/month a new snapshot lands. The gold
   view recomputes on its own normal dynamic-table refresh schedule (same as every other
   `EDGARTOOLS_GOLD` table) — no separate cadence control needed.
4. **Column scope: narrow — CRD + ~8 private-fund aggregate columns only, not the full
   448/171-column row.** Only the columns ticket 01's Q3 findings already documented
   (private-fund flag, 7B(1)/7B(2) counts, hedge-fund count, total gross assets of private
   funds, etc.) are parsed and stored. The remaining ~440/163 columns are undocumented (no
   SEC data dictionary exists per ticket 01's Q4) and unconsumed by this cross-check —
   committing to parse/maintain them now would be speculative scope with no current
   consumer.

**Not implemented in this session** — per this map's "decide, don't build" discipline
(destination is a decided plan, not code), this ticket resolves the design only. Building
`sec_adv_firm_roster`'s parser, the `fetch-adv-bulk`/`daily_incremental` wiring for the
Firm Roster CSV specifically, the `adv_fund_count_reconciliation` dbt model, and the
dashboard panel are all follow-up implementation work, not yet ticketed as build tasks —
this map's tickets were decisions; execution now hands off via `/to-spec` + `/to-tickets`
+ `/implement` per the map's Destination.
