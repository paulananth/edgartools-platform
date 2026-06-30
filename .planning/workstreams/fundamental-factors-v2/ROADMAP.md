# Roadmap: Fundamental Factors V2 (Growth, Profitability, Returns)

workstream: fundamental-factors-v2
status: proposed
milestone: Fundamental Factors V2
updated: 2026-06-29

---

## Milestone Goal

Extend `FINANCIAL_FACTORS` (shipped 2026-06-26, PR #102, accounting-only V1) with growth
(CAGR), profitability, and returns factors — using only dbt gold-layer SQL plus, for one
sub-feature (cash conversion cycle), a silver parser addition that reads fields already
present in the `companyfacts` JSON the existing loader fetches. No new loader, no new SEC
fetch path, no bronze change.

This is a proposed milestone, not yet activated. Research below establishes feasibility
ahead of a planning decision.

---

## Research Evidence (2026-06-29)

Conducted ahead of formal phase planning, to confirm the no-new-loader constraint holds:

1. **Multi-year history already exists in silver with no fetch-window limit.**
   `edgar_warehouse/parsers/financials.py` parses the SEC `companyfacts` endpoint, which
   returns *all* historical XBRL facts for a company. No `years_back`/lookback limit
   exists anywhere in `runtime.py` or the parsers (confirmed via repo-wide grep, zero
   matches). A company with 10+ years of XBRL-tagged filings already has that history
   sitting in `sec_financial_fact`/`sec_financial_derived` today.

2. **The N-year self-join CAGR needs already exists for N=1.**
   `financial_derived.sql` builds a `prior_year_values` CTE keyed on
   `(cik, fiscal_period, fiscal_year)` and self-joins on `fiscal_year - 1` to compute YoY
   growth via the `yoy_growth()` macro. A 3-year or 5-year CAGR is the same join shape —
   `fiscal_year - 3` / `fiscal_year - 5` instead of `- 1`, plus a new `cagr()` macro.
   No new tables, no new silver columns.

3. **Profitability/returns inputs are already in `financial_derived`.** Confirmed by
   direct grep of `financial_derived.sql` and `financials_derived.py`:
   `gross_profit` (line 233 parser / line 85 gold), `ebit` (operating income; line 234
   parser / line 87 gold), `roic` (line 283 parser / line 114 gold — already computed,
   just not yet surfaced in `FINANCIAL_FACTORS`), `net_income`, `total_equity`,
   `total_assets`, `revenue` (all already selected in `financial_factors.sql`). Gross
   margin, operating margin, net margin, ROE, ROA, ROIC are all computable today with
   zero silver or loader changes.

4. **Cash conversion cycle needs one new silver field, not a new loader.**
   `cost_of_revenue`/COGS is not currently parsed (gross_profit is picked directly from
   XBRL gross-profit concept tags, not derived from revenue minus COGS) — confirmed via
   grep of `_GROSS_PROFIT_CONCEPTS` in `financials_derived.py`. Adding it means extracting
   one more concept (e.g. `CostOfRevenue`, `CostOfGoodsAndServicesSold`) from the same
   already-fetched `companyfacts` JSON in `financials_derived.py` — a parser/silver
   change, not a new fetch path. Coverage (how many filers tag this concept consistently)
   is unverified and should be the first thing Phase 1 checks.

---

## Phases (proposed, not yet planned in detail)

- [ ] **Phase 1: CAGR Macro And Multi-Year Joins** — add `cagr()` dbt macro, extend
      `financial_factors.sql` with N-year self-joins (3yr, 5yr) for revenue, net income,
      total assets. Verify sign-change handling (GROW-02) and fiscal-year-gap handling
      (GROW-03) with real multi-year company data before shipping.
- [ ] **Phase 2: Profitability And Returns Factors** — add gross/operating/net margin,
      ROE, ROA to `financial_factors.sql`; surface existing `roic` column. Pure SQL
      addition, no parser changes — lowest-risk phase, could ship independently and first.
- [ ] **Phase 3: Cash Conversion Cycle (conditional)** — research `cost_of_revenue`
      XBRL-tag coverage across a representative filer sample first. If coverage is poor,
      declare CCC-01 out of scope (per CCC-02) rather than ship a low-coverage factor.
      If coverage is acceptable, parse `cost_of_revenue` in `financials_derived.py`, add
      DSO/DIO/DPO to `financial_factors.sql`.

**Suggested order:** Phase 2 first (zero risk, immediate value, no research needed),
then Phase 1 (needs sign-change/gap-handling care but no silver risk), then Phase 3
(only phase with real feasibility risk — research gates the build).

---

## Out of Scope

See `REQUIREMENTS.md` — market-derived factors (beta, P/E, EV/EBITDA) are explicitly
deferred to the held `model-builder-contract-gaps` Phase 5 charter decision, not this
milestone.
