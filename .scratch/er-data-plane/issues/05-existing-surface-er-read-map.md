# 05 — Existing-surface ER read map (ERDP-05)

Type: research  
Status: resolved  
Blocked by: 04  

## Question

Document the **current** agent-facing read paths for ER-useful data already on the platform (COMPANY/TICKER, FINANCIAL_DERIVED/FACTS, EARNINGS_RELEASE, FILING_*, ownership, 13F, Subject Bundle, MDM, graph). For each: surface name, grain, freshness/watermark notes, known limitations vs ER skills. Output as section draft for `spec.md` § ERDP-05.

## Answer

**Gist:** Current ER-useful surfaces documented in [assets/erdp-05-existing-surface-read-map.md](../assets/erdp-05-existing-surface-read-map.md) and summarized in `spec.md` §5. Layers: Gold free tables (Explore) vs Decision Contract / Subject Bundle (Agent-Grade under Decision Watermark). Prefer `EDGARTOOLS_GOLD.*` names (dbt); map SOURCE export names in the asset. Strong for identity, multi-year financials, 8-K GAAP flash, filings metadata, ownership/13F, graph neighborhood. Still Partial→Covered only after per-product acceptance criteria; does not provide consensus, guidance values, calendar, transcripts, or market prices.

**Matrix note:** Ticket 04 frozen first; ERDP-05 does not yet flip Partial cells to Covered (needs acceptance criteria per F1–F12 product).
