# 07 — edgartools-only gateway for catalogs and companyfacts (phase 2)

**What to build:** Tickers, submissions, daily index, and companyfacts network access for those object classes use edgartools-backed adapters, completing the exclusive-gateway cutover for SEC objects the library covers, without dropping silver-once skip behavior from tickets 04–05.

**Blocked by:** 04 — Silver-once companyfacts; 05 — Catalog novelty-only refresh; 06 — edgartools-only filing capture.

**Status:** resolved

- [x] Catalog and companyfacts network for migrated classes go through edgartools-backed adapters
- [x] Novelty-only and versioned skip behaviors from 04–05 still hold
- [x] Non-edgartools sources (e.g. IAPD ADV bulk) remain on mandatory archive path and are not falsely claimed as edgartools-covered
- [x] Architecture/regression coverage documents which object classes are cut over
