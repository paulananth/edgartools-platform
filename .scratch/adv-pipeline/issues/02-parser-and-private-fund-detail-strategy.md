# 02 — Fetch Target and Rolling-Window Strategy (was: Parser Rewrite)

Type: grilling
Status: open
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

(pending)
