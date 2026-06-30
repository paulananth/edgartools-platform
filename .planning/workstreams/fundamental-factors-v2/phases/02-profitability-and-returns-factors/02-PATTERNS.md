# Phase 2: Profitability And Returns Factors - Pattern Map

**Mapped:** 2026-06-30
**Files analyzed:** 4 (1 new, 3 modified)
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|---------------|
| `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql` | utility (dbt macro) | transform | `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio.sql` | exact (sibling macro, same file is the template) |
| `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` | model (dbt SQL, gold layer) | transform / CRUD-read | itself (existing file being extended) | exact — this IS the file, add columns to existing `select` |
| `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml` | test (dbt unit test) | transform | itself (existing file being extended) | exact — this IS the file, add new test case(s) |
| `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` | config (dbt schema/docs YAML) | — | itself (existing file being extended) | exact — this IS the file, add `roic` column description under `financial_factors` |

No new model files. No silver/loader/parser files touched (per CONTEXT.md domain boundary — pure gold-layer SQL).

## Pattern Assignments

### `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql` (new macro)

**Analog:** `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio.sql` (entire file, 8 lines)

**Full source to copy/modify** (lines 1-8):
```sql
{% macro safe_ratio(numerator_col, denominator_col) %}
    case
        when {{ numerator_col }} is not null
         and {{ denominator_col }} is not null
         and {{ denominator_col }} <> 0
        then {{ numerator_col }} / {{ denominator_col }}
    end
{% endmacro %}
```

