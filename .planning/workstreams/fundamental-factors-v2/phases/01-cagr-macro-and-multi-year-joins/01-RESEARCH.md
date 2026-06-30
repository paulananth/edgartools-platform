# Phase 1: CAGR Macro And Multi-Year Joins - Research

**Researched:** 2026-06-30
**Domain:** dbt gold-layer SQL (Snowflake dynamic tables), N-year self-join + compound growth rate computation
**Confidence:** HIGH

## Summary

This phase adds a `cagr()` dbt macro and extends `financial_factors.sql` with two new
self-joins (`fiscal_year - 3`, `fiscal_year - 5`) producing 6 new columns: 3yr/5yr CAGR
for revenue, net income, and total assets. The existing `prior_fy_values` CTE in
`financial_factors.sql` already proves the join shape (1-year lookback, `FY`-only,
deduplicated via `qualify row_number()`); this phase needs the identical pattern
duplicated at two more offsets, sourcing `revenue` and `net_income` in addition to the
columns `prior_fy_values` currently selects (`total_assets`, `shares_outstanding`).
**Critical structural finding:** `prior_fy_values` is keyed by `(cik, fiscal_year)` only
(not `fiscal_period`) because it's pre-filtered `where fiscal_period = 'FY'` — so a
3-year/5-year variant can reuse this exact filter-then-key pattern without needing
`fiscal_period` in the partition.

