# 01 — Confirm Scope of IAPD Bulk Format Change

Type: research
Status: resolved
Blocked by: none
Blocks: 02

## Question

SEC's live IAPD bulk archive (verified 2026-07-24 by downloading and
inspecting the July 2026 `ia07012026.zip` / `ia07012026-exempt.zip` files
directly) is now a single flat "Firm Roster" CSV
(`IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_<id>.CSV`) with ~150 columns keyed to
Form ADV item numbers, and private funds appear only as firm-level aggregate
counts (e.g. "Total number of Hedge funds", "Count of Private Funds -
7B(1)") — not the per-fund PFID/CRD/name/AUM rows that
`adv_bulk_ingest.py` and the approved `adviser-fund-source-contract.md` both
assume (the old `IA_ADV_Base`, `Schedule_D_7B1`, `Schedule_D_7B2`,
`ADV_Filing_Types` relational tables).

Resolve, against SEC/IAPD primary sources only (not secondary write-ups):

1. Is the Firm Roster CSV now the *only* bulk product SEC publishes, or does
   a separate relational/Schedule-D-detail bulk product still exist under a
   different URL or name (check `adviserinfo.sec.gov` directly, not just the
   `sec.gov` bulk-data page already checked last session)?
2. If a separate per-fund detail source no longer exists in bulk form at
   all, is per-fund Schedule 7.B.(1)/(2) detail obtainable any other way at
   scale (e.g. a different bulk product, an API, or is per-adviser lookup
   via the IAPD website genuinely the only remaining route — in which case
   note that per-adviser lookup does not scale to bulk ingestion)?
3. Does the Firm Roster CSV's aggregate private-fund columns carry enough
   information to derive anything meaningful (e.g. presence/absence of
   private-fund management, aggregate counts by fund type) even without
   per-fund PFID identity?
4. Is there a documented schema/data-dictionary for the Firm Roster format
   (column meanings, especially the ~150 ADV-item-numbered columns) to
   parse against, analogous to the old relational tables' documented keys
   the current contract references?

## Answer

Full evidence, citations, and downloaded-file inspection details:
[`research/01-iapd-format-scope-findings.md`](../research/01-iapd-format-scope-findings.md).
**Headline correction vs. last session's premise: the old relational per-fund format was
not discontinued — it moved, and a working bulk source for it still exists today.**

1. **No, the Firm Roster CSV is not the only bulk product.** `adviserinfo.sec.gov` runs
   two *different* backing services behind its `/compilation` and `/adv` routes (same
   method name, `getCompilationReport()`, but different injected services building
   different URLs — confirmed by reading both method bodies in the app's JS bundle, not
   assumed from the shared name). `/compilation` → a 3-feed XML manifest (SEC/state
   firm + individual) with only a private-fund Y/N flag, no counts. `/adv` → a *different*
   manifest (`reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json`) whose
   `advFilingData` key lists **monthly ZIPs, current through June 2026**, each containing
   the full ~100-file relational schema (`IA_ADV_Base_A/B`, `IA_Schedule_D_7B1`,
   `IA_Schedule_D_7B2`, `ADV_Filing_Types`, etc.) with real per-fund rows (fund name, Fund
   ID/PFID, AUM, fund type) — downloaded and verified directly
   (`ADV_Filing_Data_20260601_20260630.zip`). These monthly files pick up with zero gap
   exactly where SEC's static FOIA-page historical archive (2000-2024, also relational,
   also per-fund, also confirmed by inspection) leaves off on 2025-01-01.
2. **Yes — bulk per-fund detail is obtainable**, via the `advFilingData` monthly feed
   above for 2025-01-01–present, plus the FOIA page's static zips for everything before
   that. This reverses last session's "per-adviser lookup only" conclusion. Per-adviser
   PDF lookup (confirmed separately, still works, still populated) remains a valid
   fallback/single-firm cross-check but is no longer the only route.
   **`adv_bulk_ingest.py`'s existing filename regexes were tested directly against the
   June 2026 `advFilingData` ZIP's real file list and every one matches** — the parser
   was not written against a discontinued format; it was tested last session against the
   wrong SEC product (the Firm Roster CSV) instead of this one.
