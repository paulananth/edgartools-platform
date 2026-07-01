# Phase 3: Cash Conversion Cycle - Pattern Map

**Mapped:** 2026-07-01
**Files analyzed:** 10
**Analogs found:** 10 / 10 (all are extend-existing-file, not new-file, patterns)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog (same file, prior addition) | Match Quality |
|---|---|---|---|---|
| `edgar_warehouse/parsers/financials_derived.py` | parser/transform | batch/transform | `_REVENUE_CONCEPTS` (multi-concept fallback) + `_GROSS_PROFIT_CONCEPTS` (single-concept) in same file | exact |
| `edgar_warehouse/silver_store.py` (DDL + migration dict + `merge_financial_derived`) | model/migration | CRUD (upsert/merge) | `inventory`/`accounts_receivable` column additions already present in same file (DDL line ~440-441, migration dict line ~590-599, merge SQL 4 places line ~2270-2410) | exact |
| `edgar_warehouse/serving/gold_models.py` | service (export) | batch/transform (silver→Parquet) | `_SEC_FINANCIAL_DERIVED_SCHEMA` + `_build_sec_financial_derived()` in same file | exact |
| `infra/terraform/snowflake/modules/native_pull/main.tf` | config/migration (Terraform DDL) | CRUD (declarative table def) | `SEC_FINANCIAL_DERIVED.columns` block in same file | exact |
| `infra/snowflake/dbt/edgartools_gold/macros/days_outstanding.sql` (new file) | utility (dbt macro) | transform | `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio.sql` (null-guard shape) + `cagr.sql` (extra numeric-parameter + doc-comment convention) | exact (structural), role-match (this is a new file, no existing `days_outstanding`) |
| `infra/snowflake/dbt/edgartools_gold/models/gold/financial_derived.sql` | model (dbt SQL) | transform/passthrough | Existing `w.accounts_receivable, w.inventory` passthrough lines in same file | exact |
| `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` | model (dbt SQL) | transform (ratio computation) | Existing `safe_ratio()`/`cagr()` macro-call select-list entries in same file (`inventory_to_assets`, `revenue_cagr_3y` etc.) | exact |
| `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` | config (dbt docs) | — | Existing `financial_factors.columns` doc blocks (`revenue_cagr_3y` etc., lines 129-188) | exact |
| `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_derived_unit_tests.yml` and `_financial_factors_unit_tests.yml` | test (dbt unit test) | request-response (fixture-based) | Existing fixture rows (`_financial_factors_unit_tests.yml` lines 1-93) | exact |
| `tests/unit/test_fundamentals_modules.py` | test (pytest) | request-response | `FinancialsDerivedTests._basic_fact_rows()` + `test_basic_derivation_produces_row` (lines 94-153) | exact |

## Pattern Assignments

### `edgar_warehouse/parsers/financials_derived.py` (parser, batch/transform)

**Analog:** same file — `_REVENUE_CONCEPTS` (multi-concept) and `_GROSS_PROFIT_CONCEPTS` (single-concept), lines 41-54.

**Concept-list pattern** (lines 41-54):
```python
_REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenueFromContractWithCustomer",
    "Revenues",
    "TotalRevenues",
]

_GROSS_PROFIT_CONCEPTS = [
    "GrossProfit",
]
```
Add, following the exact same declaration style (module-level list constant, placed near the other `_*_CONCEPTS` lists in the "Concept priority maps" section, lines 37-70):
```python
_COST_OF_REVENUE_CONCEPTS = [
    "CostOfGoodsAndServicesSold",
    "CostOfRevenue",
]

_ACCOUNTS_PAYABLE_CONCEPTS = [
    "AccountsPayableCurrent",
    "AccountsPayableTradeCurrent",
]
```

