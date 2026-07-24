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

1. **Yes, effectively the only current bulk product.** IAPD's own SPA
   (`adviserinfo.sec.gov/compilation` and `/adv` — both routes resolve to the identical
   `getCompilationReport()` call in the app bundle) serves exactly three feeds via
   `reports.adviserinfo.sec.gov/.../CompilationReports.manifest.json`: SEC-firm, state-firm,
   and individual XML. No private-fund/Schedule-D feed exists in that manifest. A separate
   relational per-fund product (`IA_Schedule_D_7B1`/`7B2` CSVs, confirmed present via a ZIP
   central-directory listing) **did** exist and is still downloadable from SEC's FOIA page
   (`sec.gov/foia-services/.../form-adv-data`) — but it is a closed historical archive capped
   at 2024-12-31. That same FOIA page states current (2025+) data lives at
   `adviserinfo.sec.gov/adv`, which is the sparse 3-feed manifest above, not a richer
   replacement. The downloaded XML feed was inspected directly and — confirmed against its
   official XSD (`Item7BType`) — carries only a Y/N flag, not even the CSV's aggregate counts.
2. **No bulk route exists; per-adviser lookup is the only remaining route, and it does not
   scale to bulk ingestion.** Confirmed by downloading a real per-adviser PDF
   (`reports.adviserinfo.sec.gov/reports/ADV/1588/PDF/1588.pdf`, Davenport & Company LLC) —
   it contains full, populated Schedule D 7.B.(1) records (fund name "EWF PARTNERS II LLC",
   PFID `805-4154444394`, jurisdiction, fund type, AUM). The data exists and is current, but
   only one-firm-at-a-time via a PDF fetch per CRD — no bulk/API path found anywhere in the
   IAPD app's own routing table.
3. **Yes, verified against real populated data**, not just column names. Scanned ~17K rows
   of the registered-advisers CSV: 5,970 firms flag `7B=Y`; sub-type Y/N + count columns
   (hedge/PE/VC/liquidity/real-estate/securitized/other) and `Total Gross Assets of Private
   Funds` are populated whenever applicable (e.g. Davenport: 3 hedge funds, $709.9M gross
   private-fund assets). Supports firm-level "manages private funds" flags, per-type counts,
   and aggregate AUM — not per-fund identity.
4. **No CSV-specific data dictionary.** SEC's bulk-data page explicitly tells readers to
   decode columns against the generic Form ADV Part 1A instructions PDF
   (`sec.gov/files/formadv-part1a_1.pdf`) — there's no roster-CSV field-by-field document.
   Correction to this ticket's premise: the registered-advisers CSV has **448** columns
   (counted directly via Python `csv`), not ~150 — the exempt-advisers CSV is the one close
   to that figure, at **171** columns (ERAs file fewer Form ADV items). Separately, FINRA/IARD
   does publish an official XSD + PDF guide for the (different, XML) compilation feed at
   `iard.com/firm-compilation` — useful as schema-level confirmation of Q1/Q2, not as
   documentation of the CSV itself.
