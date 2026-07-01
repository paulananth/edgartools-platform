# Phase 1: CAGR Macro And Multi-Year Joins - Pattern Map

**Mapped:** 2026-06-30
**Files analyzed:** 4 (1 new macro, 3 modified)
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|---------------|
| `infra/snowflake/dbt/edgartools_gold/macros/cagr.sql` | utility (dbt macro) | transform | `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql` | exact (same sign-guard shape, extended to two operands + exponent) |
| `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` | model (dbt SQL, CRUD-style transform) | transform / CRUD (dynamic table refresh) | itself, prior-existing `prior_fy_values` CTE + `asset_growth_yoy` factor (lines 17-31, 85-88, 106-109) | exact (this phase extends the file's own established 1-year-offset pattern to 3yr/5yr) |
| `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml` | test | transform | itself, `financial_factors_negative_equity_nulls_roe` test case (lines 131-159) | exact (anchor-merge fixture pattern, multi-row given/expect) |
| `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` | config (dbt schema/docs) | transform | itself, `roic` column description (lines 123-128) | exact (column-level `description:` block precedent) |

No new model files are created — this phase only adds one macro and extends three existing files in place, per CONTEXT.md's domain boundary.

## Pattern Assignments

### `infra/snowflake/dbt/edgartools_gold/macros/cagr.sql` (utility, transform) — NEW FILE

**Analog:** `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql` (sign-guard shape) and `infra/snowflake/dbt/edgartools_gold/macros/yoy_growth.sql` (growth-macro structural template)

**Full analog — `safe_ratio_signed.sql`** (entire file, 8 lines):
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

**Full analog — `yoy_growth.sql`** (entire file, 6 lines):
```sql
{% macro yoy_growth(current_col, prior_col) %}
    case
        when {{ prior_col }} is not null and {{ prior_col }} <> 0
        then ({{ current_col }} - {{ prior_col }}) / {{ prior_col }}
    end
{% endmacro %}
```

**Core pattern to write (per RESEARCH.md Pattern 2, already verified against the macro conventions above):**
```sql
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

**Key conventions to copy exactly:**
- 4-space indent inside `case`, `when` continuation lines aligned with extra space (`         and`) matching `safe_ratio_signed.sql` lines 3-5 byte-for-byte.
- No raw `/` division anywhere outside the guarded `then` branch — division only happens after the `case when` guard passes (same as both analogs).
- Macro name and params are plain snake_case Jinja args (`current_col`, `prior_col`), no type hints — matches both analogs' signatures.
- **Critical, not present in either analog:** use `1.0 / {{ years }}`, never `1 / {{ years }}` — Snowflake integer division silently zeroes every CAGR value (RESEARCH.md Pitfall 1). This is the one place this macro diverges from a literal copy-paste of an existing macro.

---

### `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` (model, transform) — MODIFIED

**Analog:** itself — the existing `prior_fy_values` CTE (lines 17-31) and `asset_growth_yoy` factor (lines 85-88), plus the final `left join` (lines 106-109).

**CTE pattern to copy** (lines 17-31, copy structure byte-for-byte per RESEARCH.md Pitfall 4 — do not "clean up" the `partition by`/`qualify` shape while porting):
```sql
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
```
New CTEs `prior_fy_values_3y` / `prior_fy_values_5y`: same `where fiscal_period = 'FY'`, same `qualify row_number() over (partition by cik, fiscal_year order by is_current_period desc, accession_number desc) = 1`, only the CTE name and selected columns change (`revenue`, `net_income`, `total_assets` instead of `total_assets`, `shares_outstanding`).

**FY-gating `case` wrapper pattern to copy** (lines 85-88):
```sql
case
    when l.fiscal_period = 'FY'
    then {{ yoy_growth('l.total_assets', 'py.total_assets') }}
end as asset_growth_yoy,
```
New CAGR columns use the identical wrapper shape with `{{ cagr(...) }}` substituted for `{{ yoy_growth(...) }}` and a third `years` argument.

**Join pattern to copy** (lines 106-109):
```sql
from line_items l
left join prior_fy_values py
    on py.cik = l.cik
    and py.fiscal_year = l.fiscal_year - 1
```
New joins: `left join prior_fy_values_3y py3 on py3.cik = l.cik and py3.fiscal_year = l.fiscal_year - 3` and the `py5`/`- 5` equivalent — exact equi-join, no `between`/tolerance (enforces D-03).

**Macro usage pattern** (existing call style, line 87 and lines 73-84): macro calls are inlined directly in the `select` list with `{{ macro(...) }} as column_name,` — no intermediate CTE for the factor itself. Follow this for the 6 new CAGR columns.

**Where to insert:** new CTEs go after the existing `prior_fy_values` CTE (before `line_items`, i.e. after line 31); new select columns go after the existing V2 block (`l.roic,` at line 102), before `l.parser_version,` (line 104); new joins go after the existing `left join prior_fy_values py` block (after line 109).

---

### `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml` (test, transform) — MODIFIED

**Analog:** itself — `financial_factors_negative_equity_nulls_roe` (lines 131-159) for the anchor-merge single-divergent-row style, and `financial_factors_complete_fy_ratios` (lines 4-93) for the multi-row-same-cik shape needed for self-join testing.

**Anchor-merge fixture pattern to copy** (lines 4-37, the `&factor_row_defaults` anchor + `<<: *factor_row_defaults` override):
```yaml
given:
  - input: ref('financial_derived')
    rows:
      - &factor_row_defaults
        cik: 1
        accession_number: "0001"
        fiscal_year: 2023
        fiscal_period: "FY"
        period_end: "2023-12-31"
        form_type: "10-K"
        revenue: 125
        total_assets: 250
        # ... full baseline row ...
      - <<: *factor_row_defaults
        accession_number: "0002"
        fiscal_year: 2024
        revenue: 150
        total_assets: 300
```
New CAGR tests reuse `*factor_row_defaults` and override only `cik`, `accession_number`, `fiscal_year`, `period_end`, and the specific revenue/net_income/total_assets values needed per RESEARCH.md Pattern 3's 6 required fixture cases (happy path at cik 10, single-endpoint-negative at cik 11/12, negative-to-negative at cik 13, fiscal-year-gap at cik 14, quarterly-exclusion extending the existing `financial_factors_quarterly_cross_year_factors_are_null` test at lines 95-129).

**Expect-block granularity convention** (lines 64-93): only list columns relevant to what the test verifies — omitted columns are NOT asserted (not implicitly null-checked). Follow this for new CAGR test cases — assert only the 6 new `*_cagr_3y`/`*_cagr_5y` columns (plus `cik`/`accession_number`/`fiscal_year` as row keys), not the full factor set.

**Test naming convention:** `financial_factors_<scenario>` (snake_case, descriptive) — e.g. `financial_factors_cagr_happy_path`, `financial_factors_cagr_negative_to_negative_nulls`, `financial_factors_cagr_fiscal_year_gap`.

**Description field convention** (lines 132-134, YAML block scalar `>` for multi-line):
```yaml
description: >
  Negative total_equity nulls return_on_equity (D-01, Damodaran treatment) while
  return_on_assets and margins compute normally from the same negative net_income.
```
New tests should cite the relevant decision ID (D-02, D-03) and requirement ID (GROW-01/02/03) the same way this existing description cites D-01.

---

### `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` (config, transform) — MODIFIED

**Analog:** itself — `roic` column description (lines 123-128) and the `financial_factors` model-level description (lines 111-112).

**Column-level description pattern to copy** (lines 123-128):
```yaml
      - name: roic
        description: >
          Simplified pre-tax ROIC (EBIT / Average Invested Capital). Does not apply
          a NOPAT tax adjustment — financials_derived.py has no parsed
          income_tax_expense/effective-tax-rate field today (see
          edgar_warehouse/parsers/financials_derived.py line 279).
```
Add 6 new `- name:` blocks (one per `*_cagr_3y`/`*_cagr_5y` column) under `financial_factors.columns` (after the existing `roic` entry at line 128), each documenting: FY-only scope (D-01), strict-positivity null guard (D-02), and exact-N-year-match requirement — gap years null rather than fuzzy-match (D-03). This mirrors how `roic`'s description documents its own computational caveat inline.

**Insertion point:** insert new column blocks immediately after line 128 (after the existing `roic` description), still nested under the `financial_factors:` model block (lines 111-128).

---

## Shared Patterns

### Macro null/sign guard convention
**Source:** `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio.sql`, `safe_ratio_signed.sql`, `yoy_growth.sql`
**Apply to:** `cagr.sql` (new)
Every guarded computation in this codebase is a `case when <null/sign checks> then <division/formula> end` macro — never raw arithmetic inlined in the model, never relying on the caller to pre-validate. `cagr()` must follow this exactly, with TWO operand checks (`current_col > 0 and prior_col > 0`), not a same-sign check (RESEARCH.md Pitfall 2).

### FY-only gating wrapper
**Source:** `financial_factors.sql` lines 85-88 (`asset_growth_yoy`)
**Apply to:** all 6 new CAGR select columns
```sql
case
    when l.fiscal_period = 'FY'
    then {{ macro_call(...) }}
end as column_name,
```
This wrapper is distinct from and in addition to the macro's own internal null/sign guard — both layers are required, matching the existing `asset_growth_yoy` precedent.

### Exact equi-join for N-year offset (no tolerance)
**Source:** `financial_factors.sql` lines 107-109 (`py.fiscal_year = l.fiscal_year - 1`)
**Apply to:** new `prior_fy_values_3y`/`prior_fy_values_5y` joins
`= l.fiscal_year - N` only — never `between` or a fuzzy-match range. A missing exact match nulls via `left join`, which is the desired D-03 behavior, not a bug to fix.

### dbt unit-test anchor-merge fixtures
**Source:** `_financial_factors_unit_tests.yml` lines 10-36 (`&factor_row_defaults`) and lines 37-58 (`<<: *factor_row_defaults` override row)
**Apply to:** all new CAGR test cases
Reuse the existing top-level `&factor_row_defaults` anchor (defined once in the first test case, line 10) across new test cases — do not redefine a new anchor. Override only the fields relevant to each scenario.

## No Analog Found

None — every file in this phase's scope (1 new macro, 3 modified files) has a strong, directly-applicable analog already in the same files being modified or in sibling macro files. This is the rare case where the "closest analog" for most files is the file's own pre-existing pattern, extended.

## Metadata

**Analog search scope:** `infra/snowflake/dbt/edgartools_gold/macros/`, `infra/snowflake/dbt/edgartools_gold/models/gold/`
**Files scanned:** `financial_factors.sql`, `financial_derived.sql` (referenced, not modified), `yoy_growth.sql`, `safe_ratio.sql`, `safe_ratio_signed.sql`, `_financial_factors_unit_tests.yml`, `gold.yml`
**Pattern extraction date:** 2026-06-30