**Required diff for the new macro:** rename to `safe_ratio_signed`, change the comparison operator on line 5 from `<> 0` to `> 0` (this single-character change encodes D-01's negative-equity null guard — `> 0` excludes both zero and negative denominators in one condition, no extra `and` clause needed). Whitespace/indentation style must match exactly (4-space indent inside `case`, blank line conventions identical to the analog).

Target result:
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

---

### `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` (model, modified)

**Analog:** itself — extend the existing `select` list using the file's own established convention. No external analog needed; the file already contains 9/9 examples of the exact pattern to repeat for the 6 new columns.

**Imports/config header pattern** (lines 1-6, unchanged — do not touch):
```sql
-- FINANCIAL_FACTORS: Accounting-only fundamental factors per financial period.
--
-- Grain: one row per (cik, accession_number, fiscal_period, period_end).
-- This model intentionally excludes price, market cap, and market-derived
-- ratios. Shares outstanding is included as an accounting disclosure.
{{ gold_model_config('FINANCIAL_FACTORS') }}
```

**`safe_ratio()` usage pattern to copy** (lines 71-82, repeat this exact macro-call shape for gross_margin/operating_margin/net_margin/return_on_assets):
```sql
{{ safe_ratio('l.working_capital', 'l.total_assets') }} as working_capital_to_assets,
{{ safe_ratio('l.current_assets', 'l.current_liabilities') }} as current_ratio,
{{ safe_ratio('(l.current_assets - l.inventory)', 'l.current_liabilities') }} as quick_ratio,
{{ safe_ratio('l.accounts_receivable', 'l.revenue') }} as receivables_to_revenue,
```

**Base accounting inputs block** (lines 49-67) — append `l.gross_profit` and `l.ebit` here for debugging-visibility consistency (both already flow through via `base`'s `select d.*` from `financial_derived`, no upstream model change required):
```sql
    -- Base accounting inputs retained for coverage and factor debugging.
    l.revenue,
    l.total_assets,
    l.total_liabilities,
    l.total_equity,
    ...
    l.shares_outstanding,
```

**FY-only gate pattern (DO NOT copy for Phase 2 factors)** (lines 83-92) — this is the anti-pattern to avoid per D-02:
```sql
case
    when l.fiscal_period = 'FY'
    then {{ yoy_growth('l.total_assets', 'py.total_assets') }}
end as asset_growth_yoy,
```
New margin/ROE/ROA/ROIC columns must NOT be wrapped in `case when l.fiscal_period = 'FY'` — they compute for every period.

**Insertion point:** append new columns after line 92 (`shares_outstanding_yoy_change`) and before line 94 (`l.parser_version`), per RESEARCH.md's illustrated diff:
```sql
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

**Error handling pattern:** N/A — this is dbt SQL, not application code. "Error handling" here means the null/zero-safe-division macro pattern (Snowflake raises `100051 (22012): Division by zero` on raw `/`; `safe_ratio()`/`safe_ratio_signed()` prevent this). Never write a raw `/` in this file.

---

### `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml` (test, modified)

**Analog:** itself — extend using the existing `<<: *factor_row_defaults` anchor-merge pattern (lines 1-111 contain 2 existing test cases to model new ones on).

**Anchor-merge fixture pattern** (lines 10-36 define the anchor, lines 37-58 and 92-102 show override merges):
```yaml
- &factor_row_defaults
  cik: 1
  accession_number: "0001"
  fiscal_year: 2023
  fiscal_period: "FY"
  period_end: "2023-12-31"
  form_type: "10-K"
  revenue: 125
  total_assets: 250
  ...
  parser_version: "1"
  ingested_at: "2024-01-01 00:00:00"
- <<: *factor_row_defaults
  accession_number: "0002"
  fiscal_year: 2024
  ...
```

**IMPORTANT:** `factor_row_defaults` anchor currently has no `gross_profit`/`ebit`/`roic` keys (the model didn't select them before this phase). New test cases that need these fields must either extend the shared anchor (risk: changes the baseline for the two existing test cases too — check their `expect` blocks still pass) or specify `gross_profit`/`ebit` inline per-row as the negative-equity test case below does. Prefer per-row specification to avoid perturbing existing tests, unless the planner wants `gross_profit`/`ebit`/`roic` added to the anchor for all future test rows.

**`expect.rows` full-row-comparison gotcha** (documented in `_financial_derived_unit_tests.yml`'s header comment, applies identically here): omitted columns in an `expect` row are NOT checked, but every row in `given` needs a matching row in `expect` — partial column lists are fine, partial row lists are not.

**New test case to add** (per RESEARCH.md Code Examples, verify exact decimal output against a real `dbt build` before committing):
```yaml
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
        operating_margin: -0.0667  # VERIFY against real dbt build/test output before commit
```

Also extend the existing `financial_factors_complete_fy_ratios` and `financial_factors_quarterly_cross_year_factors_are_null` test cases' `expect` blocks with assertions for the new positive-value columns (`gross_margin`, `operating_margin`, `net_margin`, `return_on_equity`, `return_on_assets`, `roic`) to cover PROF-01/PROF-03's "computes correctly for FY and quarterly rows" requirement — this requires also adding `gross_profit`/`ebit`/`roic` values to those `given` rows (currently absent from `factor_row_defaults`).

---

### `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` (config, modified)

**Analog:** itself — `financial_factors` model entry already exists (lines 111-122); this is the only place in the file with a per-model `description:` to extend, and the file has NO existing per-ratio-column `description:` precedent anywhere (only PK/grain columns get `columns:` blocks, and only with `not_null` tests).

**Existing pattern to extend** (lines 111-122):
```yaml
- name: financial_factors
  description: Accounting-only fundamental factors per (cik, accession_number, fiscal_period, period_end). Excludes price, market cap, and market-derived ratios.
  columns:
    - name: cik
      tests:
        - not_null
    - name: accession_number
      tests:
        - not_null
    - name: fiscal_period
      tests:
        - not_null
```

**D-03 requires documenting the ROIC pre-tax simplification here.** Two valid approaches (per RESEARCH.md Pitfall 4 — planner/implementer must pick one explicitly, do not leave ambiguous):
1. **Model-level** (matches 100% of existing file convention — no column ever has a `description:` today): append a sentence to the `description:` field on line 112.
2. **Column-level** (first precedent in this file, but more semantically precise — RESEARCH.md's stated recommendation): add a new `columns:` entry:
```yaml
    - name: roic
      description: >
        Simplified pre-tax ROIC (EBIT / Average Invested Capital). Does not apply
        a NOPAT tax adjustment — financials_derived.py has no parsed
        income_tax_expense/effective-tax-rate field today (see
        edgar_warehouse/parsers/financials_derived.py line 279).
```

---

## Shared Patterns

### `safe_ratio()` macro convention (null/zero-safe division)
**Source:** `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio.sql`
**Apply to:** `gross_margin`, `operating_margin`, `net_margin`, `return_on_assets` in `financial_factors.sql`
```sql
{% macro safe_ratio(numerator_col, denominator_col) %}
    case
        when {{ numerator_col }} is not null
         and {{ denominator_col }} is not null
         and {{ denominator_col }} <> 0
        then {{ numerator_col }} / {{ denominator_col }}
    end
{% endmacro %}
```
100% of existing ratio columns in `financial_factors.sql` (9/9) use this macro — never write a raw `/` in this model. Snowflake raises a hard division-by-zero error (`100051`) on unguarded division, which would fail the entire dynamic table refresh, not just null one row.

### `safe_ratio_signed()` macro convention (NEW — sign-checked division, D-01)
**Source:** new file, sibling to `safe_ratio.sql`, single-character logic diff (`<>` → `>`)
**Apply to:** `return_on_equity` only (per D-01/Claude's Discretion — do not generalize to ROA or any other factor in this phase)

### dbt unit test anchor-merge pattern
**Source:** `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml` lines 10-58
**Apply to:** all new test cases — use `&factor_row_defaults` / `<<: *factor_row_defaults` YAML anchor merging, override only the fields relevant to the specific test scenario.

### `gold_model_config()` macro (dynamic table materialization)
**Source:** `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` line 6
**Apply to:** N/A for this phase — `financial_factors.sql`'s model-level config is unchanged; only the `select` list grows. No new model file means no new `gold_model_config()` call needed. Note for awareness only: per CLAUDE.md, `materialized='dynamic_table'` models require `dbt run --select financial_factors --full-refresh` to redeploy after a SQL body change (config-only diffing means `dbt run` alone is a silent no-op for body changes).

## No Analog Found

None — every file in this phase's scope is either an extension of an existing file or a near-identical sibling of an existing macro file. All four files have exact or near-exact analogs already read above.

## Metadata

**Analog search scope:** `infra/snowflake/dbt/edgartools_gold/models/gold/`, `infra/snowflake/dbt/edgartools_gold/macros/`
**Files scanned:** `financial_factors.sql`, `financial_derived.sql`, `safe_ratio.sql`, `_financial_factors_unit_tests.yml`, `gold.yml` (5 files, all read directly per CONTEXT.md/RESEARCH.md canonical refs — no further codebase search needed since RESEARCH.md already pre-identified exact file:line analogs)
**Pattern extraction date:** 2026-06-30
