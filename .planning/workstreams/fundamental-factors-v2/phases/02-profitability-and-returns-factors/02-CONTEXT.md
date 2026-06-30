# Phase 2: Profitability And Returns Factors - Context

**Gathered:** 2026-06-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Add gross margin, operating margin, net margin, return on equity, and return on assets
to the `FINANCIAL_FACTORS` gold model, and surface the existing `financial_derived.roic`
column alongside them. Pure dbt gold-layer SQL — zero changes to silver, parsers, or any
loader/runtime file. All required input columns (`gross_profit`, `ebit`, `net_income`,
`total_equity`, `total_assets`, `revenue`, `roic`) already exist in `financial_derived`.

</domain>

<decisions>
## Implementation Decisions

### Negative equity handling (ROE)
- **D-01:** `return_on_equity` nulls when `total_equity < 0`, rather than computing
  `net_income / total_equity` as-is. Research-confirmed: Aswath Damodaran (NYU Stern)
  treats ROE as "meaningless" under negative book equity, since negative/negative produces
  a misleadingly positive value — recommends nulling and falling back to ROA instead.
  ~10% of companies in his sample have negative book equity (buybacks, accumulated
  losses), so this isn't an edge case to ignore. Implementation: extend the `safe_ratio()`
  pattern with an explicit sign check on the denominator for this one factor (gross
  margin, operating margin, net margin, ROA use plain `safe_ratio()` — only ROE needs the
  extra guard, since revenue and total_assets aren't expected to go negative the way
  equity can).

### Period scope for new factors
- **D-02:** All new factors (margins, ROE, ROA) compute for every `fiscal_period` value
  (FY and quarterly), not restricted to FY-only like the existing `asset_growth_yoy`
  factor. Rationale: `asset_growth_yoy`'s FY restriction exists because YoY growth needs
  a full prior year for a clean comparison — that constraint doesn't apply to margins/
  returns, which are meaningful for any single reporting period on their own. Restricting
  to FY would silently drop quarterly data trend-watching consumers may want.

### ROIC trust vs re-derivation
- **D-03:** Phase 2 surfaces the existing `financial_derived.roic` column as-is (not
  recomputed) and documents the simplification in the dbt column description
  (`gold.yml`). Research-confirmed: textbook ROIC = NOPAT (EBIT × (1 − tax rate)) /
  Average Invested Capital — but `financials_derived.py` has no `income_tax_expense` or
  effective-tax-rate field parsed anywhere (confirmed via repo-wide grep, zero matches),
  so the tax-adjustment input for a textbook NOPAT-based ROIC doesn't exist in silver
  today. The current code's own comment (`financials_derived.py:279`) already documents
  this as a deliberate simplification, not an oversight. Re-deriving textbook ROIC would
  require adding a new parsed field — that's a silver-layer change exceeding Phase 2's
  "pure SQL" scope (see Deferred Ideas below).

### Claude's Discretion
- Exact dbt column naming for the new factors (e.g. `gross_margin` vs `gross_margin_pct`)
  — follow the existing naming convention already used in `financial_factors.sql`
  (`working_capital_to_assets`, `current_ratio`, etc. — no `_pct` suffix despite being
  ratios).
- Whether to add a comparable negative-equity guard to ROA (`net_income / total_assets`)
  — total_assets going negative is not a realistic accounting scenario the way equity
  going negative is (negative equity is common via buybacks; negative total assets would
  imply a fundamentally broken balance sheet), so `safe_ratio()`'s plain zero/missing
  guard is sufficient for ROA without a dedicated sign check.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Gold-layer SQL (existing patterns to follow)
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` — the model this phase extends; follow its existing `safe_ratio()` usage pattern for new factors.
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_derived.sql` — source of all required input columns (`gross_profit` line 85, `ebit` line 87, `roic` line 114, plus `net_income`/`total_equity`/`total_assets`/`revenue`).
- `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio.sql` — existing null-guard macro; ROE needs an additional sign-check variant per D-01.
- `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml` — existing test conventions for this model to follow for new factor tests.

### Silver-layer source of truth (for the ROIC simplification note, D-03)
- `edgar_warehouse/parsers/financials_derived.py` line 279 — existing ROIC comment documenting the simplified (pre-tax) formula; do NOT modify in this phase, only reference for the gold.yml column description.

### Workstream planning docs
- `.planning/workstreams/fundamental-factors-v2/ROADMAP.md` — Phase 2 success criteria and the workstream's no-new-loader constraint.
- `.planning/workstreams/fundamental-factors-v2/REQUIREMENTS.md` — PROF-01, PROF-02, PROF-03 requirement text; also documents the Out of Scope section (market/valuation factors).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `safe_ratio(numerator_col, denominator_col)` dbt macro — null-guards on missing/zero denominator; reuse directly for gross margin, operating margin, net margin, ROA.
- `financial_factors.sql`'s existing column block structure (line-by-line `select` list grouped by "Base accounting inputs" then "V1 accounting-only factors") — new factors should follow the same grouping convention, appended after the existing growth factors.

### Established Patterns
- Every existing ratio factor in `financial_factors.sql` uses `{{ safe_ratio(...) }}` — no factor computes a raw division without the macro. New factors must follow this, with ROE's negative-equity guard as documented in D-01.
- `financial_derived.sql`'s `prior_fy_values`/`prior_year_values` CTEs are FY-scoped by design (needed for YoY comparison) — new Phase 2 factors are NOT growth/comparison factors, so they don't need this join pattern at all (per D-02, they're single-period factors).

### Integration Points
- New factors are columns in the existing `financial_factors.sql` model — no new model file, no new gold table. Grain stays `(cik, accession_number, fiscal_period, period_end)`, unchanged.

</code_context>

<specifics>
## Specific Ideas

No specific UI/display requirements — this is a backend gold-model change consumed by
dbt/Snowflake clients, no dashboard or app-layer rendering in scope for this phase.

</specifics>

<deferred>
## Deferred Ideas

- **Valuation/market-derived factors** (P/E, EV/EBITDA, price-based ratios) — explicitly
  out of scope per `REQUIREMENTS.md`'s existing "Out of Scope" section. These require a
  platform charter decision on owning vs. sourcing market data, tracked separately under
  the held `model-builder-contract-gaps` Phase 5. Not re-litigated here.
- **Textbook NOPAT-based ROIC re-derivation** — needs a new `income_tax_expense`/
  effective-tax-rate field parsed in `financials_derived.py` (a silver-layer change, not
  pure SQL). Candidate for a future phase in this workstream or a follow-up requirement;
  not Phase 2 scope per D-03.

</deferred>

---

*Phase: 02-profitability-and-returns-factors*
*Context gathered: 2026-06-30*
