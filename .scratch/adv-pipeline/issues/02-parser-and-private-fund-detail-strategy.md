# 02 — Fetch Target and Rolling-Window Strategy (was: Parser Rewrite)

Type: grilling
Status: resolved
Blocked by: 01
Blocks: 04, 05, 06

## Constraint (non-negotiable, restated by the user 2026-07-24)

ADV data must reach the Neo4j/Snowflake graph end to end. Whatever this
ticket decides for private-fund detail, it must not become a reason to skip
Adviser/Fund entity resolution or graph sync altogether — only
`MANAGES_FUND` edge fidelity is allowed to degrade if bulk data truly lacks
per-fund PFID identity. See map.md Notes for the full statement.

## Question

**Superseded by ticket 01's finding (2026-07-24):** `adv_bulk_ingest.py`
does not need a parser rewrite — its existing filename regexes already
match the correct, currently-published source
(`adviserinfo.sec.gov`'s monthly `advFilingData` relational feed). What
remains open:

1. **Rolling-window design.** `advFilingData` is a monthly filing-activity
   delta (~17% of the ~17,073-firm registered universe per month, verified
   by row count), not a full snapshot. What window reconstructs full
   current coverage — the research suggests a rolling ~13-month union
   (dedup by CRD/FilingID, keep latest per firm), reasoned from RIAs' at
   -least-annual reaffirmation requirement, but this ticket must explicitly
   verify no firm can go stale longer than that before committing to a
   window size (i.e. confirm the annual-reaffirmation rule is airtight, not
   just a heuristic).
2. **Does the Firm Roster CSV (`sec.gov`, true full-universe snapshot,
   aggregate-only private-fund counts) get ingested at all?** Candidates:
   (a) skip it entirely now that the richer `advFilingData` feed exists;
   (b) ingest it as a parallel full-universe completeness/cross-check
   control (e.g. flag a firm whose `advFilingData`-derived fund count
   doesn't match its Firm-Roster aggregate count) — this is exactly the use
   the research doc suggested for it.
3. **Historical backfill scope for `load_history`.** SEC also publishes two
   static pre-2025 archives (2000-2011, 2011-2024) in the same relational
   shape — does `load_history`'s baseline need to backfill those too, or
   just the rolling window of recent months (ties into ticket 03's answer
   on load_history scope, which assumed no historical depth existed at all
   — that assumption is now wrong for ADV filing history, though may still
   be the right call on value grounds, mirroring the 13F/proxy
   narrow-to-recent decision in CLAUDE.md)?
4. Does firm-identity/office/disclosure-event data
   (`sec_adv_filing`/`sec_adv_office`/`sec_adv_disclosure_event`) map
   cleanly from the `advFilingData` feed's `IA_ADV_Base_A/B` files (the
   parser's original, correct target), or does inspection reveal gaps?

## Answer

**Preamble — two of the four sub-questions turned out to already be resolved in code, not
open decisions.** Reading `edgar_warehouse/mdm/adv_bulk.py` (`resolve_advisers_bulk`/
`resolve_funds_bulk`) shows MDM already projects the *latest filing per CRD/PFID* from
whatever's in silver via its own `_latest_by_identity` dedup — this is live in production,
independent of `adv_bulk_ingest.py`'s unused `reconstruct_effective_adv_set` (dead code
outside tests). Code comments in `adv_bulk_ingest.py` (fund_index SMALLINT-overflow fix,
date-format handling, cp1252 decode fix) confirm a **13-month window (2025-06..2026-06)
has already been run against the real archive in production** and surfaced/fixed real
bugs. So "does the dedup/rolling-read logic work" was never actually open — only the
*fetch window size* was.

1. **Rolling-window size: 13 months.** SEC's annual-reaffirmation rule (confirmed primary-
   source in ticket 01: Form ADV instructions PDF, "must amend Form ADV each year ...
   within 90 days after the end of your fiscal year," identical for RIA and ERA) bounds
   the theoretical worst case at ~15 months (12mo cycle + 90-day grace). Decided: keep the
   already-tested 13-month window rather than widening to the strict 15-month bound — a
   small tail of late filers may be briefly stale, accepted as consistent with the
   existing 13F/proxy narrow-window precedent in CLAUDE.md, and because SEC's own
   enforcement already tolerates the 90-day grace.
2. **Firm Roster CSV: ingested, as a parallel completeness cross-check** (not skipped).
   Flags firms where `advFilingData`-derived fund counts don't match the Firm Roster's
   aggregate counts. This is new scope beyond what existed before this ticket — spun off
   as ticket 08 (design) rather than decided here, per this map's "decide, don't build"
   discipline.
3. **Historical backfill: rolling window only, no 2000-2024 backfill.** Confirms ticket
   03's original conclusion still holds, even though the premise it was reasoned from
   ("no historical depth exists at all") was corrected by ticket 01 — the decision itself
   is unchanged: mirrors the 13F/proxy narrow-to-current-state precedent, and the 13-month
   window already captures every currently-active adviser/fund per the annual-
   reaffirmation rule. Pre-2025 filings add little value for firms still active today
   (superseded by later amendments) and none for firms no longer active.
4. **Genuine gap found, not yet resolved — spun off as ticket 07 (research).**
   `adv_bulk_ingest.py` only populates `sec_adv_filing` and `sec_adv_private_fund` from
   the bulk feed. `sec_adv_office`/`sec_adv_disclosure_event` are populated only by the
   separate EDGAR-native parser (`edgar_warehouse/parsers/adv.py`), which runs for a small
   subset of advisers (those who also file ADV on EDGAR directly). Since
   `resolve_advisers_bulk` reads `sec_adv_office` for `hq_city`/`hq_state`, at bulk scale
   the vast majority of advisers resolved via the bulk feed would have null HQ data. The
   archive has ~95 other unexamined Schedule A/B/D/R and DRP tables per firm (e.g.
   `IA_Schedule_D_1B` for offices, DRP schedules for disclosures) that may contain
   equivalents — ticket 07 inspects them before any build decision is made.

**New tickets surfaced:** 07 (research — inspect archive for office/disclosure
equivalents), 08 (grilling — design the Firm Roster CSV cross-check). Neither blocks 04,
05, or 06 — office/disclosure quality and the cross-check are both additive to the core
destination (resolved Adviser/Fund entities reaching the graph), not prerequisites for it.
