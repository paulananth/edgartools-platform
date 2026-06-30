# Requirements: Fundamental Factors V2 (Growth, Profitability, Returns)

workstream: fundamental-factors-v2
status: active
milestone: v1.0 Fundamental Factors V2
updated: 2026-06-29

---

## Constraint (non-negotiable, set by request)

No new loader, no new SEC fetch path, no change to bronze capture. Every requirement
below must be satisfiable by (a) gold-layer dbt SQL only, or (b) parsing additional
fields out of XBRL data the existing `companyfacts` loader already fetches (a silver
parser/schema change, not a new ingestion path). If a requirement cannot be satisfied
under (a) or (b), it must be declared out of scope rather than quietly requiring a new
loader.

## Milestone Requirements

### Growth Factors (CAGR)

- [ ] **GROW-01**: Consumer can query 3-year and 5-year CAGR for revenue, net income, and total assets per `(cik, fiscal_year)`, computed via N-year self-join against `financial_derived` (same join shape as the existing 1-year `prior_year_values` pattern), with null when insufficient history exists.
- [ ] **GROW-02**: CAGR computation handles negative-to-positive and positive-to-negative sign changes without producing a misleading or complex-valued result (explicit null, not a silently wrong number).
- [ ] **GROW-03**: CAGR factors are documented as requiring N consecutive `FY` fiscal periods; gaps in fiscal-year sequence (e.g. a missed 10-K) produce null, not an incorrect multi-year span treated as N years.

### Profitability And Returns

- [ ] **PROF-01**: Consumer can query gross margin (`gross_profit / revenue`), operating margin (`ebit / revenue`), and net margin (`net_income / revenue`) — all three inputs already present in `financial_derived`, no silver change required.
- [ ] **PROF-02**: Consumer can query return on equity (`net_income / total_equity`) and return on assets (`net_income / total_assets`) — both inputs already present in `financial_derived`, no silver change required.
- [ ] **PROF-03**: ROIC is already exposed in `financial_derived` (`w.roic`); this requirement is to surface it in `FINANCIAL_FACTORS` alongside the other profitability factors for a single consumer-facing model, not to recompute it.

### Cash Conversion Cycle (requires one silver parser addition)

- [ ] **CCC-01**: Consumer can query Days Sales Outstanding, Days Inventory Outstanding, and Days Payable Outstanding, requiring a new `cost_of_revenue` field parsed from XBRL concepts (e.g. `CostOfRevenue`, `CostOfGoodsAndServicesSold`) in `financials_derived.py` — extracted from the same already-fetched `companyfacts` JSON, not a new fetch.
- [ ] **CCC-02**: If `cost_of_revenue` cannot be reliably extracted for a meaningful fraction of filers during research (Phase 1), CCC-01 is declared out of scope for this milestone rather than shipped with poor coverage.

## Out of Scope

- Any factor requiring market/price data (beta, P/E, EV/EBITDA, dividend yield) — these belong to the held `model-builder-contract-gaps` Phase 5 charter decision, not this milestone.
- Any factor requiring data outside SEC XBRL filings (analyst estimates, peer-curated comparables).
- Sector-specific factor variants (bank net interest margin, REIT FFO, insurance combined ratio).

## Future Requirements

- Revisit sector-specific factor variants once the SEC-derivable accounting-only set (this milestone) is in production and consumed.
- Revisit market-derived factors once `model-builder-contract-gaps` Phase 5 charter decision lands.