**Extraction + row-dict wiring** (lines 253-259 pick calls; lines 315-323 row dict) — insert alongside existing balance-sheet fields:
```python
# ── Balance sheet ─────────────────────────────────────────────────────────
...
inventory          = _pick(fact_map, _INVENTORY_CONCEPTS)
cost_of_revenue    = _pick(fact_map, _COST_OF_REVENUE_CONCEPTS)     # NEW
accounts_payable   = _pick(fact_map, _ACCOUNTS_PAYABLE_CONCEPTS)    # NEW
...
row = {
    ...
    "inventory":          inventory,
    "cost_of_revenue":    cost_of_revenue,     # NEW
    "accounts_payable":   accounts_payable,    # NEW
    "selling_general_admin_expense": sga,
    ...
}
```

**Error handling / validation:** `_pick(fact_map, concepts)` (defined elsewhere in this file) already returns `float | None` and silently returns `None` on no-match — no new error handling needed, follow the identical no-try/except style every other `_pick()` call uses.

---

### `edgar_warehouse/silver_store.py` (model/migration, CRUD)

**Analog:** same file, `inventory`/`accounts_receivable`/`selling_general_admin_expense` additions already present at all 4 touchpoints.

**1. CREATE TABLE DDL** (lines 418-469, insert after `inventory DOUBLE,` line 441):
```sql
accounts_receivable DOUBLE,
inventory           DOUBLE,
cost_of_revenue     DOUBLE,   -- NEW
accounts_payable    DOUBLE,   -- NEW
selling_general_admin_expense DOUBLE,
```

