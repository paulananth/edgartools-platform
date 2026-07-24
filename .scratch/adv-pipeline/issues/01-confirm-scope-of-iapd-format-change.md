# 01 — Confirm Scope of IAPD Bulk Format Change

Type: research
Status: open
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

(pending)