The CAGR formula `(current/prior)^(1/years) - 1` requires Snowflake's `POWER()` function.
D-02 already nulls out negative/zero endpoints *before* the macro would ever see them
(handled by joining only positive-validated rows or guarding inside the macro itself) —
but research into Snowflake's `POWER()` semantics found no authoritative documentation of
negative-base/fractional-exponent behavior (Snowflake's own docs page is silent on this
edge case). Given that gap, **the `cagr()` macro must defensively guard the ratio's sign
itself** (mirroring `safe_ratio_signed()`'s `> 0` pattern), not rely solely on upstream
join conditions — this is both safer (defense-in-depth, matching Phase 2's established
precedent of self-contained null-safe macros) and avoids a runtime error risk from an
unverified Snowflake numeric edge case reaching production.

The dev Snowflake source-schema staleness blocker documented in STATE.md (missing
`current_assets` and 7 sibling columns from `SEC_FINANCIAL_DERIVED`) does **not** affect
this phase: `revenue`, `net_income`, and `total_assets` are all defined in the original
`CREATE TABLE SEC_FINANCIAL_DERIVED` statement (bootstrap SQL), not in the `ALTER TABLE
... ADD COLUMN IF NOT EXISTS` block that is the actual source of the staleness gap. This
phase's three required input columns are unaffected — but the live `dbt test` blocker
itself (the whole `financial_derived` model failing to compile/test against the stale
dev source table) still applies, since `dbt test` runs the entire model's unit tests,
not just the new ones. This phase's plan should flag the same execution risk Phase 2
hit, without assuming it's fixed.

**Primary recommendation:** Add a `cagr(current_col, prior_col, years)` macro (self-guarding,
`POWER()`-based) to `infra/snowflake/dbt/edgartools_gold/macros/cagr.sql`. Extend
`financial_factors.sql` with two new CTEs, `prior_fy_values_3y` and `prior_fy_values_5y`
(parallel structure to the existing `prior_fy_values`, each selecting `revenue`,
`net_income`, `total_assets`), each left-joined on `fiscal_year - 3` / `fiscal_year - 5`
respectively, gated to `fiscal_period = 'FY'` in the final select (matching the existing
`asset_growth_yoy` FY-only gating pattern, since D-03 already establishes CAGR is FY-only
per D-01 in CONTEXT.md).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| N-year self-join (3yr/5yr lookback) | Database / Storage (dbt SQL, Snowflake dynamic table) | — | Pure gold-layer join extension of the existing `prior_fy_values` pattern; no app-tier logic needed. |
| CAGR formula computation | Database / Storage (new dbt macro) | — | Compound-growth math belongs centrally in a reusable macro, matching the project's `safe_ratio()`/`yoy_growth()` convention — never inlined per-model. |
| Negative/zero endpoint guard (D-02) | Database / Storage (macro-internal `case` guard) | — | Same precedent as Phase 2's `safe_ratio_signed()` — defensive guard lives in the macro itself, not duplicated at every call site or relied upon solely from upstream join filtering. |
| Fiscal-year-gap exact-match enforcement (D-03) | Database / Storage (CTE join condition, `=` not `between`) | — | An exact `=` equi-join on `fiscal_year - N` structurally cannot fuzzy-match; this is a join-shape property, not something the macro needs to enforce. |
| Consumption (Streamlit dashboard, ad-hoc SQL) | Out of phase scope | — | No app-layer rendering changes in this phase per CONTEXT.md `<specifics>`. |

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 — Quarterly scope (researched, confirmed out of scope):** CAGR is FY-to-FY only —
quarterly `fiscal_period` rows never get a CAGR value, matching ROADMAP.md's original
scope exactly. Research-confirmed: annualizing quarter-over-quarter growth is an
explicitly named pitfall for revenue/earnings-style fundamentals specifically, because
seasonality makes single-quarter annualization volatile and misleading. No
quarterly-projection capability is added in this phase.

**D-02 — Negative-value handling:** CAGR nulls when EITHER endpoint (current or
N-years-prior value) is negative or zero — not just on an actual sign change. Rationale:
a negative-to-negative CAGR is mathematically computable but produces a misleadingly
POSITIVE CAGR number for a company that's still unprofitable — same class of problem as
Phase 2's D-01 (ROE negative-equity null guard). Implementation: the `cagr()` macro
requires BOTH the numerator (current-period value) and denominator (N-years-prior value)
to be strictly positive, not just non-zero with matching sign.

**D-03 — Fiscal-year matching tolerance:** Exact `fiscal_year - N` match required for the
prior-period comparator — no tolerance window for fiscal year-end shifts. If a company's
fiscal_year sequence has a gap or shift such that no row exists at exactly
`fiscal_year - N`, the CAGR nulls for that company-year rather than fuzzy-matching the
nearest available year. Rationale: silently matching a nearby year would compute a CAGR
over a non-N-year span while labeling it as an N-year CAGR — exactly the
"incorrectly-spanning calculation" GROW-03 already prohibits. Exact-match keeps the
N-year claim in the column name/semantics honest.

### Claude's Discretion

- Exact macro signature and parameter naming for `cagr()` — follow the `yoy_growth()`
  macro's existing signature pattern (`cagr(current_col, prior_col, years)` or similar).
  **Research recommendation: `cagr(current_col, prior_col, years)`** — see Architecture
  Patterns below for exact implementation.
- Whether 3yr and 5yr CAGR share a single parameterized self-join CTE or use two separate
  CTEs (mirroring `financial_derived.sql`'s existing `prior_year_values` single-offset
  pattern, extended to two offsets). **Research recommendation: two separate CTEs**
  (`prior_fy_values_3y`, `prior_fy_values_5y`) — dbt/Jinja has no clean way to
  parameterize a CTE's join offset without a `{% for %}` macro-generated CTE block,
  which would be a larger structural change than this phase's scope justifies. Two
  near-identical CTEs (each ~12 lines) is simpler to read, debug, and unit-test than one
  parameterized/generated CTE, and matches the codebase's existing preference for
  explicit over clever (see `Don't Hand-Roll` below).

### Deferred Ideas (OUT OF SCOPE)

- **Quarterly-cadence annualized growth metric** — explicitly considered and rejected for
  this phase (see D-01). Research showed it's a named pitfall for seasonal businesses
  when applied to revenue/earnings fundamentals. If ever revisited, it would need
  explicit seasonal-adjustment logic and clear "annualized, short-run only" labeling — a
  substantially larger feature than this phase's FY-to-FY CAGR.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GROW-01 | Consumer can query 3-year and 5-year CAGR for revenue, net income, and total assets per `(cik, fiscal_year)`, computed via N-year self-join against `financial_derived` (same join shape as the existing 1-year `prior_year_values` pattern), with null when insufficient history exists. | `financial_factors.sql`'s existing `prior_fy_values` CTE (lines 17-31) is the exact template — confirmed by direct file read. Two new CTEs (`prior_fy_values_3y`, `prior_fy_values_5y`) extend this pattern; "insufficient history" naturally nulls via `left join` (no matching row at `fiscal_year - N` → all prior-value columns null → `cagr()` macro's null-guard returns null). |
| GROW-02 | CAGR computation handles negative-to-positive and positive-to-negative sign changes without producing a misleading or complex-valued result (explicit null, not a silently wrong number). | D-02 specifies BOTH endpoints must be strictly positive. The `cagr()` macro implements this with a `case` guard identical in structure to `safe_ratio_signed()`, applied to both numerator and denominator (two sign checks, not one) — see Architecture Patterns, Pattern 2. |
| GROW-03 | CAGR factors are documented as requiring N consecutive `FY` fiscal periods; gaps in fiscal-year sequence (e.g. a missed 10-K) produce null, not an incorrect multi-year span treated as N years. | Exact-equality join condition (`py3.fiscal_year = l.fiscal_year - 3`, not a range/tolerance) structurally cannot match a non-N-year-distant row — a gap produces no match, hence null via `left join`. Column-level `description:` in `gold.yml` documents the exact-N-year requirement (mirrors Phase 2's `roic` documentation precedent — see Pitfall 4 analog below). |

</phase_requirements>

## Standard Stack

This phase introduces no new libraries, packages, or dependencies. It is a pure dbt SQL
model extension plus one new dbt macro, using the project's existing dbt + Snowflake
toolchain.

| Tool | Version | Purpose | Provenance |
|------|---------|---------|------------|
| dbt-core | 1.11.8 (pinned in `uv.lock`) | dbt framework | `[VERIFIED: uv.lock]` |
| dbt-snowflake | per `uv.lock` (invoked via `uv run --with dbt-snowflake`) | dbt adapter for Snowflake dynamic tables | `[VERIFIED: repo CLAUDE.md command reference; dbt-core dependency chain confirmed in uv.lock]` |
| Snowflake `POWER()` / `POW()` SQL function | N/A (Snowflake platform built-in) | CAGR exponentiation: `(current/prior)^(1/years)` | `[CITED: docs.snowflake.com/en/sql-reference/functions/pow]` |
| Snowflake dynamic tables | N/A (Snowflake platform feature) | Materialization strategy for `financial_factors` (`gold_model_config` macro) | `[VERIFIED: infra/snowflake/dbt/edgartools_gold/macros/gold_model_config.sql]` |

**Installation:** None required — no new packages for this phase.

## Package Legitimacy Audit

Not applicable. This phase makes zero changes to `pyproject.toml`, `uv.lock`, or any
Python/Node dependency manifest — it is dbt SQL plus a Jinja macro only. The Package
Legitimacy Gate is skipped per its own scope (only applies "whenever this phase installs
external packages").

## Architecture Patterns

### System Architecture Diagram

```
financial_derived (existing gold model — unchanged this phase)
   │  select d.*  (includes: revenue, net_income, total_assets, fiscal_year, fiscal_period)
   ▼
financial_factors.sql :: base CTE  (unchanged)
   │
   ├──────────────► prior_fy_values        (existing, 1-year lookback — UNCHANGED)
   │                   where fiscal_period = 'FY'
   │                   key: (cik, fiscal_year)
   │
   ├──────────────► prior_fy_values_3y     (NEW — this phase)
   │                   where fiscal_period = 'FY'
   │                   key: (cik, fiscal_year)
   │                   selects: revenue, net_income, total_assets
   │
   └──────────────► prior_fy_values_5y     (NEW — this phase)
                       where fiscal_period = 'FY'
                       key: (cik, fiscal_year)
                       selects: revenue, net_income, total_assets
   │
   ▼
financial_factors.sql :: line_items CTE  (unchanged)
   │
   ▼
financial_factors.sql :: final select
   │
   ├─ existing V1 factors (safe_ratio() × 9, FY-only growth × 2)
   ├─ existing V2 profitability/returns factors (Phase 2, 6 columns)
   │
   └─ NEW Phase 1 factors  ◄── this phase's only change
        ├─ revenue_cagr_3y      = cagr(l.revenue,     py3.revenue,     3)   [FY-only gate]
        ├─ net_income_cagr_3y   = cagr(l.net_income,  py3.net_income,  3)   [FY-only gate]
        ├─ total_assets_cagr_3y = cagr(l.total_assets,py3.total_assets,3)   [FY-only gate]
        ├─ revenue_cagr_5y      = cagr(l.revenue,     py5.revenue,     5)   [FY-only gate]
        ├─ net_income_cagr_5y   = cagr(l.net_income,  py5.net_income,  5)   [FY-only gate]
        └─ total_assets_cagr_5y = cagr(l.total_assets,py5.total_assets,5)   [FY-only gate]
   │
   ▼
from line_items l
left join prior_fy_values    py   on py.cik = l.cik  and py.fiscal_year  = l.fiscal_year - 1   (existing)
left join prior_fy_values_3y py3  on py3.cik = l.cik and py3.fiscal_year = l.fiscal_year - 3   (NEW)
left join prior_fy_values_5y py5  on py5.cik = l.cik and py5.fiscal_year = l.fiscal_year - 5   (NEW)
   │
   ▼
EDGARTOOLS_GOLD.FINANCIAL_FACTORS  (Snowflake dynamic table)
   │
   ▼
Consumers (Streamlit dashboard, ad-hoc SQL clients) — out of scope this phase
```

### Recommended Project Structure

No new model files. One new macro file:

```
infra/snowflake/dbt/edgartools_gold/
├── macros/
│   ├── safe_ratio.sql                    # existing — untouched, not reused by this phase
│   ├── safe_ratio_signed.sql             # existing (Phase 2) — pattern template for cagr()'s sign guard
│   ├── yoy_growth.sql                    # existing — null-guard structural template for cagr()
│   └── cagr.sql                          # NEW — cagr(current_col, prior_col, years)
├── models/gold/
│   ├── financial_factors.sql             # MODIFIED — add 2 CTEs + 2 joins + 6 select columns
│   ├── _financial_factors_unit_tests.yml # MODIFIED — add new test cases
│   └── gold.yml                          # MODIFIED — add column-level descriptions for the 6 new CAGR columns
```

### Pattern 1: `prior_fy_values_3y` / `prior_fy_values_5y` CTEs (two CTEs, not one parameterized CTE)

**What:** Two CTEs, structurally identical to the existing `prior_fy_values` (lines
17-31 of the current `financial_factors.sql`), each adding `revenue` and `net_income` to
the selected columns (the existing CTE only selects `total_assets` and
`shares_outstanding` — neither of those two extra columns is needed by this phase, but
they must remain harmless/unused in the new CTEs, or simply omitted since each new CTE
is purpose-built for CAGR).

**Why two CTEs, not a parameterized single CTE:** dbt/Jinja has no native parameterized
CTE call — generating one would require a `{% for years in [3, 5] %}...{% endfor %}`
macro block emitting two near-identical CTE definitions as text, which is strictly more
complex (harder to read, harder to unit-test column-by-column, breaks dbt's static SQL
parsing assumptions in some tooling) than just writing two CTEs directly. The existing
`prior_fy_values` CTE is already a 14-line, easily-copied template — duplicating it
twice with a different join offset and selected columns is the lower-complexity choice,
consistent with the project's established "explicit over clever" pattern (see Phase 2's
own `Don't Hand-Roll` "YAGNI" conclusion about not building a parameterized macro for a
one-character logic change).

**Example (exact syntax, modeled on the existing `prior_fy_values` CTE):**

```sql
-- Source: financial_factors.sql existing pattern, extended (NEW CTEs)
prior_fy_values_3y as (
    select
        cik,
        fiscal_year,
        revenue,
        net_income,
        total_assets
    from base
    where fiscal_period = 'FY'
    qualify row_number() over (
        partition by cik, fiscal_year
        order by
            is_current_period desc,
            accession_number desc
    ) = 1
),

prior_fy_values_5y as (
    select
        cik,
        fiscal_year,
        revenue,
        net_income,
        total_assets
    from base
    where fiscal_period = 'FY'
    qualify row_number() over (
        partition by cik, fiscal_year
        order by
            is_current_period desc,
            accession_number desc
    ) = 1
)
```

Note: `prior_fy_values_3y` and `prior_fy_values_5y` are **identical in body** — the only
difference is which `fiscal_year` offset they get joined against in the final `select`'s
`left join` clause, not anything in the CTE definition itself. This is intentional and
matches the existing `prior_fy_values` CTE's own design (it has no offset baked into the
CTE — the `- 1` lives entirely in the final join condition, line 109 of the current
file). **Implication for the planner:** because the CTE bodies are byte-for-byte
identical except name, consider whether dbt's `ephemeral` materialization or a single
shared CTE selecting ALL fiscal years (not just `fiscal_year - 3` / `fiscal_year - 5`
specifically) and joining twice would be simpler — see Open Questions below.

### Pattern 2: `cagr()` macro — self-guarding, matches `safe_ratio_signed()` precedent

**What:** A macro computing `(current/prior)^(1/years) - 1`, guarding BOTH operands for
strict positivity (D-02) before calling `POWER()`. This is the single most
implementation-critical piece of this phase.

**Why guard both operands explicitly (not just rely on join-side filtering):**
Snowflake's official `POW`/`POWER` documentation page does not document behavior for a
negative base with a fractional exponent (confirmed via direct fetch of
`docs.snowflake.com/en/sql-reference/functions/pow` — the page shows only positive-base,
integer-exponent examples). Mathematically, a negative base raised to a fractional
exponent (`1/years`, e.g. `1/3` or `1/5`) is undefined in the reals (would require
complex-number arithmetic) — Snowflake could plausibly return `NULL`, `NaN`, or raise a
numeric error for this input; this is a **verify-before-relying-on** gap, not a
confirmed-safe behavior. Given that, the macro should NEVER pass a non-positive value
into `POWER()`'s base argument — this is defense-in-depth consistent with Phase 2's
established pattern (every macro in this codebase is a self-contained null-safe unit;
none rely on the caller/upstream join to have already validated inputs).

**Example (matches `safe_ratio_signed.sql`'s exact macro syntax/whitespace style):**

```sql
-- Source: infra/snowflake/dbt/edgartools_gold/macros/cagr.sql (NEW)
{% macro cagr(current_col, prior_col, years) %}
    case
        when {{ current_col }} is not null
         and {{ prior_col }} is not null
         and {{ current_col }} > 0
         and {{ prior_col }} > 0
        then power({{ current_col }} / {{ prior_col }}, 1.0 / {{ years }}) - 1
    end
{% endmacro %}
```

**Usage in `financial_factors.sql`:**

```sql
case
    when l.fiscal_period = 'FY'
    then {{ cagr('l.revenue', 'py3.revenue', 3) }}
end as revenue_cagr_3y,
case
    when l.fiscal_period = 'FY'
    then {{ cagr('l.net_income', 'py3.net_income', 3) }}
end as net_income_cagr_3y,
case
    when l.fiscal_period = 'FY'
    then {{ cagr('l.total_assets', 'py3.total_assets', 3) }}
end as total_assets_cagr_3y,
case
    when l.fiscal_period = 'FY'
    then {{ cagr('l.revenue', 'py5.revenue', 5) }}
end as revenue_cagr_5y,
case
    when l.fiscal_period = 'FY'
    then {{ cagr('l.net_income', 'py5.net_income', 5) }}
end as net_income_cagr_5y,
case
    when l.fiscal_period = 'FY'
    then {{ cagr('l.total_assets', 'py5.total_assets', 5) }}
end as total_assets_cagr_5y,
```

Note the outer `case when l.fiscal_period = 'FY'` wrapper mirrors the existing
`asset_growth_yoy` pattern (lines 85-88 of the current file) exactly — this is the
established convention for FY-gating a factor in this model, distinct from the
macro-internal null/sign guard. **`1.0 / years` (not `1 / years`):** Snowflake (like
most SQL engines) performs integer division when both operands are integers — `1 / 3`
would truncate to `0`, making every CAGR exponent `0` and the whole formula evaluate to
`1 - 1 = 0`. Using `1.0 / {{ years }}` (or equivalently `{{ years }}` passed as a literal
float, or wrapping in `::float`) forces floating-point division. This is the single most
likely silent-bug vector in this phase — flag it explicitly in the plan's verification
steps.

**Float literal alternative if Jinja renders `years` ambiguously:** if the macro call
site passes `3`/`5` as Jinja-rendered integers, confirm the rendered SQL text is
`1.0 / 3` (correct) and not `1 / 3` (wrong) by inspecting `dbt compile` output for this
model — do not assume Jinja's string interpolation preserves the `1.0` correctly without
checking the compiled SQL.

### Pattern 3: dbt unit-test fixture conventions for D-02/D-03 coverage

**What:** Following `_financial_factors_unit_tests.yml`'s existing `<<: *factor_row_defaults`
anchor-merge pattern (see Phase 2's identical convention, already used for
`financial_factors_negative_equity_nulls_roe`), add fixture rows at multiple
`fiscal_year` offsets within a single test case's `given.rows` list to populate the
self-join's prior-year side.

**Critical structural requirement:** Because `prior_fy_values_3y`/`prior_fy_values_5y`
select from `base` (which selects from `financial_derived`, the unit test's mocked
`ref()` input), a CAGR unit test needs **multiple `given` rows at different
`fiscal_year` values for the same `cik`** — not just one row per test case as Phase 2's
margin/ROE tests used (those were single-period, no self-join dependency). This mirrors
the existing `financial_factors_complete_fy_ratios` test, which already uses two rows
(`fiscal_year: 2023` and `fiscal_year: 2024`, same `cik: 1`) to test the existing 1-year
`asset_growth_yoy`/`shares_outstanding_yoy_change` factors via the `prior_fy_values`
join — the CAGR tests need the same two-row-minimum shape, but spanning exactly 3 and 5
years for dedicated CAGR-specific test cases (the existing 2023/2024 pair only tests the
1-year join, not 3yr/5yr).

**Needed fixture rows (minimum set per the the phase's required coverage):**

1. **Happy path (3yr and 5yr both compute):** `cik: 10`, rows at `fiscal_year: 2019, 2021,
   2024` (gives both a `fiscal_year - 3` match for 2024→2021 and `fiscal_year - 5` match for
   2024→2019), all `revenue`/`net_income`/`total_assets` positive at both endpoints.
   Verify expected CAGR value against a hand-computed value (`(current/prior)^(1/years) -
   1`), not assumed — same caution Phase 2's research flagged for floating-point output
   precision.
2. **D-02 negative endpoint (current period):** `cik: 11`, current-year `net_income`
   negative, prior-year (N years back) `net_income` positive → `net_income_cagr_Ny` must
   be null while `revenue_cagr_Ny`/`total_assets_cagr_Ny` (unaffected columns, still
   positive at both ends) compute normally in the same row — proves the macro's guard is
   per-column, not an all-or-nothing row-level null.
3. **D-02 negative endpoint (prior period):** `cik: 12`, current-year positive, but the
   N-years-prior row has a negative value for the same field → must null, proving the
   guard checks BOTH operands, not just the numerator.
4. **D-02 negative-to-negative (the specific case D-02's rationale calls out):**
   `cik: 13`, both current and prior `net_income` negative (e.g. -50 and -100, an
   "improving" trend) → must null despite the mathematically-computable-but-misleading
   positive CAGR a naive implementation would produce. This is the most important test
   case in the suite — it is the literal scenario D-02's rationale describes and the
   one most likely to be silently wrong if the macro's guard is implemented as "numerator
   sign matches denominator sign" instead of "both strictly positive."
5. **D-03 fiscal-year gap (no exact match exists):** `cik: 14`, rows at `fiscal_year:
   2020, 2024` only (gap — no 2021 row, so `fiscal_year - 3` from 2024 finds nothing) →
   `*_cagr_3y` columns must all be null for the 2024 row (no matching `prior_fy_values_3y`
   row), while `*_cagr_5y` would also be null here (no 2019 row either) — consider a
   richer fixture that isolates 3yr-gap-but-5yr-present, or vice versa, to prove the two
   join offsets are independent and a gap in one doesn't null the other.
6. **Quarterly rows do not receive CAGR (D-01):** reuse the existing
   `financial_factors_quarterly_cross_year_factors_are_null` test case (already exists,
   already proves `asset_growth_yoy`/`shares_outstanding_yoy_change` null on `Q1` rows)
   — extend its `expect` block to also assert all 6 new CAGR columns are null for that
   row, rather than writing a new test case from scratch.

**Why this matters more than Phase 2's tests:** Phase 2's new factors (margins, ROE,
ROA) were single-period computations with no self-join dependency — every fixture needed
only one row. This phase's CAGR factors fundamentally depend on a working multi-row
self-join, so the test fixtures must establish realistic multi-year `cik` histories, not
just single isolated rows. Under-fixturing (e.g. only ever testing a 2-row, exactly
N-years-apart scenario) would not catch a join-key bug (e.g. accidentally joining on
`fiscal_period` instead of just `cik`/`fiscal_year`, which would silently break for any
company whose accession includes both `FY` and `Q4` rows for the same `period_end`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Compound growth rate math | Inline `power()` expression per factor, or a hand-rolled Newton's-method/log-based nth-root | `cagr()` macro (new, this phase) | Centralizes the sign-guard + exponent-math in one tested, reusable unit — matches every other ratio/growth factor in this model. |
| Multi-year self-join | A single mega-CTE with `union all` across offsets, or a recursive CTE | Two parallel CTEs (`prior_fy_values_3y`, `prior_fy_values_5y`), each a near-copy of the existing `prior_fy_values` | The existing 1-year CTE is already the simplest correct shape; copying it twice with different offsets is lower-risk than inventing a more "clever" unified join. |
| Integer/float division pitfall | Trusting `1 / years` to produce a float | `1.0 / {{ years }}` (explicit float literal) | Snowflake performs integer division when both operands are integer-typed — `1/3` truncates to `0`, silently breaking every CAGR value to `0`. This is a textbook SQL pitfall, not specific to this codebase, but easy to miss in a Jinja-templated macro where the literal `1.0` isn't visually adjacent to the variable. |

**Key insight:** This phase's only genuinely new logic is the CAGR formula itself
(`POWER()`-based) and its dual-operand sign guard — everything else (CTE shape, join
pattern, FY-gating `case` wrapper, unit-test fixture conventions) is a direct, low-risk
extension of patterns the codebase has already established and proven in `financial_factors.sql`
and Phase 2's `safe_ratio_signed()`.

## Common Pitfalls

### Pitfall 1: Integer division silently zeroing every CAGR exponent

**What goes wrong:** Writing `power(current/prior, 1/years)` instead of
`power(current/prior, 1.0/years)` — Snowflake truncates `1/3` and `1/5` to `0` under
integer division, making `power(x, 0)` evaluate to `1` for every row, so every CAGR
column silently becomes `1 - 1 = 0` instead of erroring or producing an obviously wrong
value. This is a SILENT bug — no error, no null, just a wrong "0% CAGR" for every company,
which could easily pass a superficial smoke test (a `0` looks like a plausible growth
rate at first glance, especially for a flat-revenue company).

**Why it happens:** SQL's default integer/integer division behavior is a well-known
trap that's easy to miss in a parameterized macro, since the literal `1.0` isn't
adjacent to `years` in the call site — it's buried inside the macro body.

**How to avoid:** Use `1.0 / {{ years }}` explicitly in the macro. Verify via a unit
test with a known hand-computed expected CAGR value (not `0`) for at least one fixture
row — if the test fixture's expected value happens to be near zero for unrelated
reasons, this bug could pass undetected; pick a fixture with an obviously non-zero,
easily-verified CAGR (e.g. revenue doubling over 3 years → CAGR ≈ 0.2599, not 0).

**Warning signs:** Every `*_cagr_3y`/`*_cagr_5y` column showing exactly `0` (or exactly
`-1`, the symptom if the macro accidentally inverts current/prior) across multiple
different companies/fixture rows would indicate this exact bug.

### Pitfall 2: Negative-to-negative CAGR passing a naive same-sign check

**What goes wrong:** Implementing the guard as "numerator and denominator have the same
sign" (e.g. `sign(current) = sign(prior)`) instead of "both strictly positive" would
incorrectly ALLOW a negative-to-negative CAGR to compute — exactly the case D-02's
rationale explicitly warns about (`-100 → -50` is an "improving but still negative"
trend that would produce a misleadingly positive CAGR number).

**Why it happens:** "Sign change produces a complex number" (the literal GROW-02
wording) is a narrower condition than D-02's actual decision ("either endpoint
negative or zero nulls the result") — a same-sign check satisfies the narrow reading of
GROW-02 but violates D-02's explicit, broader decision.

**How to avoid:** The macro's guard must be `current_col > 0 and prior_col > 0` (both
strictly positive), never `sign(current_col) = sign(prior_col)` or any equivalent
same-sign-allowing logic. Test case 4 in Pattern 3 above (`cik: 13`, both negative)
exists specifically to catch this class of bug — do not skip it.

**Warning signs:** A unit test with both endpoints negative producing a non-null,
positive CAGR value.

### Pitfall 3: Snowflake `POWER()` with negative base — unverified edge case reaching production

**What goes wrong:** If the macro's guard has any gap (e.g. only checking `current_col >
0` but forgetting `prior_col > 0`, or vice versa), a negative value could still reach
`POWER()`'s base argument with the fractional `1.0/years` exponent — Snowflake's
documented behavior for this specific combination (negative base, fractional exponent)
is not established in the official docs (confirmed via direct fetch — the docs page
shows no example for this case). This could mean a runtime error (failing the entire
dynamic table refresh, the same class of failure `safe_ratio()` was built to prevent for
division-by-zero), a silent `NULL`, or a `NaN` — none of which are acceptable
uninvestigated.

**Why it happens:** Easy to assume `POWER()` behaves like a typical exponent function
without checking the negative-base/fractional-exponent edge case specifically, since
positive-base cases (the vast majority of real financial data) work as expected.

**How to avoid:** The macro's guard (Pattern 2) ensures `POWER()` NEVER receives a
non-positive base — defense-in-depth, not relying on the FY-gating `case` wrapper or
upstream join filtering alone. If a future maintainer ever modifies the macro and
weakens this guard, a live `dbt test`/`dbt run` against real Snowflake data is the only
way to discover the actual runtime behavior — recommend a follow-up note in the macro's
own SQL comment warning against removing the guard, given the undocumented Snowflake
behavior.

**Warning signs:** A `dbt run --select financial_factors --full-refresh` failure with a
Snowflake numeric/domain error mentioning `POWER`, or `NaN`/`Infinity` values appearing
in a CAGR column in production data.

### Pitfall 4: `prior_fy_values_3y`/`prior_fy_values_5y` accidentally keyed wrong (silent join failure)

**What goes wrong:** Copying the existing `prior_fy_values` CTE but forgetting to match
its exact `partition by cik, fiscal_year` (not including `fiscal_period`, since the CTE
is already pre-filtered to `FY` only) would either (a) over-partition if `fiscal_period`
is added to the `qualify row_number() over (partition by ...)` clause unnecessarily
(harmless since it's already filtered to one value, but inconsistent with the existing
CTE's exact shape), or (b) under-partition if `cik`/`fiscal_year` aren't both included,
silently producing duplicate or wrong rows that corrupt the self-join.

**Why it happens:** Easy to "improve" or restructure the copied CTE while porting it,
introducing a subtle divergence from the proven 1-year CTE's exact key shape.

**How to avoid:** Copy `prior_fy_values`'s structure byte-for-byte (the `where
fiscal_period = 'FY'` filter, the `partition by cik, fiscal_year` qualify clause, the
`is_current_period desc, accession_number desc` tiebreaker order) and only change the
CTE name and the additional selected columns (`revenue`, `net_income` beyond
`total_assets`). Do not "clean up" or restructure during the port.

**Warning signs:** A unit test expecting exactly one CAGR value per `(cik, fiscal_year)`
producing duplicate rows or an unexpected `null` where a value was expected — would
indicate the self-join's CTE produced more than one row per key, fanning out the final
join.

### Pitfall 5: dbt unit tests check the FULL result row, not a subset (same as Phase 2's Pitfall 3)

**What goes wrong:** A new CAGR unit test's `expect.rows` entry only lists the new CAGR
columns, but per `_financial_derived_unit_tests.yml`'s own documented dbt semantics,
columns omitted from an `expect` row are NOT checked (omission means "don't assert,"
not "assert null/ignore") — so this isn't actually a failure risk the way Phase 2's
research framed it, but the inverse risk applies: a test author might assume an omitted
column is implicitly checked as null and be surprised when an unrelated regression in,
say, `gross_margin` doesn't fail this new CAGR-focused test.

**Why it happens:** Same dbt unit-test column-omission semantics Phase 2's research
already identified and documented — repeating here because this phase's tests are new
fixtures, not extensions of existing ones, so the convention must be re-applied
correctly from scratch.

**How to avoid:** Mirror the granularity already used in `_financial_factors_unit_tests.yml`'s
existing test cases — list the columns specifically relevant to what each CAGR test
case is verifying (the 6 new CAGR columns, plus `working_capital`/`current_ratio`/etc.
only if the fixture's `given` data also makes those meaningfully assertable).

**Warning signs:** A test passing despite an actual CAGR computation bug, because the
`expect` block never asserted the specific column where the bug manifests.

## Runtime State Inventory

Not applicable — this phase is a pure dbt gold-layer SQL/macro addition with no rename,
refactor, or migration of existing identifiers, data, or external service configuration.
No stored data, live service config, OS-registered state, secrets, or build artifacts
reference the new column names (`revenue_cagr_3y`, etc.) prior to this phase, since they
do not yet exist. **Confirmed by inspection:** no grep hits for `cagr` anywhere in the
repo outside `.planning/` planning artifacts (verified during this research session).

## Code Examples

### Full proposed diff shape for `financial_factors.sql` (illustrative, exact line numbers as of this research — see file for current state)

```sql
-- Source: existing financial_factors.sql (current state, lines 17-38), extended with two new CTEs
prior_fy_values as (
    select
        cik,
        fiscal_year,
        total_assets,
        shares_outstanding
    from base
    where fiscal_period = 'FY'
    qualify row_number() over (
        partition by cik, fiscal_year
        order by
            is_current_period desc,
            accession_number desc
    ) = 1
),

prior_fy_values_3y as (
    select
        cik,
        fiscal_year,
        revenue,
        net_income,
        total_assets
    from base
    where fiscal_period = 'FY'
    qualify row_number() over (
        partition by cik, fiscal_year
        order by
            is_current_period desc,
            accession_number desc
    ) = 1
),

prior_fy_values_5y as (
    select
        cik,
        fiscal_year,
        revenue,
        net_income,
        total_assets
    from base
    where fiscal_period = 'FY'
    qualify row_number() over (
        partition by cik, fiscal_year
        order by
            is_current_period desc,
            accession_number desc
    ) = 1
),

line_items as (
    select
        *,
        current_assets - current_liabilities as working_capital
    from base
)
```

```sql
-- Source: existing financial_factors.sql final select (current state, lines 96-109), extended
    -- V2 profitability and returns factors (Phase 2).
    {{ safe_ratio('l.gross_profit', 'l.revenue') }} as gross_margin,
    {{ safe_ratio('l.ebit', 'l.revenue') }} as operating_margin,
    {{ safe_ratio('l.net_income', 'l.revenue') }} as net_margin,
    {{ safe_ratio_signed('l.net_income', 'l.total_equity') }} as return_on_equity,
    {{ safe_ratio('l.net_income', 'l.total_assets') }} as return_on_assets,
    l.roic,

    -- V2 growth factors: N-year CAGR (Phase 1).
    case
        when l.fiscal_period = 'FY'
        then {{ cagr('l.revenue', 'py3.revenue', 3) }}
    end as revenue_cagr_3y,
    case
        when l.fiscal_period = 'FY'
        then {{ cagr('l.net_income', 'py3.net_income', 3) }}
    end as net_income_cagr_3y,
    case
        when l.fiscal_period = 'FY'
        then {{ cagr('l.total_assets', 'py3.total_assets', 3) }}
    end as total_assets_cagr_3y,
    case
        when l.fiscal_period = 'FY'
        then {{ cagr('l.revenue', 'py5.revenue', 5) }}
    end as revenue_cagr_5y,
    case
        when l.fiscal_period = 'FY'
        then {{ cagr('l.net_income', 'py5.net_income', 5) }}
    end as net_income_cagr_5y,
    case
        when l.fiscal_period = 'FY'
        then {{ cagr('l.total_assets', 'py5.total_assets', 5) }}
    end as total_assets_cagr_5y,

    l.parser_version,
    l.ingested_at
from line_items l
left join prior_fy_values py
    on py.cik = l.cik
    and py.fiscal_year = l.fiscal_year - 1
left join prior_fy_values_3y py3
    on py3.cik = l.cik
    and py3.fiscal_year = l.fiscal_year - 3
left join prior_fy_values_5y py5
    on py5.cik = l.cik
    and py5.fiscal_year = l.fiscal_year - 5
```

### New macro file

```sql
-- Source: infra/snowflake/dbt/edgartools_gold/macros/cagr.sql (NEW)
-- Compound Annual Growth Rate: (current/prior)^(1/years) - 1.
-- Nulls when either endpoint is missing, zero, or negative (D-02) — a
-- negative-to-negative span is mathematically computable but produces a
-- misleadingly positive CAGR for a still-unprofitable company, and
-- Snowflake's POWER() does not document negative-base/fractional-exponent
-- behavior, so this guard is required, not optional defense-in-depth.
{% macro cagr(current_col, prior_col, years) %}
    case
        when {{ current_col }} is not null
         and {{ prior_col }} is not null
         and {{ current_col }} > 0
         and {{ prior_col }} > 0
        then power({{ current_col }} / {{ prior_col }}, 1.0 / {{ years }}) - 1
    end
{% endmacro %}
```

### New unit test cases (illustrative — see Pattern 3 for the full required set)

```yaml
# Source: pattern matches existing _financial_factors_unit_tests.yml anchor-merge style
  - name: financial_factors_cagr_happy_path
    description: >
      3yr and 5yr CAGR compute correctly for revenue, net_income, total_assets
      when exact fiscal_year - N rows exist (GROW-01).
    model: financial_factors
    given:
      - input: ref('financial_derived')
        rows:
          - <<: *factor_row_defaults
            cik: 10
            accession_number: "0010"
            fiscal_year: 2019
            period_end: "2019-12-31"
            revenue: 100
            net_income: 10
            total_assets: 200
          - <<: *factor_row_defaults
            cik: 10
            accession_number: "0011"
            fiscal_year: 2021
            period_end: "2021-12-31"
            revenue: 130
            net_income: 13
            total_assets: 230
          - <<: *factor_row_defaults
            cik: 10
            accession_number: "0012"
            fiscal_year: 2024
            period_end: "2024-12-31"
            revenue: 200
            net_income: 25
            total_assets: 300
    expect:
      rows:
        - cik: 10
          accession_number: "0010"
          fiscal_year: 2019
          revenue_cagr_3y: null
          revenue_cagr_5y: null
        - cik: 10
          accession_number: "0011"
          fiscal_year: 2021
          revenue_cagr_3y: null
          revenue_cagr_5y: null
        - cik: 10
          accession_number: "0012"
          fiscal_year: 2024
          # revenue_cagr_3y = (200/130)^(1/3) - 1 -- verify exact value via dbt build, not by hand
          # revenue_cagr_5y = (200/100)^(1/5) - 1 -- verify exact value via dbt build, not by hand
          revenue_cagr_3y: 0.154767
          revenue_cagr_5y: 0.148698

  - name: financial_factors_cagr_negative_to_negative_nulls
    description: >
      Negative-to-negative endpoints null CAGR (D-02) even though the ratio is
      mathematically computable and would otherwise look like a positive trend.
    model: financial_factors
    given:
      - input: ref('financial_derived')
        rows:
          - <<: *factor_row_defaults
            cik: 13
            accession_number: "0013"
            fiscal_year: 2021
            period_end: "2021-12-31"
            net_income: -100
          - <<: *factor_row_defaults
            cik: 13
            accession_number: "0014"
            fiscal_year: 2024
            period_end: "2024-12-31"
            net_income: -50
    expect:
      rows:
        - cik: 13
          accession_number: "0013"
          fiscal_year: 2021
          net_income_cagr_3y: null
        - cik: 13
          accession_number: "0014"
          fiscal_year: 2024
          net_income_cagr_3y: null
```

Note: the `revenue_cagr_3y`/`revenue_cagr_5y` expected values in the happy-path example
(`0.154767`, `0.148698`) are illustrative hand-computed approximations — **must be
verified against a real `dbt build`/`dbt test` run** before committing the fixture's
expected value, per the same floating-point-precision caution Phase 2's research already
flagged for its own unit tests (Snowflake's exact `POWER()` floating-point output
precision should not be assumed from manual arithmetic).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A — first-time addition of multi-year CAGR factors to `financial_factors` | `cagr()` macro + parallel `prior_fy_values_3y`/`prior_fy_values_5y` CTEs, modeled on the existing 1-year `prior_fy_values` pattern | This phase (Phase 1) | No prior state to compare; this IS the "current approach" being established for N-year growth metrics in this codebase. |

**Deprecated/outdated:** Nothing in this phase deprecates existing behavior — the
existing `prior_fy_values` CTE and `asset_growth_yoy`/`shares_outstanding_yoy_change`
factors (1-year YoY) remain completely unchanged.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Recommended macro name `cagr` and signature `cagr(current_col, prior_col, years)` (vs. some other name/parameter order) | Architecture Patterns, Pattern 2 | Low — purely cosmetic; planner/implementer can rename/reorder freely without behavior change, since this is genuinely "Claude's Discretion" per CONTEXT.md. |
| A2 | Recommendation to use two separate CTEs (`prior_fy_values_3y`, `prior_fy_values_5y`) rather than one parameterized/generated CTE | Architecture Patterns, Pattern 1 | Low-medium — if the planner instead chooses a single `{% for %}`-generated CTE block, GROW-01's functional requirement is still satisfiable, but with more Jinja complexity; flagging only because CONTEXT.md left this explicitly as "Claude's Discretion." |
| A3 | Snowflake's `POWER()` function behavior for a negative base with a fractional exponent is undocumented and therefore should be defensively guarded against, never relied upon | Architecture Patterns, Pattern 2; Common Pitfalls, Pitfall 3 | Medium — this assumption drives the recommendation to guard inside the macro itself (defense-in-depth) rather than trusting upstream join/FY-gating alone. If Snowflake's actual behavior is benign (e.g. returns NULL gracefully), the extra guard is still harmless (it's a stricter superset of D-02's requirement anyway) — so the practical risk of this assumption being wrong is low, but it should not be presented as a confirmed Snowflake behavior. |
| A4 | Exact hand-computed CAGR values in the illustrative unit test example (`0.154767`, `0.148698`) | Code Examples | Low — explicitly flagged in the accompanying note as illustrative/unverified; implementer must confirm against a real `dbt build` run before committing. |
| A5 | `revenue`, `net_income`, `total_assets` are NOT affected by the documented dev-environment `SEC_FINANCIAL_DERIVED` source-schema staleness gap (only `current_assets` and 7 sibling columns from the `ALTER TABLE ADD COLUMN` block are affected) | Summary; Environment Availability | Medium — based on direct read of `infra/snowflake/sql/bootstrap/01_source_stage.sql` showing these 3 columns in the original `CREATE TABLE` statement, not the `ALTER TABLE` block. This is a structural/textual inference from the bootstrap SQL definition, not a live query against the actual dev Snowflake account's deployed schema — the actual deployed table could still be missing columns for other undocumented reasons. Recommend a quick `DESCRIBE TABLE EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED` (or equivalent) check at execution time before assuming this phase's `dbt test` will pass where Phase 2's did not. |

**If this table is empty:** N/A — see entries above.

## Open Questions

1. **Should `prior_fy_values_3y` and `prior_fy_values_5y` be collapsed into a single CTE
   that selects ALL FY rows (not pre-filtered to a specific offset), with both offsets
   joined against the SAME CTE in two separate `left join`s?**
   - What we know: Both CTE bodies (Pattern 1) are byte-for-byte identical except name —
     the offset (`- 3` vs `- 5`) lives entirely in the join condition, not the CTE
     itself. This means a SINGLE CTE (call it `prior_fy_values_all` or similar,
     selecting `cik`, `fiscal_year`, `revenue`, `net_income`, `total_assets` for every
     FY row, deduplicated the same way) could be joined TWICE — once for the 3-year
     offset, once for the 5-year offset — eliminating the duplicate CTE definition
     entirely.
   - What's unclear: Whether this also subsumes the EXISTING `prior_fy_values` CTE
     (1-year offset, currently selecting `total_assets`/`shares_outstanding`) — if
     `shares_outstanding` were added to this unified CTE, all three offsets (1yr, 3yr,
     5yr) could share ONE CTE definition with three separate joins, which would actually
     simplify the existing code too, not just avoid duplicating it for this phase.
   - Recommendation: This is a legitimate simplification opportunity, but **changing the
     existing `prior_fy_values` CTE is out of this phase's stated boundary** ("Pure dbt
     gold-layer SQL... extend `financial_factors.sql`" — CONTEXT.md's `<domain>` section
     does not authorize touching the existing 1-year CTE). Recommend the planner choose
     the safer, more conservative option (two new, separate CTEs, Pattern 1 as written)
     for this phase, and log the unification opportunity as a candidate for a future
     cleanup phase rather than scope-creeping into modifying proven, already-shipped
     code. Flagging here so the planner makes this choice deliberately rather than by
     default.

2. **Exact dbt unit test floating-point precision for `POWER()`-based CAGR values.**
   - What we know: Phase 2's research already flagged the same general caution for
     `safe_ratio()`-based division (e.g. `-10/150 = -0.0667` needing verification against
     real `dbt build` output, not hand arithmetic) — `POWER()` with a fractional exponent
     compounds this risk further, since nth-root computation has more floating-point
     surface area than simple division.
   - What's unclear: Whether Snowflake's `POWER()` returns full double precision or
     truncates/rounds at some fixed decimal count, and whether dbt unit tests' row
     comparison tolerates any floating-point epsilon or requires exact match.
   - Recommendation: Treat every CAGR expected-value fixture as a placeholder requiring
     live verification against an actual `dbt build`/`dbt test` run before the plan is
     considered complete — do not trust this research's illustrative numbers.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| dbt-core / dbt-snowflake toolchain | All dbt compile/test/run commands | ✓ | dbt-core 1.11.8 (`uv.lock`) | — |
| Live Snowflake connection (`snowconn` dev) | `dbt test --target prod`/full validation | ✓ (connection exists) | — | `dbt compile`-only validation if live test blocked (see below) |
| `EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED` source table — fully synced schema | Live `dbt test --select financial_factors` execution | **⚠ Unverified / at risk** | — | Same Phase 2 blocker may recur; `dbt compile`/`dbt parse` validation remains a fallback that does NOT require live data |

**Missing dependencies with no fallback:** None — `dbt compile`/`dbt parse` (syntax/Jinja
validation) does not require a live Snowflake connection and can validate this phase's
SQL/macro correctness independent of the source-schema staleness issue.

**Missing dependencies with fallback:** Live `dbt test --select financial_factors`
execution is at risk of hitting the SAME pre-existing dev-environment source-schema
staleness blocker documented in STATE.md's "Blockers" section for Phase 2 — **this
phase's required input columns (`revenue`, `net_income`, `total_assets`) are NOT
themselves part of the known-missing column set** (confirmed via direct read of
`infra/snowflake/sql/bootstrap/01_source_stage.sql`: these three columns are in the
original `CREATE TABLE SEC_FINANCIAL_DERIVED` statement, not the `ALTER TABLE ... ADD
COLUMN IF NOT EXISTS` block that is the actual source of the gap). However, **the
blocker manifests at the whole-model level** — Phase 2's `dbt test` failed because
`financial_derived`'s OWN unit test fixture references `current_assets` (a different,
affected column), and that failure blocks `dbt test --select financial_factors` from
running at all (since `financial_factors` depends on `financial_derived` in the DAG).
**This phase cannot assume Phase 2's blocker is resolved** — if it is still open when
this phase executes, the same live-test execution risk applies here too, for the same
root cause, even though this phase's own new columns are unaffected. The plan should
document this risk explicitly (matching the additional_context's explicit ask) rather
than assuming a clean live-test run.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | dbt unit tests (`unit_tests:` YAML spec, dbt-core native feature) |
| Config file | `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml` |
| Quick run command | `cd infra/snowflake/dbt/edgartools_gold && uv run --with dbt-snowflake dbt test --select financial_factors` |
| Full suite command | `cd infra/snowflake/dbt/edgartools_gold && uv run --with dbt-snowflake dbt test --target prod` |

Note (same caveat Phase 2's research already documented): dbt unit tests mock `ref()`
inputs and do not strictly require a live warehouse connection for the unit-test
assertions themselves, but this repo's actual CLI invocation (`dbt test`) still requires
a configured target/connection to start up — confirm at execution time whether
`dbt compile`-only validation is an acceptable substitute if the live-connection
blocker (see Environment Availability) is still open.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GROW-01 | 3yr/5yr CAGR compute correctly for revenue/net_income/total_assets given exact N-year-apart FY rows | unit | `dbt test --select financial_factors` (new test: `financial_factors_cagr_happy_path`) | Wave 0 — new test |
| GROW-01 | CAGR nulls when insufficient history exists (no row at all at `fiscal_year - N`) | unit | `dbt test --select financial_factors` (new test, e.g. `financial_factors_cagr_insufficient_history`) | Wave 0 — new test |
| GROW-02 | Negative-to-negative endpoints null CAGR (not a misleadingly positive value) | unit | `dbt test --select financial_factors` (new test: `financial_factors_cagr_negative_to_negative_nulls`) | Wave 0 — new test |
| GROW-02 | Negative current-period endpoint (positive prior) nulls CAGR | unit | `dbt test --select financial_factors` (new test, fixture row in Pattern 3 item 2) | Wave 0 — new test |
| GROW-02 | Negative prior-period endpoint (positive current) nulls CAGR | unit | `dbt test --select financial_factors` (new test, fixture row in Pattern 3 item 3) | Wave 0 — new test |
| GROW-03 | Fiscal-year gap (no exact `fiscal_year - N` match) nulls CAGR, not a fuzzy-matched span | unit | `dbt test --select financial_factors` (new test: `financial_factors_cagr_fiscal_year_gap`) | Wave 0 — new test |
| GROW-01/02/03 | Quarterly (`Q1`-`Q4`) rows never receive a CAGR value (D-01) | unit | `dbt test --select financial_factors` (extend existing `financial_factors_quarterly_cross_year_factors_are_null`) | Wave 0 — extend existing file |

### Sampling Rate

- **Per task commit:** `dbt test --select financial_factors` (scoped, fast)
- **Per wave merge:** `dbt test --target prod` (full suite, confirms no regression in
  sibling models)
- **Phase gate:** Full suite green before `/gsd-verify-work` — **but see Environment
  Availability above: this gate may be blocked by the same pre-existing dev-environment
  source-schema staleness issue documented for Phase 2.** If still open, the plan should
  document `dbt compile`/`dbt parse` success as the achievable verification bar and
  explicitly flag live `dbt test` as deferred/blocked, exactly as Phase 2's plan did,
  rather than silently treating compile success as equivalent to test success.

### Wave 0 Gaps

- [ ] `infra/snowflake/dbt/edgartools_gold/macros/cagr.sql` — new macro, does not exist yet
- [ ] New unit test cases in `_financial_factors_unit_tests.yml` covering: (a) happy-path
      3yr/5yr CAGR, (b) negative-to-negative nulling, (c) single-endpoint-negative
      nulling (both directions), (d) fiscal-year-gap nulling, (e) quarterly-row
      exclusion (extend existing test)
- None other — `dbt test` infrastructure, fixture-anchor conventions, and the model file
      itself all already exist; this phase only adds to them.

## Security Domain

Not applicable — this phase has no input validation, authentication, session, or
cryptography surface. It is read-only financial-ratio computation over already-validated
SEC XBRL data inside a Snowflake dynamic table. No ASVS category applies.

## Sources

### Primary (HIGH confidence)
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` (repo, read
  directly, current post-Phase-2-merge state) — existing `prior_fy_values` CTE shape,
  join condition, V1/V2 factor placement.
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_derived.sql` (repo, read
  directly) — confirms `revenue`, `net_income`, `total_assets` are selected and
  available; confirms `prior_year_values` 1-year self-join precedent.
- `infra/snowflake/dbt/edgartools_gold/macros/yoy_growth.sql`,
  `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio.sql`,
  `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql` (repo, read
  directly) — exact macro syntax/style templates for the new `cagr()` macro.
- `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml`
  (repo, read directly, current post-Phase-2-merge state) — exact test fixture
  conventions, confirms the `<<: *factor_row_defaults` anchor-merge pattern.
- `infra/snowflake/sql/bootstrap/01_source_stage.sql` (repo, read directly, lines
  258-307) — confirms `revenue`/`net_income`/`total_assets` are in the original
  `CREATE TABLE SEC_FINANCIAL_DERIVED` statement, not the `ALTER TABLE ADD COLUMN`
  block that is the source of the documented dev-environment staleness gap.
- `uv.lock` (repo, read directly) — confirms dbt-core 1.11.8 pinned.
- `.planning/workstreams/fundamental-factors-v2/STATE.md` (repo, read directly) —
  Phase 2 live `dbt test` blocker details, confirmed still open as of this research.

### Secondary (MEDIUM confidence)
- `https://docs.snowflake.com/en/sql-reference/functions/pow` `[CITED]` — fetched
  directly; confirms `POWER`/`POW` syntax and positive-base/integer-exponent examples,
  but does NOT document negative-base/fractional-exponent behavior — this absence is
  itself the finding driving this phase's defensive-guard recommendation (Pitfall 3).

### Tertiary (LOW confidence)
- WebSearch results on Snowflake `POWER()` negative-base/fractional-exponent behavior
  `[ASSUMED — gap, not a confirmed claim]` — search results did not surface an
  authoritative answer; this is explicitly logged as an unresolved gap (Open Questions
  do not include this since it's resolved via defensive macro design rather than needing
  further research — the guard makes the unknown behavior unreachable).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; existing dbt+Snowflake toolchain confirmed
  via direct file reads (`uv.lock`, `gold_model_config.sql`).
- Architecture: HIGH — every pattern (CTE shape, join condition, macro structure, FY-gating
  wrapper) verified by reading the actual current `financial_factors.sql`/
  `financial_derived.sql`/macro source, not inferred.
- Pitfalls: HIGH for D-02/D-03/CTE-keying pitfalls (grounded in direct code reading and
  CONTEXT.md's explicit decisions); MEDIUM for the Snowflake `POWER()` negative-base
  edge case specifically (the underlying Snowflake behavior itself is unverified — the
  macro's defensive design is the mitigation, not a confirmation of what Snowflake would
  otherwise do).

**Research date:** 2026-06-30
**Valid until:** Stable — single-repo, single-model implementation question with no
external API/library version drift risk. Valid until `financial_factors.sql`,
`financial_derived.sql`, `safe_ratio.sql`/`safe_ratio_signed.sql`, or
`01_source_stage.sql` are next modified by another phase/PR (check `git log` on those
files before reusing this research unmodified). Re-verify the Phase 2 live-`dbt test`
blocker status (STATE.md) immediately before planning, since it may have been resolved
between this research and plan execution.