3. **Yes, verified against real populated data**, unchanged from the first pass. Scanned
   ~17K rows of the registered-advisers Firm Roster CSV: 5,970 firms flag `7B=Y`; sub-type
   Y/N + count columns and `Total Gross Assets of Private Funds` are populated whenever
   applicable. Given (1)/(2), read this CSV's aggregate counts as a useful cross-check
   signal alongside the richer per-fund feed, not the primary source.
4. **No CSV-specific data dictionary** for the Firm Roster CSV (unchanged) — SEC's bulk
   page points to the generic Form ADV Part 1A instructions PDF. Correction to this
   ticket's premise: the registered-advisers CSV has **448** columns (direct count), not
   ~150 — the exempt-advisers CSV is the one near that figure, at **171**. The
   `advFilingData` relational feed uses the same Form-ADV-item-numbered column convention
   the parser already targets, decodable the same way.

**Follow-up for ticket 02 to account for:** the `advFilingData` feed is confirmed (row
count, not just file size) to be a *monthly delta of filing activity*, not a
full-universe snapshot — June 2026's `IA_ADV_Base_A` file has 2,938 firm rows vs. the
~17,073-firm registered universe (Q3). Reconstructing full current per-fund coverage will
need a rolling window of trailing months (RIAs reaffirm ADV at least annually), not a
single month's fetch. See the research doc's "Ingestion-strategy implication" note.

**Independent re-validation (2026-07-24, before finalizing ticket 03's resolution which
depends on this ticket's findings):**

- **Annual reaffirmation rule confirmed from a primary source, not inferred.** Fetched
  `https://www.sec.gov/about/forms/formadv-instructions.pdf` directly and located the
  exact clause: SEC/state-registered advisers "must amend Form ADV each year by filing
  an annual updating amendment within 90 days after the end of your fiscal year,"
  updating "all items in Part 1A, 1B, 2A and 2B ... including corresponding sections of
  Schedules A, B, C, and D" (which includes Schedule D 7.B private-fund detail).
  **Exempt Reporting Advisers have the identical requirement**, same 90-day/fiscal-year
  clause, "including corresponding sections of Schedules A, B, C, and D." This
  independently grounds both the 12-13 month rolling-window sizing and ticket 03's
  "ERA and RIA get identical handling" answer in a real regulatory rule, not a
  heuristic.
- **`advFilingData` feed re-fetched and re-verified independently**
  (`reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json`, June 2026 ZIP
  downloaded fresh): the parser's four regexes were tested directly against the live
  ZIP's real `namelist()` (not the subagent's report) and all four matched
  (`ERA_ADV_Base`, `IA_ADV_Base_A`, `IA_ADV_Base_B`; `ERA_Schedule_D_7B1`,
  `IA_Schedule_D_7B1`; `ERA_Schedule_D_7B2`, `IA_Schedule_D_7B2`;
  `ADV_Filing_Types`) — confirmed against the actual regex literals in
  `edgar_warehouse/application/adv_bulk_ingest.py:99-102`, not a reconstruction. Row
  counts independently reproduced: `IA_ADV_Base_A` = 2,938 rows (exact match), real
  per-fund data in `IA_Schedule_D_7B1` confirmed (`PALM PEAK CAPITAL FUND I, L.P.`,
  PFID `805-4964869201`, exact match to the research doc's sample).
- **New finding the original research pass did not surface — a genuine caveat, not a
  reversal:** inspecting `reports_metadata.json`'s `uploadedOn` timestamps shows this
  feed's apparent "monthly" history is mostly **two bulk backfill events**, not organic
  month-by-month publication: all 12 files for 2025 were uploaded on the *same day*
  (2026-05-04), and January–April 2026 were uploaded on 2026-05-01. Only **May 2026**
  (uploaded 2026-06-02) and **June 2026** (uploaded 2026-07-01) show the genuine
  ~one-month-after-period-end cadence the research assumed. Practical implication: the
  feed's *content* (18 months of real monthly deltas, Jan 2025–Jun 2026) is solid and
  independently confirmed, and the regulatory annual-reaffirmation rule guarantees
  eventual coverage regardless of exactly how SEC operates the feed — but confidence in
  "this publishes reliably every month going forward" rests on only two real data
  points so far, not an established long-run track record. Ticket 06 (automated fetch)
  should treat "expected file not yet present this month" as a normal no-op-and-retry
  case (already planned), not assume monthly publication is guaranteed reliable.
