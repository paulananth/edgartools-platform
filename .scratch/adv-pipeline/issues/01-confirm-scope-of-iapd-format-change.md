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
