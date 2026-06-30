# Phase 1: CAGR Macro And Multi-Year Joins - Context

**Gathered:** 2026-06-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a `cagr()` dbt macro and extend `financial_factors.sql` with N-year self-joins (3yr,
5yr) for revenue, net income, and total assets — computing CAGR strictly between two `FY`
fiscal periods exactly N years apart. Pure dbt gold-layer SQL — zero changes to silver,
parsers, or any loader/runtime file. No quarterly-cadence growth metric is in scope (see
Deferred Ideas).

</domain>

<decisions>
## Implementation Decisions

### Quarterly scope (researched, confirmed out of scope)
- **D-01:** CAGR is FY-to-FY only — quarterly `fiscal_period` rows never get a CAGR value,
  matching ROADMAP.md's original scope exactly. Research-confirmed: annualizing
  quarter-over-quarter growth (the textbook formula exists — CAGR with exponent n=4 for
  quarters) is an explicitly named pitfall for revenue/earnings-style fundamentals
  specifically, because seasonality makes single-quarter annualization volatile and
  misleading (e.g. a retailer's Q4 spike, annualized, produces a wildly wrong "growth
  rate"). Practitioner consensus reserves quarterly-annualized growth for narrow
  short-run capacity-planning contexts with explicit labeling — not a general-purpose
  fundamentals dataset like `FINANCIAL_FACTORS`. No quarterly-projection capability is
  added in this phase.

### Negative-value handling
- **D-02:** CAGR nulls when EITHER endpoint (current or N-years-prior value) is negative
  or zero — not just on an actual sign change as GROW-02's literal wording might suggest.
  Rationale: a negative-to-negative CAGR (e.g. -100 → -50, an improving-but-still-negative
  trend) is mathematically computable but produces a misleadingly POSITIVE CAGR number for
  a company that's still unprofitable — the same class of problem Phase 2's D-01 (ROE
  negative-equity null guard, Damodaran-sourced) already established a precedent for in
  this codebase. Implementation: the `cagr()` macro requires BOTH the numerator
  (current-period value) and denominator (N-years-prior value) to be strictly positive,
  not just non-zero with matching sign.

### Fiscal-year matching tolerance
- **D-03:** Exact `fiscal_year - N` match required for the prior-period comparator — no
  tolerance window for fiscal year-end shifts. If a company's fiscal_year sequence has a
  gap or shift (e.g. after M&A or an accounting-period change) such that no row exists at
  exactly `fiscal_year - N`, the CAGR nulls for that company-year rather than fuzzy-matching
  the nearest available year. Rationale: silently matching a nearby year would compute a
  CAGR over a non-N-year span while labeling it as an N-year CAGR — exactly the
  "incorrectly-spanning calculation" GROW-03 already prohibits for the fiscal-year-gap
  case. Exact-match keeps the N-year claim in the column name/semantics honest.

### Claude's Discretion
- Exact macro signature and parameter naming for `cagr()` — follow the `yoy_growth()`
  macro's existing signature pattern (`cagr(current_col, prior_col, years)` or similar),
  per RESEARCH.md's findings once researched.
- Whether 3yr and 5yr CAGR share a single parameterized self-join CTE or use two separate
  CTEs (mirroring `financial_derived.sql`'s existing `prior_year_values` single-offset
  pattern, extended to two offsets) — an implementation-pattern decision, not a
  vision-level one.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Gold-layer SQL (existing patterns to follow)
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_derived.sql` — existing `prior_year_values` CTE (single `fiscal_year - 1` offset) and `yoy_growth()` macro usage; the pattern this phase's N-year self-joins extend.
- `infra/snowflake/dbt/edgartools_gold/macros/yoy_growth.sql` — existing growth macro to model `cagr()`'s null-guard structure on.
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` — the model this phase extends (same model Phase 2 added profitability/returns factors to); contains the existing `prior_fy_values` CTE and `asset_growth_yoy` factor as the closest analog for an FY-to-FY comparison pattern.
- `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio.sql` and `safe_ratio_signed.sql` (Phase 2) — established null-guard macro conventions in this codebase; `cagr()` should follow the same defensive-division style (no raw `/`, Snowflake hard-errors on division by zero).

### Workstream planning docs
- `.planning/workstreams/fundamental-factors-v2/ROADMAP.md` — Phase 1 success criteria (5 criteria, GROW-01/02/03) and the workstream's no-new-loader constraint.
- `.planning/workstreams/fundamental-factors-v2/REQUIREMENTS.md` — GROW-01, GROW-02, GROW-03 requirement text.
- `.planning/workstreams/fundamental-factors-v2/phases/02-profitability-and-returns-factors/02-CONTEXT.md` — Phase 2's D-01 (negative-equity null guard) precedent, directly informing this phase's D-02.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `yoy_growth(current_col, prior_col)` macro — existing single-year growth macro; `cagr()` is a generalization to N years, likely reusing or closely mirroring its null-guard shape.
- `prior_year_values`/`prior_fy_values` CTE pattern — already exists for 1-year-back joins in both `financial_derived.sql` and `financial_factors.sql`; this phase needs the same join shape at `fiscal_year - 3` and `fiscal_year - 5` offsets.

### Established Patterns
- Every existing ratio/growth factor in this codebase uses a macro — never raw division or raw subtraction-based growth without a null guard. `cagr()` must follow this convention.
- Phase 2 established the precedent (D-01) that a sign-sensitive guard belongs in a dedicated macro variant when an existing macro's guard isn't strict enough — same precedent applies to D-02 here.

### Integration Points
- New CAGR columns are added to the existing `financial_factors.sql` model — no new model file, no new gold table, matching Phase 2's approach. Grain stays `(cik, accession_number, fiscal_period, period_end)`.

</code_context>

<specifics>
## Specific Ideas

No specific UI/display requirements — backend gold-model change only, consumed by dbt/Snowflake clients.

</specifics>

<deferred>
## Deferred Ideas

- **Quarterly-cadence annualized growth metric** — explicitly considered and rejected for
  this phase (see D-01). Research showed it's a named pitfall for seasonal businesses when
  applied to revenue/earnings fundamentals. If ever revisited, it would need explicit
  seasonal-adjustment logic and clear "annualized, short-run only" labeling — a
  substantially larger feature than this phase's FY-to-FY CAGR, and not a natural fit for
  this workstream's existing scope.

</deferred>

---

*Phase: 01-cagr-macro-and-multi-year-joins*
*Context gathered: 2026-06-30*
