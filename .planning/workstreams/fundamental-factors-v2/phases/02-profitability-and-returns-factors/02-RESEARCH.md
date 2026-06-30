# Phase 2: Profitability And Returns Factors - Research

**Researched:** 2026-06-30
**Domain:** dbt gold-layer SQL (Snowflake dynamic tables), accounting ratio computation
**Confidence:** HIGH

## Summary

This phase is a pure dbt SQL extension to one existing model (`financial_factors.sql`),
adding 6 columns: `gross_margin`, `operating_margin`, `net_margin`, `return_on_equity`,
`return_on_assets`, and a pass-through `roic`. All source columns already exist one
model upstream in `financial_derived` and — critically — **`financial_derived` already
computes equivalent margin/return ratios today** (`gross_margin`, `net_margin`, `roe`,
`roa`, `roic`), but using plain unguarded division (`_safe_div` in the Python silver
parser, zero/null-only guard, no sign check). `financial_factors.sql` does not currently
select any of these computed ratio columns from `financial_derived` — it only selects the
raw base inputs (`revenue`, `total_assets`, `net_income`, etc.) and computes its own V1
ratios independently using the dbt `safe_ratio()` macro. This phase must therefore
**recompute** the new factors in `financial_factors.sql` using `safe_ratio()` (matching
the model's own established pattern), not reuse `financial_derived.roe`/`gross_margin`/
etc., because: (a) `operating_margin` doesn't exist upstream at all (only `ebitda_margin`
does — `ebit`/revenue must be computed fresh), (b) the upstream `roe`/`roa` lack the D-01
negative-equity sign guard the user decided on, and (c) `financial_factors.sql`'s own
established convention is "every ratio factor uses `safe_ratio()` in this model," not
"pass through ratios computed upstream." The one column that genuinely is a pass-through
per D-03 is `roic` — `financial_derived.roic` is selected as-is, aliased directly into
`financial_factors`, no recomputation.

**Primary recommendation:** Extend `financial_factors.sql`'s existing `select` list
(after the existing V1 factor block, before `l.parser_version`), reusing `safe_ratio()`
for five factors and adding one new sign-checked macro variant for `return_on_equity`.
Surface `l.roic` as a pass-through (must first add `roic` to the `base`/`line_items` CTE
chain by ensuring it flows from `financial_derived` — see Architecture Patterns). Add new
unit-test cases to `_financial_factors_unit_tests.yml` following the file's existing
`<<: *factor_row_defaults` anchor-merge pattern, with at least one fixture row carrying
negative `total_equity` and negative `net_income` to verify both the ROE null-guard and
the (un-guarded) ROA negative-margin path per Phase 2's roadmap success criterion #4.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Margin/return ratio computation | Database / Storage (dbt SQL, Snowflake dynamic table) | — | All inputs already materialized in `financial_derived`; ratio math belongs in the gold SQL layer per the project's existing `safe_ratio()` convention — no app-tier or API-tier computation needed. |
| Negative-equity sign guard | Database / Storage (new dbt macro) | — | Business rule about ratio meaningfulness (Damodaran ROE treatment) is a data-quality concern best enforced once, centrally, in the transformation layer — not duplicated in every downstream consumer query. |
| ROIC pass-through | Database / Storage | — | Already computed in `financial_derived`; this phase only adds a `select` reference, no new computation tier. |
| Consumption (Streamlit dashboard, ad-hoc SQL) | Out of phase scope | — | No app-layer rendering changes in this phase per CONTEXT.md `<specifics>`. |

## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 — Negative equity handling (ROE):** `return_on_equity` nulls when
`total_equity < 0`, rather than computing `net_income / total_equity` as-is.
Research-confirmed: Aswath Damodaran (NYU Stern) treats ROE as "meaningless" under
negative book equity, since negative/negative produces a misleadingly positive value —
recommends nulling and falling back to ROA instead. ~10% of companies in his sample have
negative book equity (buybacks, accumulated losses), so this isn't an edge case to ignore.
Implementation: extend the `safe_ratio()` pattern with an explicit sign check on the
denominator for this one factor (gross margin, operating margin, net margin, ROA use
plain `safe_ratio()` — only ROE needs the extra guard, since revenue and total_assets
aren't expected to go negative the way equity can).

**D-02 — Period scope for new factors:** All new factors (margins, ROE, ROA) compute for
every `fiscal_period` value (FY and quarterly), not restricted to FY-only like the
existing `asset_growth_yoy` factor. Rationale: `asset_growth_yoy`'s FY restriction exists
because YoY growth needs a full prior year for a clean comparison — that constraint
doesn't apply to margins/returns, which are meaningful for any single reporting period on
their own. Restricting to FY would silently drop quarterly data trend-watching consumers
may want.

**D-03 — ROIC trust vs re-derivation:** Phase 2 surfaces the existing
`financial_derived.roic` column as-is (not recomputed) and documents the simplification
in the dbt column description (`gold.yml`). Research-confirmed: textbook ROIC = NOPAT
(EBIT × (1 − tax rate)) / Average Invested Capital — but `financials_derived.py` has no
`income_tax_expense` or effective-tax-rate field parsed anywhere (confirmed via
repo-wide grep, zero matches), so the tax-adjustment input for a textbook NOPAT-based ROIC
doesn't exist in silver today. The current code's own comment
(`financials_derived.py:279`) already documents this as a deliberate simplification, not
an oversight. Re-deriving textbook ROIC would require adding a new parsed field — that's
a silver-layer change exceeding Phase 2's "pure SQL" scope (see Deferred Ideas below).

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

### Deferred Ideas (OUT OF SCOPE)

- **Valuation/market-derived factors** (P/E, EV/EBITDA, price-based ratios) — explicitly
  out of scope per `REQUIREMENTS.md`'s existing "Out of Scope" section. These require a
  platform charter decision on owning vs. sourcing market data, tracked separately under
  the held `model-builder-contract-gaps` Phase 5. Not re-litigated here.
- **Textbook NOPAT-based ROIC re-derivation** — needs a new `income_tax_expense`/
  effective-tax-rate field parsed in `financials_derived.py` (a silver-layer change, not
  pure SQL). Candidate for a future phase in this workstream or a follow-up requirement;
  not Phase 2 scope per D-03.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROF-01 | Consumer can query gross margin (`gross_profit / revenue`), operating margin (`ebit / revenue`), and net margin (`net_income / revenue`) — all three inputs already present in `financial_derived`, no silver change required. | `financial_derived.sql` lines 84-88 already select `gross_profit`, `ebit`, `revenue`, `net_income` into `financial_factors` via `base`/`line_items`; all three new ratios use plain `safe_ratio()` per Architecture Patterns below. |
| PROF-02 | Consumer can query return on equity (`net_income / total_equity`) and return on assets (`net_income / total_assets`) — both inputs already present in `financial_derived`, no silver change required. | `total_equity`/`total_assets`/`net_income` already selected in `financial_factors.sql` lines 53/51/58. `return_on_equity` needs the new sign-checked macro (D-01); `return_on_assets` uses plain `safe_ratio()` (Claude's Discretion — no guard needed). |
| PROF-03 | ROIC is already exposed in `financial_derived` (`w.roic`); this requirement is to surface it in `FINANCIAL_FACTORS` alongside the other profitability factors for a single consumer-facing model, not to recompute it. | `financial_derived.sql` line 114 selects `w.roic` from the silver `_safe_div(ebit, invested_capital)` computation (`financials_derived.py` lines 279-283). `financial_factors.sql`'s `base` CTE does `select d.*` from `financial_derived` (line 10), so `roic` is already implicitly available on every row in `base`/`line_items` — it only needs to be added to the final `select` list, no upstream model change. |

## Standard Stack

This phase introduces no new libraries, packages, or dependencies. It is a pure dbt SQL
model extension plus one new dbt macro, using the project's existing dbt + Snowflake
toolchain.

| Tool | Version | Purpose | Provenance |
|------|---------|---------|------------|
| dbt-snowflake | per `uv.lock` (invoked via `uv run --with dbt-snowflake`, no pin observed in CLAUDE.md) | dbt adapter for Snowflake dynamic tables | `[VERIFIED: repo CLAUDE.md command reference]` |
| Snowflake dynamic tables | N/A (Snowflake platform feature) | Materialization strategy for all gold models (`gold_model_config` macro) | `[VERIFIED: infra/snowflake/dbt/edgartools_gold/macros/gold_model_config.sql]` |

**Installation:** None required — no new packages for this phase.

## Package Legitimacy Audit

Not applicable. This phase makes zero changes to `pyproject.toml`, `uv.lock`, or any
Python/Node dependency manifest — it is dbt SQL plus a Jinja macro only. The Package
Legitimacy Gate is skipped per its own scope (only applies "whenever this phase installs
external packages").

## Architecture Patterns

### System Architecture Diagram

```
financial_derived (existing gold model)
   │  select d.*  (includes: revenue, gross_profit, ebit, net_income,
   │               total_equity, total_assets, roic, ... + already-computed
   │               but UNUSED-downstream gross_margin/net_margin/roe/roa)
   ▼
financial_factors.sql :: base CTE
   │
   ▼
financial_factors.sql :: line_items CTE
   │  (adds working_capital = current_assets - current_liabilities)
   ▼
financial_factors.sql :: final select
   │
   ├─ existing V1 factors (safe_ratio() × 9, FY-only growth × 2)
   │
   └─ NEW Phase 2 factors  ◄── this phase's only change
        ├─ gross_margin       = safe_ratio(gross_profit, revenue)
        ├─ operating_margin   = safe_ratio(ebit, revenue)
        ├─ net_margin         = safe_ratio(net_income, revenue)
        ├─ return_on_equity   = safe_ratio_signed(net_income, total_equity)  [NEW macro]
        ├─ return_on_assets   = safe_ratio(net_income, total_assets)
        └─ roic               = l.roic   (pass-through, no computation)
   │
   ▼
EDGARTOOLS_GOLD.FINANCIAL_FACTORS  (Snowflake dynamic table)
   │
   ▼
Consumers (Streamlit dashboard, ad-hoc SQL clients) — out of scope this phase
```

### Recommended Project Structure

No new files for models. One new macro file:

```
infra/snowflake/dbt/edgartools_gold/
├── macros/
│   ├── safe_ratio.sql                    # existing — reused as-is for 4 of 6 factors
│   ├── yoy_growth.sql                    # existing — untouched, not used by this phase
│   └── safe_ratio_signed.sql             # NEW — sign-checked variant for return_on_equity
├── models/gold/
│   ├── financial_factors.sql             # MODIFIED — add 6 columns to final select
│   ├── _financial_factors_unit_tests.yml # MODIFIED — add new test cases
│   └── gold.yml                          # MODIFIED — model-level description update only
```

### Pattern 1: `safe_ratio()` macro reuse (gross/operating/net margin, ROA)

**What:** The existing `safe_ratio(numerator_col, denominator_col)` macro already
null-guards on missing numerator/denominator and zero denominator. Reuse directly,
unmodified, for `gross_margin`, `operating_margin`, `net_margin`, `return_on_assets`.

**When to use:** Any ratio where the denominator going negative is not a realistic or
specially-meaningful accounting scenario (revenue, total_assets — per Claude's
Discretion in CONTEXT.md).

**Example (follows the exact syntax already in `financial_factors.sql` lines 71-81):**

```sql
-- Source: infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql (existing pattern)
{{ safe_ratio('l.gross_profit', 'l.revenue') }} as gross_margin,
{{ safe_ratio('l.ebit', 'l.revenue') }} as operating_margin,
{{ safe_ratio('l.net_income', 'l.revenue') }} as net_margin,
{{ safe_ratio('l.net_income', 'l.total_assets') }} as return_on_assets,
```

Note: `l.ebit` and `l.gross_profit` are NOT currently in `financial_factors.sql`'s
`select` list (only `financial_derived.sql` selects them, and `base` does `select d.*`
so they ARE available on `l.` inside `line_items` — they're just not in the FINAL
`select` list of `financial_factors.sql` yet, lines 40-95). Confirm whether the planner
wants `gross_profit`/`ebit` added to the "Base accounting inputs retained for coverage"
block (lines 49-67) alongside `revenue`/`net_income`/etc. for consistency — every other
ratio's both inputs are already exposed as raw columns in that block (e.g.
`current_assets`/`current_liabilities` for `current_ratio`). Recommend adding
`l.gross_profit` and `l.ebit` to that block for consistency, since `revenue`,
`total_equity`, and `total_assets` are already there.

### Pattern 2: New sign-checked macro for `return_on_equity` (D-01)

**What:** A new macro variant that nulls the ratio when the denominator is negative
(not just zero/null), implementing the Damodaran ROE treatment.

**When to use:** Only `return_on_equity` in this phase. Designed to be specific/reusable
enough that the macro itself documents the rule, not buried in a `case` expression
inline in `financial_factors.sql` (keeps the model's `select` list visually consistent
with the rest of the file, which always calls a macro, never inlines `case`/division
directly — except `asset_growth_yoy`/`shares_outstanding_yoy_change`, which use `case`
specifically for the FY-only period gate, a different concern than the ratio-safety
gate that `safe_ratio()` exists for).

**Naming:** No existing convention to extend (`safe_ratio` is the only existing ratio
macro), so name it descriptively. Recommend `safe_ratio_signed` (parallels `safe_ratio`,
signals "with an added sign check") or `safe_ratio_positive_denominator` (more explicit
but verbose). Either is fine — planner's call, but should match whichever verb pattern
exists at execution time.

**Example (matches `safe_ratio.sql`'s exact macro syntax/whitespace style):**

```sql
{% macro safe_ratio_signed(numerator_col, denominator_col) %}
    case
        when {{ numerator_col }} is not null
         and {{ denominator_col }} is not null
         and {{ denominator_col }} > 0
        then {{ numerator_col }} / {{ denominator_col }}
    end
{% endmacro %}
```

Note the single change from `safe_ratio()`: `<> 0` becomes `> 0`. This single comparison
operator change is the entire diff in business logic — `> 0` naturally excludes both
`= 0` (already excluded by `safe_ratio`'s guard) and `< 0` (the new D-01 guard), so one
condition replaces `safe_ratio`'s `<> 0` rather than adding a second `and` clause. This
is the minimal, idiomatic implementation — do not write `denominator > 0 and denominator
<> 0` (redundant) or a separate `case when denominator < 0 then null` branch (equivalent
but unnecessarily verbose).

**Usage in `financial_factors.sql`:**

```sql
{{ safe_ratio_signed('l.net_income', 'l.total_equity') }} as return_on_equity,
```

### Pattern 3: ROIC pass-through (D-03)

**What:** No macro, no computation — straight column reference, since `financial_derived`
already computed it.

```sql
l.roic as roic,
```

Because `base` does `select d.*` from `financial_derived` (line 10 of
`financial_factors.sql`), `roic` already flows through `base` → `line_items` → is
available as `l.roic` without any upstream model change. Confirm this also applies
to whichever of `gross_profit`/`ebit` get added per Pattern 1's note — same mechanism
(`select d.*` already exposes every `financial_derived` column to `l.`).

### Anti-Patterns to Avoid

- **Reusing `financial_derived.gross_margin`/`net_margin`/`roe`/`roa` directly instead of
  recomputing in `financial_factors.sql`:** These columns exist in `financial_derived`
  (selected at lines 110-116) but are computed by the Python silver parser's
  `_safe_div()` (zero/null guard only, NO sign check) — reusing `financial_derived.roe`
  would silently skip the D-01 negative-equity guard entirely, since that guard does not
  exist anywhere in the silver layer. Recompute fresh in `financial_factors.sql` using
  `safe_ratio()`/`safe_ratio_signed()` for every factor except `roic` (which has no
  sign-sensitivity concern, per D-03's deliberate "surface as-is" decision).
- **Inlining `case when total_equity > 0 then net_income / total_equity end` directly in
  the `select` list:** Breaks the file's 100% macro-based ratio convention (every other
  ratio factor — 9 of 9 in the current file — calls `safe_ratio()`). A reviewer scanning
  `financial_factors.sql` should see consistent `{{ macro(...) }}` calls for every ratio;
  an inline `case` for just one factor reads as inconsistent/accidental rather than a
  deliberate, reusable rule.
- **Restricting new factors to `fiscal_period = 'FY'` by copying the `asset_growth_yoy`
  pattern:** Explicitly rejected by D-02. The FY restriction in the existing code exists
  ONLY because YoY growth requires a same-fiscal-period prior-year comparison row (the
  `left join prior_fy_values py` in the current model) — margins/returns are single-period
  calculations with no such join dependency, so the `case when l.fiscal_period = 'FY'`
  gate must NOT be copied onto the new columns.
- **Adding a sign guard to `return_on_assets`:** Explicitly rejected under "Claude's
  Discretion" in CONTEXT.md — negative total_assets is not a realistic balance-sheet
  state, so the plain `safe_ratio()` zero/null guard suffices; do not over-engineer by
  copying the ROE guard onto ROA "for consistency."

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Null/zero-safe division | Inline `case when x <> 0 then a/b end` per factor | `safe_ratio()` macro (existing) | Already exists, already tested, already the file's 100% convention — zero reason to duplicate the guard logic inline. |
| Sign-checked division for ROE | Inline `case` in the model `select` | New `safe_ratio_signed()` (or similarly named) macro, sibling to `safe_ratio()` | Keeps the rule centrally documented and reusable if a future factor needs the same guard (e.g. if ROIC's `invested_capital` denominator is ever recomputed downstream with similar negative-equity risk). |

**Key insight:** This codebase already has the exact macro abstraction needed
(`safe_ratio()`); the only net-new code is one macro file with a one-character logic
change (`<>` → `>`) plus six `select`-list lines. Resist the urge to write anything more
elaborate (e.g. a parameterized macro with a `sign_check` boolean flag) — YAGNI applies;
a five-line sibling macro is simpler to read and test than a flag-driven variant of
`safe_ratio()`.

## Common Pitfalls

### Pitfall 1: Forgetting `gross_profit`/`ebit` are not yet in the "Base accounting
inputs" select block

**What goes wrong:** A planner/implementer might assume `l.gross_profit` and `l.ebit`
need a new CTE or upstream model change to become available, when they're already
implicitly present via `base`'s `select d.*`.

**Why it happens:** `financial_factors.sql`'s current "Base accounting inputs retained
for coverage and factor debugging" comment block (lines 49-67) lists the columns that
got promoted to the final select for debugging visibility — it is NOT an exhaustive list
of every column available on `l.`. `gross_profit` and `ebit` are available on `l.` right
now (via `select d.*` in `base`) even though they aren't in that comment block.

**How to avoid:** Reference `l.gross_profit`/`l.ebit` directly in the new ratio
expressions; no upstream model change needed. Optionally also add them to the "Base
accounting inputs" block for debugging-visibility consistency with the rest of the file
(every other ratio's raw inputs are exposed there) — this is a style/consistency call,
not a functional requirement.

**Warning signs:** A plan that includes a task like "modify `financial_derived.sql` to
expose `gross_profit`" — this is unnecessary; it's already exposed.

### Pitfall 2: Snowflake division semantics differ subtly from generic SQL

**What goes wrong:** Assuming `0/0` or `x/0` errors at the database level the way some
engines do, leading to defensive code that's redundant with `safe_ratio()`.

**Why it happens:** Standard SQL division by zero raises a runtime error in many engines
(Postgres, MySQL strict mode). Snowflake's behavior: `x / 0` raises
`100051 (22012): Division by zero` for non-floating-point exact division, **unless**
guarded — which is exactly why `safe_ratio()`'s `<> 0` check exists. The macro is not
optional style — without it, a zero denominator in production data would error the
entire dynamic table refresh, not just null one row.

**How to avoid:** Always go through `safe_ratio()`/`safe_ratio_signed()`; never write a
raw `/` in the gold SQL layer. This is already the file's 100% convention — just don't
break it for the new columns.

**Warning signs:** A `dbt run --select financial_factors --full-refresh` failure with a
Snowflake division-by-zero error message — would indicate someone bypassed the macro
somewhere in the new columns.

### Pitfall 3: dbt unit tests check the FULL result row, not a subset

**What goes wrong:** A new unit test `expect.rows` entry that only lists the new
factor columns (e.g. just `return_on_equity: null`) will still implicitly check every
OTHER column in that row against whatever the existing fixture produces — if the
fixture's other expected values are stale or the row doesn't match an existing
`expect` block, the test can fail for unrelated reasons.

**Why it happens:** Per `_financial_derived_unit_tests.yml`'s own header comment:
"`expect.rows` must enumerate ONE row per `given` row (dbt unit tests compare the full
result set, not a subset) -- columns omitted from an `expect` row are still checked, but
only the growth/grain-relevant columns are listed explicitly here." This is dbt's actual
unit-test semantics (column omission in `expect` rows means "don't assert," not "ignore
column"), already documented in-repo from the team's own prior experience.

**How to avoid:** Follow the existing pattern exactly: list every column that matters
for the specific test's assertion (the new factor + any factor whose behavior the test
is specifically verifying), and trust dbt to not fail on genuinely-omitted columns —
but double check by running the actual test, since dbt's per-version omission semantics
can be subtle. Mirror the granularity already used in `_financial_factors_unit_tests.yml`
(e.g. its existing `expect` blocks list ~15 specific columns per row, not the full ~25
column output).

**Warning signs:** A new unit test failing with a diff on a column you didn't intend to
test (e.g. `current_ratio` showing up in a diff for a test that's supposed to be about
`return_on_equity`).

### Pitfall 4: `gold.yml` has no per-ratio-column description pattern to extend

**What goes wrong:** D-03 says "documents the simplification in the dbt column
description (`gold.yml`)" — but `gold.yml` as it exists today has NO per-column
`description:` field for any ratio column in `financial_factors` or `financial_derived`
(only PK/grain columns like `cik`, `accession_number`, `fiscal_period` get a `columns:`
block, and only with `not_null` tests, no `description:` at all). The model-level
`description:` field IS used (e.g. `financial_factors`'s one-line description at line
112), but no individual column ever gets prose documentation in this file currently.

**Why it happens:** The team has not yet established a per-column doc convention for
ratio/derived columns — only grain/PK columns get individual `columns:` entries.

**How to avoid:** The planner has two reasonable options, since CONTEXT.md's intent
(documenting the ROIC simplification) is clear even though the exact YAML shape isn't
established: (1) extend `financial_factors`'s model-level `description:` field in
`gold.yml` with a sentence noting ROIC is a simplified pre-tax measure, matching the
file's current all-model-level-description pattern, or (2) add a new `columns:` entry
for `roic` specifically with a `description:` field, which would be the first
per-ratio-column doc in this file (an acceptable, low-risk precedent given this is
exactly the kind of caveat that benefits from being column-scoped rather than buried in
a model-level sentence). Either satisfies D-03's actual intent; recommend option 2
(column-level) since the caveat is specific to one column, not the whole model — but
this is implementation discretion the plan should decide explicitly rather than leaving
ambiguous.

**Warning signs:** A plan/task that says "add description to gold.yml" without
specifying model-level vs. column-level — ambiguous enough to cause back-and-forth
during execution; the plan should pick one.

## Code Examples

### Full proposed diff shape for `financial_factors.sql` (illustrative, not exact line numbers)

```sql
-- Source: existing financial_factors.sql pattern, extended per Phase 2 (PROF-01/02/03)
    -- ... existing V1 accounting-only factors (lines 70-92, unchanged) ...
    case
        when l.fiscal_period = 'FY'
         and l.shares_outstanding is not null
         and py.shares_outstanding is not null
        then l.shares_outstanding - py.shares_outstanding
    end as shares_outstanding_yoy_change,

    -- V2 profitability and returns factors (Phase 2).
    {{ safe_ratio('l.gross_profit', 'l.revenue') }} as gross_margin,
    {{ safe_ratio('l.ebit', 'l.revenue') }} as operating_margin,
    {{ safe_ratio('l.net_income', 'l.revenue') }} as net_margin,
    {{ safe_ratio_signed('l.net_income', 'l.total_equity') }} as return_on_equity,
    {{ safe_ratio('l.net_income', 'l.total_assets') }} as return_on_assets,
    l.roic,

    l.parser_version,
    l.ingested_at
from line_items l
left join prior_fy_values py
    on py.cik = l.cik
    and py.fiscal_year = l.fiscal_year - 1
```

### New macro file

```sql
-- Source: infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql (NEW)
{% macro safe_ratio_signed(numerator_col, denominator_col) %}
    case
        when {{ numerator_col }} is not null
         and {{ denominator_col }} is not null
         and {{ denominator_col }} > 0
        then {{ numerator_col }} / {{ denominator_col }}
    end
{% endmacro %}
```

### New unit test case (negative equity, verifies D-01's null guard)

```yaml
# Source: pattern matches existing _financial_factors_unit_tests.yml anchor-merge style
  - name: financial_factors_negative_equity_nulls_roe
    description: >
      Negative total_equity nulls return_on_equity (D-01, Damodaran treatment) while
      return_on_assets and margins compute normally from the same negative net_income.
    model: financial_factors
    given:
      - input: ref('financial_derived')
        rows:
          - <<: *factor_row_defaults
            cik: 99
            accession_number: "0099"
            fiscal_year: 2024
            net_income: -30
            total_equity: -20
            total_assets: 300
            revenue: 150
            gross_profit: 60
            ebit: -10
    expect:
      rows:
        - cik: 99
          accession_number: "0099"
          fiscal_year: 2024
          return_on_equity: null
          return_on_assets: -0.1
          net_margin: -0.2
          gross_margin: 0.4
          operating_margin: -0.0667
```

Note: `gross_profit`/`ebit` must be added to the `factor_row_defaults` anchor (or
specified per-row) in the test fixture, since the current anchor doesn't include them —
the existing fixture rows never needed them because `financial_factors.sql` didn't
select them before this phase. Also confirm the exact expected `operating_margin` value
against dbt's actual floating-point output (Snowflake division of `-10/150` =
`-0.0666...`) — exact decimal precision/rounding should be verified against a real
`dbt build` run, not assumed from manual arithmetic, since dbt unit test row comparison
is typically exact-match on the returned numeric type.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A — first-time addition of profitability/returns factors to `financial_factors` | `safe_ratio()`/`safe_ratio_signed()` macro-based computation | This phase (Phase 2) | No prior state to compare; this IS the "current approach" being established. |

**Deprecated/outdated:** Nothing in this phase deprecates existing behavior —
`financial_derived.roe`/`roa`/`gross_margin`/`net_margin` remain in `financial_derived`
unchanged (their consumers, if any exist outside this workstream, are unaffected); this
phase only adds new, separately-named, more-conservative columns to a different model
(`financial_factors`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Recommended macro name `safe_ratio_signed` (vs. some other name) | Architecture Patterns, Pattern 2 | Low — purely cosmetic; planner/implementer can rename freely without behavior change. Flagging only because no existing precedent constrains the choice. |
| A2 | `gold.yml` documentation for D-03 should land as a column-level `description:` under `financial_factors`'s `roic` column (Option 2 in Pitfall 4) rather than a model-level sentence | Common Pitfalls, Pitfall 4 | Low-medium — if the planner instead chooses model-level, D-03's intent is still satisfied; only risk is plan/implementation disagreement on which YAML shape to use if not made explicit in the plan. |
| A3 | Exact floating-point output of `-10/150` in the example unit test (`-0.0667`) is illustrative rounding, not dbt's actual returned precision | Code Examples | Low — flagged explicitly in the example's accompanying note; implementer must verify against a real `dbt build`/`dbt test` run before committing the fixture's expected value. |

## Open Questions

1. **Should `gross_profit` and `ebit` be added to the "Base accounting inputs retained
   for coverage" comment block (lines 49-67) for visibility, or only referenced inline
   in the new ratio expressions?**
   - What we know: Both columns are already available on `l.` via `base`'s `select d.*`
     — no functional blocker either way.
   - What's unclear: Whether the team wants every ratio's raw inputs visible in the
     "debugging" block (current convention for the 9 existing ratios) or considers that
     block already complete/closed.
   - Recommendation: Add both for consistency with the established pattern (every other
     ratio's inputs are in that block) — low cost, matches precedent, aids future
     debugging of the new factors the same way it aids the existing ones.

2. **Exact macro name for the sign-checked ROE guard.**
   - What we know: Functionally must check `denominator > 0` (not `<> 0`).
   - What's unclear: No project precedent for naming a `safe_ratio()` variant.
   - Recommendation: `safe_ratio_signed` (parallels `safe_ratio`, short, signals "extra
     check on sign") — but this is a free naming choice for the planner/implementer.

## Environment Availability

Skipped — this phase has no external dependencies beyond the project's already-configured
dbt + Snowflake toolchain (no new tools, services, or runtimes). `dbt-snowflake` and
Snowflake connectivity are prerequisites already established by prior phases (V1
`financial_factors` shipped 2026-06-26 per PR #102) and are out of scope to re-verify
here.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | dbt unit tests (`unit_tests:` YAML spec, dbt-core native feature) |
| Config file | `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml` |
| Quick run command | `cd infra/snowflake/dbt/edgartools_gold && uv run --with dbt-snowflake dbt test --select financial_factors` |
| Full suite command | `cd infra/snowflake/dbt/edgartools_gold && uv run --with dbt-snowflake dbt test --target prod` (per CLAUDE.md / AGENTS.md / docs/runbook.md convention) |

Note: dbt unit tests (the `unit_tests:` block, which mocks `ref()`/`source()` inputs and
asserts row-level output) run via `dbt test` (or `dbt build`) and do NOT require a live
Snowflake connection for the unit-test portion specifically when using dbt's
`--empty`/unit-test execution path — but this repo's actual CI/local convention (per
CLAUDE.md) is `dbt test --target prod` against a real warehouse. Confirm at execution
time whether local `dbt compile`-only validation is sufficient for plan verification or
whether a live `dbt test` run (requiring `DBT_SNOWFLAKE_*` env vars) is required per this
phase's verification gate — `dbt compile` alone does NOT execute unit tests, only
validates SQL/Jinja syntax.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROF-01 | gross_margin/operating_margin/net_margin compute correctly for a representative FY row | unit | `dbt test --select financial_factors` (existing `financial_factors_complete_fy_ratios` test, extended) | Wave 0 — extend existing file |
| PROF-01 | margins compute for non-FY (quarterly) rows too, per D-02 | unit | `dbt test --select financial_factors` (existing `financial_factors_quarterly_cross_year_factors_are_null` test, extended) | Wave 0 — extend existing file |
| PROF-02 | return_on_equity nulls when total_equity < 0 (D-01) | unit | `dbt test --select financial_factors` (new test case) | Wave 0 — add new test |
| PROF-02 | return_on_assets computes normally (including negative net_income / negative margin) per roadmap success criterion #4 | unit | `dbt test --select financial_factors` (new test case, same fixture as above) | Wave 0 — add new test |
| PROF-03 | roic passes through unchanged from financial_derived | unit | `dbt test --select financial_factors` (new test case, or extend existing FY test with a roic assertion) | Wave 0 — add new test |

### Sampling Rate

- **Per task commit:** `dbt test --select financial_factors` (fast, scoped to this model
  and its unit tests only — no live warehouse query needed if using mocked `ref()`
  inputs per dbt unit test semantics)
- **Per wave merge:** `dbt test --target prod` (full suite, per repo convention,
  confirms no regression in sibling models)
- **Phase gate:** Full suite green before `/gsd-verify-work`, matching the roadmap's
  Phase 2 success criterion #4 (negative net income coverage) and #5 (no
  silver/loader changes — verify via `git diff --stat` showing only
  `infra/snowflake/dbt/edgartools_gold/**` paths touched)

### Wave 0 Gaps

- [ ] `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql` — new macro,
      does not exist yet
- [ ] New unit test case(s) in `_financial_factors_unit_tests.yml` covering: (a)
      negative total_equity nulling ROE, (b) negative net_income flowing through
      margins/ROA without special-casing, (c) ROIC pass-through assertion
- None other — `dbt test` infrastructure, fixture-anchor conventions, and the model
      file itself all already exist; this phase only adds to them.

## Security Domain

Not applicable — this phase has no input validation, authentication, session, or
cryptography surface. It is read-only financial-ratio computation over already-validated
SEC XBRL data inside a Snowflake dynamic table. No ASVS category applies. (If
`security_enforcement` is enabled project-wide, this section's "no applicable categories"
determination is the explicit answer, not an omission.)

## Sources

### Primary (HIGH confidence)
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` (repo, read
  directly) — existing model structure, CTE chain, `safe_ratio()` usage convention.
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_derived.sql` (repo, read
  directly) — confirms `gross_profit`, `ebit`, `roic`, `gross_margin`, `net_margin`,
  `roe`, `roa` already computed/selected upstream.
- `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio.sql` and `yoy_growth.sql`
  (repo, read directly) — exact macro syntax/style to mirror for the new
  `safe_ratio_signed` macro.
- `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml`
  and `_financial_derived_unit_tests.yml` (repo, read directly) — exact test fixture
  conventions (`<<: *anchor` merge pattern, full-row `expect` semantics documented in
  the latter file's own header comment).
- `edgar_warehouse/parsers/financials_derived.py` lines 169-283 (repo, read directly)
  — confirms `_safe_div()`'s plain null/zero-only guard (no sign check) for the
  upstream silver-computed ratios, and the existing ROIC simplification comment at
  line 279 (referenced, not modified, per D-03/canonical_refs).
- `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` (repo, read directly) —
  confirms no existing per-ratio-column `description:` pattern (informs Pitfall 4).
- `CLAUDE.md`, `AGENTS.md`, `docs/runbook.md` (repo, grep + read) — confirms
  `dbt test --target prod` as the standard validation command convention.

### Secondary (MEDIUM confidence)
None used — all findings in this research were verified directly against the repo's
own source files (highest-confidence source available for an in-repo implementation
question); no external web search was needed since CONTEXT.md had already done the
external research (Damodaran ROE treatment) and this research's job was implementation
detail, which lives entirely in the codebase.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; existing dbt+Snowflake toolchain
  confirmed via direct file reads.
- Architecture: HIGH — every pattern (macro reuse, CTE chain, select-list placement)
  verified by reading the actual current `financial_factors.sql`/`financial_derived.sql`
  source, not inferred.
- Pitfalls: HIGH — each pitfall is grounded in a specific, cited line/file (e.g.
  Snowflake division-by-zero motivating `safe_ratio()`'s existence; dbt unit test
  full-row-comparison semantics quoted from the repo's own prior documentation in
  `_financial_derived_unit_tests.yml`).

**Research date:** 2026-06-30
**Valid until:** Stable — this is a single-repo, single-model implementation question
with no external API/library version drift risk. Valid until `financial_factors.sql`,
`financial_derived.sql`, or `safe_ratio.sql` are next modified by another phase/PR
(check `git log` on those three files before reusing this research unmodified).