**2. Migration dict** (`_SEC_FINANCIAL_DERIVED_FACTOR_COLUMNS`, lines 590-600) — this dict drives `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for existing local DuckDB stores (line 620-623):
```python
_SEC_FINANCIAL_DERIVED_FACTOR_COLUMNS = {
    "current_assets": "DOUBLE",
    "current_liabilities": "DOUBLE",
    "accounts_receivable": "DOUBLE",
    "inventory": "DOUBLE",
    "cost_of_revenue": "DOUBLE",     # NEW
    "accounts_payable": "DOUBLE",    # NEW
    "selling_general_admin_expense": "DOUBLE",
    "retained_earnings": "DOUBLE",
    "depreciation_amortization": "DOUBLE",
    "property_plant_equipment_net": "DOUBLE",
    "shares_outstanding": "DOUBLE",
}
```

**3. `merge_financial_derived()` — 4 separate places, all in one method (lines 2270-2410):**
- Staging `CREATE TEMP TABLE stg_sec_financial_derived` DDL (lines 2274-2312) — add `cost_of_revenue DOUBLE,` / `accounts_payable DOUBLE,` after `inventory DOUBLE,` (line 2296).
- `insert_first_sql` column list + SELECT list (lines 2314-2339) — add both columns to both the `INSERT INTO ... (...)` column list and the `SELECT ...` list, positioned after `inventory`.
- `insert_last_sql` column list + SELECT list (lines 2341-2366) — identical addition, mirrored.
- `ON CONFLICT ... DO UPDATE SET` clause (lines 2366-2389, e.g. `inventory = excluded.inventory,`) — add `cost_of_revenue = excluded.cost_of_revenue,` and `accounts_payable = excluded.accounts_payable,`.

**Pitfall called out in RESEARCH.md Pattern 1 touchpoint 2:** missing any one of these 4 places silently drops the column from the merge — no exception raised.

---

### `edgar_warehouse/serving/gold_models.py` (service/export, batch/transform)

**Analog:** same file, `_SEC_FINANCIAL_DERIVED_SCHEMA` (lines 287-327) + `_build_sec_financial_derived()` (lines 1179-1226).

**PyArrow schema addition** (after `pa.field("inventory", pa.float64()),` at line 309):
```python
pa.field("inventory", pa.float64()),
pa.field("cost_of_revenue", pa.float64()),      # NEW
pa.field("accounts_payable", pa.float64()),     # NEW
pa.field("selling_general_admin_expense", pa.float64()),
```

**SELECT list addition** (after `inventory,` at line 1204, inside `_build_sec_financial_derived()`'s SQL):
```sql
inventory,
cost_of_revenue,      -- NEW
accounts_payable,     -- NEW
selling_general_admin_expense,
```
Both the schema field order and the SELECT column order must match — this file follows a strict "same order in both places" convention throughout (verified: every column in `_SEC_FINANCIAL_DERIVED_SCHEMA` has a corresponding, identically-ordered entry in the `SELECT`).

---

### `infra/terraform/snowflake/modules/native_pull/main.tf` (config/migration, CRUD declarative)

**Analog:** same file, `SEC_FINANCIAL_DERIVED.columns` block, lines 206-247.

**Column addition** (after `{ name = "INVENTORY", type = "FLOAT" },` at line 229):
```hcl
{ name = "INVENTORY", type = "FLOAT" },
{ name = "COST_OF_REVENUE", type = "FLOAT" },     # NEW
{ name = "ACCOUNTS_PAYABLE", type = "FLOAT" },    # NEW
{ name = "SELLING_GENERAL_ADMIN_EXPENSE", type = "FLOAT" },
```
Note the naming convention: all-caps snake_case matching Snowflake unquoted identifier convention, `type = "FLOAT"` for every DOUBLE-equivalent numeric field in this table (no precision/scale, unlike `NUMBER(38,0)` used for `CIK`).

**Critical follow-up (not a code pattern, a deploy step):** per RESEARCH.md Pitfall 1, this Terraform edit alone does not create the physical column — `terraform apply` must run against dev (then prod), followed by an explicit `SHOW COLUMNS IN TABLE EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED` verification. This is the same table with a live, currently-unresolved Phase 1/2 drift blocker (`current_assets` missing) documented in STATE.md.

---

### `infra/snowflake/dbt/edgartools_gold/macros/days_outstanding.sql` (new file — utility/macro, transform)

**Analog:** `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio.sql` (structural null-guard shape) + `cagr.sql` (extra-parameter + doc-comment convention).

**`safe_ratio.sql` full file (base shape to extend):**
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

**`cagr.sql` doc-comment convention (lines 1-18)** — every macro with a non-obvious design decision carries a leading `--` comment block explaining the choice and citing precedent/decision IDs. Follow this for `days_outstanding()`'s ending-balance-only choice (D-04/A4 in CONTEXT.md/RESEARCH.md).

**Recommended new file content** (from RESEARCH.md Pattern 2, already drafted and verified against the macro conventions above):
```sql
-- days_outstanding(balance_col, flow_col, days): balance / flow * days, e.g.
-- DSO = days_outstanding('accounts_receivable', 'revenue', 365).
-- Ending-balance single-period approximation (same convention as this codebase's
-- ROA/ROE — see financials_derived.py's "single-period approx" comment), not the
-- textbook average-of-beginning-and-ending-balance formula.
{% macro days_outstanding(balance_col, flow_col, days=365) %}
    case
        when {{ balance_col }} is not null
         and {{ flow_col }} is not null
         and {{ flow_col }} <> 0
        then {{ balance_col }} / {{ flow_col }} * {{ days }}
    end
{% endmacro %}
```

---

### `infra/snowflake/dbt/edgartools_gold/models/gold/financial_derived.sql` (dbt model, transform/passthrough)

**Analog:** same file, existing passthrough select-list, lines 76-127.

**Addition** (after `w.inventory,` at line 99):
```sql
w.inventory,
w.cost_of_revenue,      -- NEW
w.accounts_payable,     -- NEW
w.selling_general_admin_expense,
```
This model does column-by-column `select`, never `select *` — every silver column must be explicitly listed here or it never reaches `financial_factors.sql`.

---

### `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` (dbt model, transform/ratio computation)

**Analog:** same file — `l.inventory` passthrough (line 96) + `safe_ratio()`/`cagr()` macro-call entries in the final select (lines 106-162).

**Passthrough addition** (after `l.inventory,` at line 96, in the "Base accounting inputs" block):
```sql
l.inventory,
l.cost_of_revenue,     -- NEW
l.accounts_payable,    -- NEW
l.selling_general_admin_expense,
```

**Ratio addition** (new "V2 cash conversion cycle factors (Phase 3)" block, following the same `{{ macro(...) }} as column_name,` style as the existing V1/V2 blocks — see `inventory_to_assets` at line 111 and `gross_margin` at line 131):
```sql
-- V2 cash conversion cycle factors (Phase 3).
{{ days_outstanding('l.accounts_receivable', 'l.revenue') }} as days_sales_outstanding,
{{ days_outstanding('l.inventory', 'l.cost_of_revenue') }} as days_inventory_outstanding,
{{ days_outstanding('l.accounts_payable', 'l.cost_of_revenue') }} as days_payable_outstanding,
```
No FY-gating `case when l.fiscal_period = 'FY'` wrapper needed — unlike the CAGR block (lines 139-162), DSO/DIO/DPO are same-period ratios like `current_ratio`/`gross_margin`, not cross-period growth — do not copy the CAGR block's FY-only gating pattern here.

---

### `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` (dbt docs config)

**Analog:** same file, `financial_factors.columns` doc blocks for `revenue_cagr_3y` etc. (lines 129-188).

**Pattern to follow** (add 3 new column entries under the existing `- name: financial_factors` → `columns:` list, after the CAGR entries around line 188):
```yaml
      - name: days_sales_outstanding
        description: >
          Days Sales Outstanding: accounts_receivable / revenue * 365. Ending-balance
          single-period approximation (not average of beginning+ending), consistent
          with this codebase's ROA/ROE precedent. Universal across industries — the
          only CCC factor with near-100% coverage (Phase 3, D-03).
      - name: days_inventory_outstanding
        description: >
          Days Inventory Outstanding: inventory / cost_of_revenue * 365. Null for
          filers with no COGS/inventory line (banks, insurers, REITs, most SaaS) —
          same structural-null semantics as gross_margin (Phase 2), not a coverage
          defect. Measured coverage: ~51-63% of economically-applicable filers
          (Phase 3 D-01).
      - name: days_payable_outstanding
        description: >
          Days Payable Outstanding: accounts_payable / cost_of_revenue * 365. Same
          structural-null population and coverage caveat as days_inventory_outstanding
          (Phase 3 D-01).
```
Every existing Phase 1/2 CAGR/margin column carries a `description:` block explaining formula + null semantics + decision-ID cross-reference — match that density, not a one-line description.

---

### `_financial_derived_unit_tests.yml` and `_financial_factors_unit_tests.yml` (dbt unit test, request-response fixture)

**Analog:** `_financial_factors_unit_tests.yml` lines 1-93 (`financial_factors_complete_fy_ratios` test).

**Fixture-row pattern** — every existing fixture row (the `&factor_row_defaults` anchor, lines 10-36, and its override rows) must gain `cost_of_revenue`/`accounts_payable` keys, since RESEARCH.md's Wave 0 Gaps note flags that omission currently means "field doesn't exist" but will silently become "intentional null" once the column exists — ambiguous unless a dedicated fixture row exercises the null path explicitly:
```yaml
- &factor_row_defaults
  cik: 1
  ...
  inventory: 25
  cost_of_revenue: 20        # NEW
  accounts_payable: 15       # NEW
  selling_general_admin_expense: 12.5
  ...
```

**New expect-block entries** (mirroring the `inventory_to_assets: 0.1` style at line 78):
```yaml
- cik: 1
  accession_number: "0002"
  ...
  days_sales_outstanding: 73.0          # 30 / 150 * 365
  days_inventory_outstanding: <expected>
  days_payable_outstanding: <expected>
```

**Null-path fixture row (new, per RESEARCH.md Pitfall/Test Map):** add a row with `cost_of_revenue: null` (or omitted with an explicit comment) and assert `days_inventory_outstanding`/`days_payable_outstanding` are null, distinguishing "intentionally testing the null path" from "field just doesn't exist yet" — this is a new fixture row pattern, not present in the current file, needed specifically because of the coverage-null semantics documented in CONTEXT.md D-01.

---

### `tests/unit/test_fundamentals_modules.py` (pytest, request-response)

**Analog:** same file — `FinancialsDerivedTests._basic_fact_rows()` (lines 95-113) + `test_basic_derivation_produces_row` (lines 123-153).

**Fixture extension** — add to `_basic_fact_rows()`'s returned list, following the exact `{"concept": ..., "value": ...}` dict shape:
```python
{"concept": "CostOfGoodsAndServicesSold", "value": 40_000_000_000},   # NEW
{"concept": "AccountsPayableCurrent", "value": 8_000_000_000},        # NEW
```

**New assertions** in `test_basic_derivation_produces_row` (or a new test method, following the same `self.assertEqual(row["field"], expected)` style as lines 137-148):
```python
self.assertEqual(row["cost_of_revenue"], 40_000_000_000)
self.assertEqual(row["accounts_payable"], 8_000_000_000)
```

**Recommend also adding** a dedicated fallback-concept test (new method) verifying `_pick()` correctly prefers `CostOfGoodsAndServicesSold` over `CostOfRevenue` when both are present, and `AccountsPayableCurrent` over `AccountsPayableTradeCurrent` — mirrors how `_REVENUE_CONCEPTS`'s multi-tag fallback ordering would ideally be tested (no existing test does this for revenue either, so this is a net-new test pattern, not a copy of an existing one — use `_basic_fact_rows()`'s dict-list shape as the template).

## Shared Patterns

### 9-touchpoint "new derived silver field" checklist
**Source:** RESEARCH.md Pattern 1 (verified against every file above this session).
**Apply to:** Both `cost_of_revenue` and `accounts_payable` — each field independently touches all 9 files/locations:
1. `financials_derived.py` — concept list + `_pick()` + row dict key
2. `silver_store.py` — DDL + migration dict + `merge_financial_derived()` (4 places)
3. `gold_models.py` — PyArrow schema + SELECT list
4. `native_pull/main.tf` — Terraform column list + explicit `terraform apply` + `SHOW COLUMNS` verification
5. `financial_derived.sql` — passthrough select
6. `financial_factors.sql` — passthrough select + ratio expression(s)
7. `gold.yml` — column doc block
8. `_financial_derived_unit_tests.yml` / `_financial_factors_unit_tests.yml` — fixture rows (all existing rows need the new keys, plus one explicit null-path row)
9. `tests/unit/test_fundamentals_modules.py` — Python-level extraction assertion

### Null-safe ratio macro convention
**Source:** `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio.sql`, `cagr.sql`.
**Apply to:** `days_outstanding.sql` (new macro) — same `case when ... is not null and ... <> 0 then ... end` null-guard shape; deviates from `cagr()` by not requiring strict positivity (a negative `accounts_payable`/`inventory` balance is not expected in practice, unlike CAGR's negative-base defense).

### Terraform-drift verification step (explicit task, not assumed)
**Source:** RESEARCH.md Pitfall 1; live STATE.md Phase 1/2 blocker on this exact table.
**Apply to:** Any plan touching `native_pull/main.tf` in this phase — must include an explicit "run `terraform apply` against dev (then prod) + `SHOW COLUMNS IN TABLE EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED`" task, not a side-effect assumption of the file edit.

## No Analog Found

None — every file in this phase is an extension of an existing file that already has at least one prior addition of the identical shape (a new derived field, a new ratio column, or a new macro following an established sibling macro's convention). The `days_outstanding.sql` macro file itself is new but has two structurally-identical sibling macros (`safe_ratio.sql`, `cagr.sql`) as strong analogs.

## Metadata

**Analog search scope:** `edgar_warehouse/parsers/`, `edgar_warehouse/silver_store.py`, `edgar_warehouse/serving/gold_models.py`, `infra/terraform/snowflake/modules/native_pull/`, `infra/snowflake/dbt/edgartools_gold/macros/`, `infra/snowflake/dbt/edgartools_gold/models/gold/`, `tests/unit/test_fundamentals_modules.py`
**Files scanned:** 10 (all read directly this session; no grep-only files)
**Pattern extraction date:** 2026-07-01
