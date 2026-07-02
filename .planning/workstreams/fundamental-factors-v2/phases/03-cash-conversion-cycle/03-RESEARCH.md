# Phase 3: Cash Conversion Cycle - Research

**Researched:** 2026-07-01
**Domain:** SEC XBRL concept-tag coverage measurement; silver parser schema addition; dbt gold-layer ratio macros
**Confidence:** MEDIUM (coverage numbers are VERIFIED against a live authoritative source; the "acceptable threshold" judgment itself is a policy call, not a fact)

## Summary

This phase has two independent parts that got bundled under one requirement (CCC-01) but
have very different risk profiles. **DSO (Days Sales Outstanding) needs zero new fields** —
`accounts_receivable` and `revenue` already exist in `sec_financial_derived`/`financial_derived`.
**DIO (Days Inventory Outstanding) and DPO (Days Payable Outstanding) both need a new
`cost_of_revenue` field, and DPO additionally needs a new `accounts_payable` field that is
not currently parsed anywhere in the codebase** (confirmed via full grep — no `AccountsPayable`
concept, silver column, or gold column exists today). `inventory` for DIO already exists.

I ran the actual coverage measurement this research question flagged as "may need to be a
live-data task" — using the public SEC XBRL Frames API (`data.sec.gov/api/xbrl/frames/...`),
which is a free, no-auth, one-shot-per-concept GET endpoint that returns one fact per
reporting entity for a given concept/period. This does **not** violate the milestone's
"no new loader" constraint — it is a one-time research measurement using a different SEC
endpoint than the platform's own `companyfacts` loader, not a new production fetch path.
Results (CY2023 annual frame, verified live 2026-07-01):

- `CostOfGoodsAndServicesSold` ∪ `CostOfRevenue`: **3,390 unique CIKs**
- As % of a broad "files structured 10-K/10-Q financials" proxy (`NetIncomeLoss` reporters,
  6,364 CIKs): **51.5%**
- As % of revenue-tag reporters (`Revenues` ∪ `RevenueFromContractWithCustomerExcludingAssessedTax`,
  5,016 CIKs): **63.3%**
- `AccountsPayableCurrent`: 3,908 CIKs (**58.9%** of the NetIncomeLoss proxy)
- `InventoryNet`: 2,705 CIKs (**41.0%** of the NetIncomeLoss proxy — expected, most
  service/financial/software filers carry no inventory)
- Companies with **all three** (COGS-family ∩ AP ∩ Inventory) simultaneously non-null:
  **1,753 CIKs, 27.5%** of the NetIncomeLoss proxy

The low "all-three" number is a *structural* fact about the economy (banks, insurers,
REITs, and most SaaS/software companies genuinely have no COGS/inventory line — it is not
a missing-tag problem), not evidence of poor tagging discipline among companies that
*do* have physical costs. This mirrors an existing precedent already shipped in this
model: `gross_margin` (Phase 2) is null for the same population, and nobody proposed
declaring `gross_margin` out of scope for that reason.

**Primary recommendation:** Ship all three (DSO/DIO/DPO) rather than declaring CCC-01 out
of scope. Treat the ~51-63% COGS-family coverage rate as the CCC-02 evidence and document
it as an accepted, expected null rate (same semantic class as `gross_margin`), not a data
quality failure — but this framing is a judgment call, not a verified fact, and should be
confirmed with the user/discuss-phase before being treated as a locked decision (see
Assumptions Log A1).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `cost_of_revenue` / `accounts_payable` extraction from XBRL facts | Backend/ETL (silver parser, `financials_derived.py`) | — | Concept-tag selection is a research/business decision made once per fact, same tier as existing `gross_profit`/`accounts_receivable` extraction |
| Coverage measurement (CCC-02 evidence) | Research/one-off script (SEC Frames API) | — | Not a production pipeline component; a point-in-time measurement, discarded after the decision is made |
| DSO/DIO/DPO ratio computation | Database/Gold (`financial_factors.sql`, dbt) | — | Pure ratio of already-selected silver columns, same tier as existing `current_ratio`/`quick_ratio` |
| Native-pull Snowflake source table schema (`SEC_FINANCIAL_DERIVED`) | Infra/Terraform (`native_pull/main.tf`) | Database/Gold | The physical Snowflake column must exist before dbt's `ref()`/`source()` can select it; declarative Terraform table resource, not dbt-managed |
| CCC-02 out-of-scope decision (if coverage judged unacceptable) | Requirements/Product | — | Policy threshold call, not a technical implementation |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CCC-01 | Consumer can query DSO/DIO/DPO, requiring a new `cost_of_revenue` field | Coverage measured live via SEC Frames API (Summary); parser addition pattern documented below (Architecture Patterns, Pattern 1); DPO also needs a new `accounts_payable` field not mentioned in ROADMAP.md — flagged as a scope gap the planner must account for |
| CCC-02 | If coverage is poor, declare out of scope with measured evidence | Coverage numbers above are the CCC-02 evidence regardless of which way the decision goes; "acceptable" threshold is not industry-documented (see Open Questions) — recommend proceeding, but this is Claude's-discretion-level, not settled fact |

## Standard Stack

No new libraries. This phase touches only: `edgar_warehouse/parsers/financials_derived.py`
(pure Python, no new deps), `edgar_warehouse/silver_store.py` (DuckDB DDL, existing dep),
`edgar_warehouse/serving/gold_models.py` (PyArrow, existing dep), dbt SQL/Jinja (existing),
and `infra/terraform/snowflake/modules/native_pull/main.tf` (existing Snowflake Terraform
provider). The coverage-measurement research step used only `curl` against a public SEC
endpoint — not a project dependency, not part of any deliverable.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SEC XBRL Frames API for coverage measurement | Live sampling via the platform's own `companyfacts` loader across N companies already in the warehouse | Frames API is a full-population census for one period/concept in a single HTTP call; sampling via the loader would need to actually fetch+parse N companies' `companyfacts` (slow, and arguably closer to violating "no new loader" in spirit even if not in fact). Frames API is strictly better for this one-off measurement. |
| Average-balance DSO/DIO/DPO (textbook formula uses average of beginning+ending balance) | Ending-balance-only (single period) | This codebase already uses ending-balance-only for ROA/ROE (`financials_derived.py` line 275 comment: "single-period approx uses ending assets") — averaging would require a self-join to the prior period the same way `prior_year_values`/`prior_fy_values` CTEs do for CAGR, adding complexity the existing precedent doesn't require. Recommend following the established ending-balance precedent for consistency, not textbook purity. |

## Package Legitimacy Audit

Not applicable — this phase installs no new packages (Python or otherwise). All work uses
existing project dependencies (Python stdlib, `duckdb`, `pyarrow`, dbt-snowflake, Terraform
Snowflake provider) already present in `pyproject.toml`/`uv.lock`/`infra/terraform`.

## Architecture Patterns

### System Architecture Diagram

```
SEC data.sec.gov "companyfacts" JSON  (already fetched by existing loader — NOT re-fetched)
        |
        v
edgar_warehouse/parsers/financials_derived.py
  compute_derived_for_accession()
  -- ADD: _COST_OF_REVENUE_CONCEPTS lookup -> cost_of_revenue
  -- ADD: _ACCOUNTS_PAYABLE_CONCEPTS lookup -> accounts_payable
        |
        v
edgar_warehouse/silver_store.py
  sec_financial_derived DuckDB table (silver)
  -- ADD: cost_of_revenue DOUBLE, accounts_payable DOUBLE columns
  -- ADD: both to _SEC_FINANCIAL_DERIVED_FACTOR_COLUMNS migration dict
  -- ADD: both to merge_financial_derived() staging DDL / INSERT / UPDATE column lists
        |
        v
edgar_warehouse/serving/gold_models.py
  _SEC_FINANCIAL_DERIVED_SCHEMA (PyArrow) + _build_sec_financial_derived()
  -- ADD: both fields to schema + SELECT list  (this is the export-to-Parquet step)
        |
        v
S3 Snowflake-export Parquet  ->  Snowflake native-pull COPY INTO / MERGE
  infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql
  (generic: MERGE columns come from target table's INFORMATION_SCHEMA.COLUMNS —
   no code change needed here IF the target table already has the columns)
        |
        v
Snowflake EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED  (physical table)
  *** MUST physically have cost_of_revenue / accounts_payable columns BEFORE
      the MERGE above can write them — this is a Terraform-managed table ***
  infra/terraform/snowflake/modules/native_pull/main.tf
  -- ADD: both columns to the SEC_FINANCIAL_DERIVED column list; terraform apply
        |
        v
infra/snowflake/dbt/edgartools_gold/models/gold/financial_derived.sql
  -- ADD: w.cost_of_revenue, w.accounts_payable to the final select list
        |
        v
infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql
  -- ADD: days_outstanding()-style ratios for DSO / DIO / DPO
        |
        v
Consumer query (Streamlit dashboard / ad-hoc SQL)
```

### Recommended Project Structure

No new files/directories — this phase only extends existing files at every layer shown
above. One new dbt macro file is warranted (see Pattern 2).

### Pattern 1: Adding a new derived silver field (concept-tag fallback list)

**What:** The exact, currently-shipped pattern for turning an XBRL concept into a silver
column, illustrated by `gross_profit` (single-concept list, simplest case) and `_REVENUE_CONCEPTS`
(multi-concept fallback list, the pattern `cost_of_revenue` should follow since multiple
XBRL tag variants exist for cost of revenue).

**When to use:** Any time a new line item needs to be pulled from the already-fetched
`companyfacts` facts (no new SEC fetch).

**Example — current `gross_profit` (single concept):**
```python
# edgar_warehouse/parsers/financials_derived.py:52-54
_GROSS_PROFIT_CONCEPTS = [
    "GrossProfit",
]
```

**Example — current `_REVENUE_CONCEPTS` (fallback-list pattern to follow for cost_of_revenue):**
```python
# edgar_warehouse/parsers/financials_derived.py:41-50
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
```

**Recommended new lists (concept names verified live against the SEC Frames API — see
Package/Coverage evidence above; `CostOfGoodsSold` and `CostOfServices` returned 404
"NoSuchKey" from the Frames API for both CY2022 and CY2023, meaning no filer's frame data
exists for those exact element names in the current us-gaap taxonomy — do not include them
without separately confirming the exact taxonomy element name, e.g. via the FASB taxonomy
viewer):**
```python
_COST_OF_REVENUE_CONCEPTS = [
    "CostOfGoodsAndServicesSold",  # [VERIFIED: SEC XBRL Frames API — 1,895 CY2023 filers]
    "CostOfRevenue",               # [VERIFIED: SEC XBRL Frames API — 1,667 CY2023 filers]
]

_ACCOUNTS_PAYABLE_CONCEPTS = [
    "AccountsPayableCurrent",      # [VERIFIED: SEC XBRL Frames API — 3,908 CY2023Q4I filers]
    "AccountsPayableTradeCurrent", # [ASSUMED — common secondary tag, not measured this session]
]
```

**Extraction + row dict wiring (same pattern as existing balance-sheet fields, lines
253-259 and 315-323 of `financials_derived.py`):**
```python
# In the "Balance sheet" section (after line 257's `inventory = _pick(...)`)
cost_of_revenue    = _pick(fact_map, _COST_OF_REVENUE_CONCEPTS)
accounts_payable   = _pick(fact_map, _ACCOUNTS_PAYABLE_CONCEPTS)

# In the returned row dict (after "inventory": inventory,)
"cost_of_revenue":     cost_of_revenue,
"accounts_payable":    accounts_payable,
```

**Full checklist of touchpoints for this one field addition** (missing any of these causes
either a silent `AttributeError`-free no-op — the field is computed in Python but never
reaches Snowflake — or an outright pipeline failure; confirmed by reading each file):

1. `edgar_warehouse/parsers/financials_derived.py` — concept list + `_pick()` call + row dict key (Pattern 1 above)
2. `edgar_warehouse/silver_store.py` — `sec_financial_derived` `CREATE TABLE` DDL (~line 418-469) + `_SEC_FINANCIAL_DERIVED_FACTOR_COLUMNS` dict (~line 590, drives the `ALTER TABLE ADD COLUMN IF NOT EXISTS` migration for existing local DuckDB stores) + `merge_financial_derived()`'s staging DDL, both `INSERT` column lists, and the `ON CONFLICT ... DO UPDATE SET` column list (~lines 2270-2410) — **4 separate places in one method**, each must list the new columns or the MERGE silently drops them
3. `edgar_warehouse/serving/gold_models.py` — `_SEC_FINANCIAL_DERIVED_SCHEMA` PyArrow schema (~line 287) + `_build_sec_financial_derived()`'s `SELECT` list (~line 1179) — this is the silver → Parquet export step; a field present in DuckDB but missing here never reaches S3
4. `infra/terraform/snowflake/modules/native_pull/main.tf` — the `SEC_FINANCIAL_DERIVED` `columns` list (~line 206-246) that declaratively defines the physical Snowflake table — **must be applied via `terraform apply` against each target Snowflake account (dev, then prod) before the new columns physically exist**
5. `infra/snowflake/dbt/edgartools_gold/models/gold/financial_derived.sql` — add `w.cost_of_revenue, w.accounts_payable` to the final `select` list (this model does `select * , ...` style column-by-column, not `select *`)
6. `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` — add the columns to `base`'s passthrough selects if surfaced raw, plus the DSO/DIO/DPO ratio expressions
7. `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` — document the new `financial_factors` columns (existing precedent: every Phase 1/2 CAGR/margin column got a `description:` block, see lines 129-188)
8. `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_derived_unit_tests.yml` and `_financial_factors_unit_tests.yml` — extend fixture rows with the two new fields (every existing fixture row currently omits them, so DSO/DIO/DPO tests would compute against implicit nulls unless fixtures are extended)
9. `tests/unit/test_fundamentals_modules.py` (or a new test file) — Python-level unit test for `compute_derived_for_accession()` asserting `cost_of_revenue`/`accounts_payable` extraction, following the existing `_basic_fact_rows()` fixture pattern (lines 116-172)

### Pattern 2: New dbt macro for "days outstanding" ratios (research question 5)

**What:** No existing macro handles the `(balance / flow) * days_in_period` shape. The
four existing macros (`safe_ratio`, `safe_ratio_signed`, `yoy_growth`, `cagr`) are all
plain ratios or growth rates — none multiply by a day-count constant.

**When to use:** DSO, DIO, DPO — and any future "days of X" factor.

**Recommended new macro**, following the exact structural convention of `safe_ratio.sql`
(null-safe divide-by-zero guard) plus a `days` parameter to mirror `cagr()`'s `years`
parameter style:
```sql
-- infra/snowflake/dbt/edgartools_gold/macros/days_outstanding.sql
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

**Usage in `financial_factors.sql`** (added alongside the existing V2 profitability block):
```sql
-- V2 cash conversion cycle factors (Phase 3).
{{ days_outstanding('l.accounts_receivable', 'l.revenue') }} as days_sales_outstanding,
{{ days_outstanding('l.inventory', 'l.cost_of_revenue') }} as days_inventory_outstanding,
{{ days_outstanding('l.accounts_payable', 'l.cost_of_revenue') }} as days_payable_outstanding,
```

Note DSO's formula uses `revenue` as the flow denominator (not `cost_of_revenue`) — this
is the standard formula (verified via WebSearch, multiple corroborating sources: Wall
Street Prep, Breaking Into Wall Street, CFI). **DSO therefore needs no new field at all**
and could ship independently of the DIO/DPO coverage question if the planner wants to
de-risk by splitting it out.

### Anti-Patterns to Avoid

- **Requiring average (beginning+ending) balances for DSO/DIO/DPO:** would require adding
  a new self-join CTE (like `prior_fy_values`) purely for this, when the codebase's own
  ROA/ROE precedent already establishes ending-balance-only as the house convention. Doing
  this differently for CCC factors than for return factors is an inconsistency, not a
  correctness improvement.
- **Assuming the Terraform `snowflake_table` column addition is a no-op deploy step:**
  it requires an explicit `terraform apply` against the target Snowflake account. The
  ROADMAP/STATE.md's existing Phase 1/2 blocker (`SEC_FINANCIAL_DERIVED` missing
  `current_assets` and other columns in the dev account, discovered 2026-06-30) is direct
  evidence this step gets skipped in practice — this phase adds two *more* columns to the
  same table and risks the identical failure mode if the plan does not include an explicit
  "run terraform apply against dev (and eventually prod), then verify via
  `SHOW COLUMNS IN TABLE EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED`" task.
- **Treating `CostOfGoodsSold` as a valid taxonomy element name:** it returned HTTP 404
  "NoSuchKey" from the SEC Frames API for two different years, strongly suggesting it is
  either a legacy/deprecated element (pre-dating the "AndServices" rename) or was never a
  valid us-gaap element. Use `CostOfGoodsAndServicesSold` instead.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Measuring XBRL tag coverage across filers | A script that pulls `companyfacts` for N sampled companies via the platform's own loader | SEC's public XBRL Frames API (`data.sec.gov/api/xbrl/frames/us-gaap/{concept}/USD/CY{year}.json`) | One HTTP call per concept returns every reporting entity's latest value for that calendar period — a near-census, not a sample, and doesn't touch the platform's loader/rate limiter/bronze storage at all |
| "Days outstanding" ratio math | Inline `(x / y) * 365` repeated 3 times in `financial_factors.sql` | The new `days_outstanding()` macro (Pattern 2) | Matches the existing macro-per-formula-shape convention (`cagr`, `yoy_growth`, `safe_ratio`) already established in this dbt project — a bare inline expression would be the first ratio in this model not going through a shared macro |

**Key insight:** The genuinely hard part of this phase is not the SQL or the Python
parser (both are copy-the-existing-pattern work) — it is that a new silver field touches
9 separate files/resources across 3 layers (Python/DuckDB, PyArrow export, Snowflake
Terraform DDL), and this codebase has already demonstrated (via the live Phase 1/2
blocker) that the Terraform/native-pull layer is the one most likely to silently drift
out of sync.

## Common Pitfalls

### Pitfall 1: Forgetting the Snowflake-side physical column (repeat of the live Phase 1/2 blocker)

**What goes wrong:** Code changes to `financials_derived.py`/`silver_store.py`/
`gold_models.py`/`financial_derived.sql` all pass `dbt compile`/`dbt parse` and look
"done," but the actual Snowflake `EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED` table never
gets the new columns because nobody ran `terraform apply`.

**Why it happens:** `dbt compile`/`dbt parse` only validate Jinja/SQL syntax against the
dbt project's own model definitions — they do not touch the live warehouse and cannot
detect a missing source column. The failure only surfaces at `dbt run`/`dbt test` time
(exactly the failure mode STATE.md documents happening right now for `current_assets`,
unrelated to this phase but the same root-cause class).

**How to avoid:** Make "confirm `SHOW COLUMNS IN TABLE EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED`
includes `cost_of_revenue`/`accounts_payable`" an explicit, separate verification task in
the plan — not an assumed side effect of the Terraform file edit. Given the existing
unresolved Phase 1/2 blocker in this exact table, budget for this being the single most
likely thing to go wrong in this phase.

**Warning signs:** `dbt run --select financial_derived` (not `--full-refresh`, since this
is a genuinely new column, not just a config change) either silently returns nulls for
the new columns, or errors with `invalid identifier` / `Invalid column name` — the same
error text already seen in this milestone's STATE.md.

### Pitfall 2: Treating "gap in requirements" (missing `accounts_payable`) as covered by existing research

**What goes wrong:** ROADMAP.md and REQUIREMENTS.md both describe this phase as needing
"one new silver field" (`cost_of_revenue`). A planner reading only those documents (not
this research) would plan for one field addition and discover mid-implementation that DPO
also needs `accounts_payable`, which was never mentioned.

**Why it happens:** The milestone's original research pass (ROADMAP.md's "Research
Evidence" section, 2026-06-29) focused on `cost_of_revenue` because that was the field
explicitly named in the initial feasibility scan; nobody separately checked whether
`accounts_payable` already existed for DPO's denominator pairing.

**How to avoid:** Plan for two new silver fields (`cost_of_revenue`, `accounts_payable`),
not one. Both go through the identical 9-touchpoint pattern in Pattern 1.

### Pitfall 3: Assuming DSO shares DIO/DPO's feasibility risk

**What goes wrong:** Because CCC-01/CCC-02 bundle DSO+DIO+DPO under one coverage-gated
requirement, a plan might gate *all three* behind the coverage research spike's outcome —
including DSO, which needs zero new fields and has near-100% coverage today (subject only
to `accounts_receivable`/`revenue` already being null for the same structural reasons
`gross_margin` is).

**How to avoid:** Consider splitting into "DSO ships regardless" + "DIO/DPO ship if
coverage is judged acceptable" if the planner wants to de-risk incrementally, rather than
an all-or-nothing decision on the whole requirement.

## Code Examples

### DuckDB DDL addition (silver_store.py CREATE TABLE, ~line 440)
```sql
-- Source: edgar_warehouse/silver_store.py, existing sec_financial_derived DDL pattern
accounts_receivable DOUBLE,
inventory            DOUBLE,
cost_of_revenue      DOUBLE,   -- NEW
accounts_payable     DOUBLE,   -- NEW
selling_general_admin_expense DOUBLE,
```

### DuckDB schema-evolution migration dict addition (silver_store.py, ~line 590)
```python
# Source: edgar_warehouse/silver_store.py _SEC_FINANCIAL_DERIVED_FACTOR_COLUMNS
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

### Terraform native-pull column addition (main.tf, ~line 228)
```hcl
# Source: infra/terraform/snowflake/modules/native_pull/main.tf, SEC_FINANCIAL_DERIVED table_definitions
{ name = "ACCOUNTS_RECEIVABLE", type = "FLOAT" },
{ name = "INVENTORY", type = "FLOAT" },
{ name = "COST_OF_REVENUE", type = "FLOAT" },     # NEW
{ name = "ACCOUNTS_PAYABLE", type = "FLOAT" },    # NEW
{ name = "SELLING_GENERAL_ADMIN_EXPENSE", type = "FLOAT" },
```

### SEC XBRL Frames API coverage measurement (used live in this research session)
```bash
# Source: data.sec.gov public API, no auth beyond a compliant User-Agent
curl -s -A "EdgarTools Platform thepaulananth@gmail.com" \
  "https://data.sec.gov/api/xbrl/frames/us-gaap/CostOfGoodsAndServicesSold/USD/CY2023.json" \
  -o cogs_frame.json
python3 -c "
import json
d = json.load(open('cogs_frame.json'))
print('unique CIKs:', len(set(r['cik'] for r in d['data'])))
"
# Repeat for CostOfRevenue, AccountsPayableCurrent (use .../CY2023Q4I.json for
# balance-sheet "instant" concepts), InventoryNet, NetIncomeLoss (universe proxy).
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A — this is a net-new factor family, not a migration | — | — | — |

**Deprecated/outdated:**
- `CostOfGoodsSold` (without "AndServices") — appears to be a legacy/non-existent us-gaap
  element; use `CostOfGoodsAndServicesSold`. [ASSUMED — inferred from two 404s, not from
  reading the FASB taxonomy documentation directly; low-cost to double check before
  committing to the plan.]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | ~51-63% COGS-family coverage should be treated as "acceptable" (ship DSO/DIO/DPO) rather than "poor" (declare CCC-01 out of scope), because the shortfall is structural (financial/software companies genuinely lack COGS) rather than a tagging-quality problem | Summary, Common Pitfalls | If wrong, the phase ships three factors with a majority-null population for a large filer segment, which may not meet user/consumer expectations for "this factor is broadly usable" — this is the single most consequential open call in this research and should be confirmed via `/gsd-discuss-phase` before planning locks it in |
| A2 | `AccountsPayableTradeCurrent` is a reasonable secondary concept for the `_ACCOUNTS_PAYABLE_CONCEPTS` fallback list | Architecture Patterns, Pattern 1 | Not measured via the Frames API this session (only `AccountsPayableCurrent` was checked); if the real secondary tag is different, the fallback list undercounts AP coverage — low risk, easy to verify with one more Frames API call during planning/execution |
| A3 | `CostOfGoodsSold` (no "AndServices") is a legacy/non-existent us-gaap taxonomy element, not merely "zero filers used it in CY2022/CY2023" | State of the Art, Pattern 1 | If wrong (element exists but is simply rare), excluding it from the fallback list slightly undercounts coverage — low impact given `CostOfGoodsAndServicesSold` already captures the "AndServices" successor naming |
| A4 | Ending-balance-only (not average of beginning+ending) is the right convention for DSO/DIO/DPO in this codebase | Alternatives Considered, Pattern 2 | This is inferred from the ROA/ROE precedent's explicit code comment, not a locked user decision for this specific phase — a reasonable planner/user could still prefer the textbook average-balance formula given CCC factors are commonly presented that way in finance literature |

## Open Questions

1. **What numeric threshold makes coverage "acceptable" per CCC-02?**
   - What we know: No authoritative, documented industry threshold was found via
     WebSearch (searches for XBRL tag-coverage acceptance thresholds returned only
     descriptions of the concepts themselves, not a "X% is the bar" standard). The
     measured numbers (51.5% / 63.3% / 27.5% depending on denominator choice) are real
     but the "is this good enough" judgment is inherently a product decision.
   - What's unclear: Whether the milestone's stakeholder wants a strict "must exceed X%
     of ALL filers" bar (which DIO/DPO alone would likely fail given the 27.5% all-three
     number) or a "must exceed X% of filers where the concept is economically applicable"
     bar (which the 51-63% numbers would likely pass).
   - Recommendation: Surface this explicitly in `/gsd-discuss-phase` before planning locks
     in a go/no-go — do not let the planner silently pick a threshold.

2. **Should DSO ship independently of the DIO/DPO coverage decision?**
   - What we know: DSO needs zero new fields (Pattern 2) and is architecturally
     independent of the `cost_of_revenue`/`accounts_payable` coverage question entirely.
   - What's unclear: Whether CCC-01's wording ("Consumer can query DSO, DIO, and DPO")
     implies all-or-nothing, or whether shipping DSO alone (with DIO/DPO explicitly
     deferred) satisfies the spirit of the requirement while de-risking the coverage-gated
     part.
   - Recommendation: Flag as a planning-time decision; the research supports either path.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Terraform | Physical Snowflake column addition (`native_pull/main.tf`) | Yes | v1.14.8 (windows_amd64) | — |
| Snowflake CLI (`snow`) | Verifying `SHOW COLUMNS`/deploying via `deploy-snowflake-stack.sh` | Yes | 3.16.0 | — |
| dbt-snowflake (via `uv run --with`) | `dbt compile`/`dbt run`/`dbt test` | Assumed available per existing Phase 1/2 pattern (not re-verified this session — no live creds in this research session) | — | — |
| `curl` (for SEC Frames API coverage measurement) | One-off research step, not a shipped dependency | Yes | — | — |

**Missing dependencies with no fallback:** None identified.

**Missing dependencies with fallback:** None — all required tooling for this phase is
already present, same as Phase 1/2.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework (Python) | `pytest` (existing `[tool.pytest.ini_options]` in `pyproject.toml`) |
| Framework (dbt) | dbt unit tests (`unit_tests:` in `_financial_derived_unit_tests.yml` / `_financial_factors_unit_tests.yml`) |
| Config file | `pyproject.toml` (pytest); `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_*_unit_tests.yml` (dbt) |
| Quick run command | `uv run pytest tests/unit/test_fundamentals_modules.py -x` |
| Full suite command | `uv run pytest tests/unit/ -x` ; `uv run --with dbt-snowflake dbt test --select financial_derived financial_factors` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|--------------------|-------------|
| CCC-01 | `cost_of_revenue`/`accounts_payable` extracted from XBRL facts (first-non-null concept preference) | unit | `uv run pytest tests/unit/test_fundamentals_modules.py -x` | Extend existing file, pattern at lines 116-172 |
| CCC-01 | DSO null when `accounts_receivable` or `revenue` is null/zero | dbt unit | `uv run --with dbt-snowflake dbt test --select financial_factors` | Extend `_financial_factors_unit_tests.yml`, same fixture-row pattern as lines 1-90 |
| CCC-01 | DIO/DPO null when `cost_of_revenue` is null (majority case per coverage measurement) | dbt unit | same as above | Same file — add a fixture row with `cost_of_revenue: null` explicitly, since every existing fixture row currently omits this field by omission-equals-null, which won't distinguish "field doesn't exist yet" from "intentionally testing the null path" once the column is added |
| CCC-01 | DSO/DIO/DPO happy-path values match hand-computed expected ratios | dbt unit | same as above | New fixture rows with non-null `cost_of_revenue`/`accounts_payable` |
| CCC-02 | Coverage evidence is documented (not a runtime test — a plan-time deliverable) | manual | N/A — the coverage numbers in this document (or a refreshed live re-measurement at plan/execute time) ARE the CCC-02 evidence | This RESEARCH.md |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_fundamentals_modules.py -x` (fast, no Snowflake creds needed) plus `uv run --with dbt-snowflake dbt parse`
- **Per wave merge:** `uv run --with dbt-snowflake dbt compile --select financial_derived financial_factors`
- **Phase gate:** Live `dbt test --select financial_derived financial_factors` against a
  Snowflake account with the new physical columns present — **this phase inherits the same
  live-test-blocked risk Phase 1/2 are currently stuck on**; do not mark this phase complete
  on compile-only verification without the same explicit "held open" caveat STATE.md already
  uses for Phase 1/2, unless the dev source-sync gap is resolved first

### Wave 0 Gaps
- [ ] `tests/unit/test_fundamentals_modules.py` — no `cost_of_revenue`/`accounts_payable`
      extraction test exists yet (Wave 0 addition, extending the existing file)
- [ ] `_financial_derived_unit_tests.yml` / `_financial_factors_unit_tests.yml` fixture
      rows — none currently populate `cost_of_revenue`/`accounts_payable` (fields don't
      exist yet); every existing fixture row will need these two keys added once the
      columns exist, or DSO/DIO/DPO tests will silently compute against implicit nulls
- [ ] `days_outstanding.sql` macro — does not exist yet (Pattern 2)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | No new auth surface — internal ETL/dbt pipeline change |
| V3 Session Management | No | N/A |
| V4 Access Control | No | Same Snowflake role model (`EDGARTOOLS_DEV_DEPLOYER`) already governs this table; no new grants beyond the existing `SELECT`/table-owner pattern |
| V5 Input Validation | Yes | XBRL fact values are already typed `DOUBLE`/`float` at extraction (`_pick()` returns `float | None`); no new string/injection surface — same pattern as every other `_pick()`-derived field already shipped |
| V6 Cryptography | No | N/A |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Malformed/extreme XBRL values (e.g. a filer XBRL-tagging COGS in the wrong unit, producing an absurd DSO/DIO/DPO) | Tampering (data integrity, not security) | No new mitigation needed beyond what already exists — same class of risk as every other `_pick()`-derived numeric field, not specific to this phase; out of scope for a security review, in scope for a data-quality follow-up if observed post-ship |

## Sources

### Primary (HIGH confidence)
- SEC XBRL Frames API (`data.sec.gov/api/xbrl/frames/us-gaap/...`) — live queries run
  2026-07-01 for `CostOfGoodsAndServicesSold`, `CostOfRevenue`, `CostOfGoodsSold`,
  `CostOfServices`, `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`,
  `GrossProfit`, `NetIncomeLoss`, `AccountsPayableCurrent`, `InventoryNet` (all `CY2023` or
  `CY2023Q4I` frames). Government-authoritative source, confirmed via direct tool call —
  [VERIFIED: SEC XBRL Frames API].
- `edgar_warehouse/parsers/financials_derived.py`, `edgar_warehouse/silver_store.py`,
  `edgar_warehouse/serving/gold_models.py`, `infra/snowflake/dbt/edgartools_gold/models/gold/*.sql`,
  `infra/terraform/snowflake/modules/native_pull/main.tf`,
  `infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql`,
  `tests/unit/test_fundamentals_modules.py` — read directly this session, current repo state.
- `.planning/workstreams/fundamental-factors-v2/STATE.md`, `ROADMAP.md`,
  `REQUIREMENTS.md`, `TODOS.md` — project planning docs, current as of 2026-07-01.

### Secondary (MEDIUM confidence)
- WebSearch: Wall Street Prep, Breaking Into Wall Street, Corporate Finance Institute —
  DSO/DIO/DPO/CCC formula definitions, mutually corroborating.

### Tertiary (LOW confidence)
- WebSearch: `edgartools.io` "XBRL mappings from 32,000 SEC filings" blog — general
  context on XBRL tag standardization/consistency methodology, no directly usable
  cost-of-revenue coverage number (explicitly checked via WebFetch and confirmed absent).
- `CostOfGoodsSold`/`CostOfServices` "legacy element" characterization (Assumptions Log A3)
  — inferred from two 404 responses, not confirmed against FASB taxonomy documentation.

## Metadata

**Confidence breakdown:**
- Coverage measurement: HIGH — live-verified against the authoritative SEC source, not a sample
- "Acceptable threshold" judgment: LOW — no documented industry standard found; flagged as an open decision, not presented as fact
- Multi-layer touchpoint checklist (Pattern 1): HIGH — every file/line read directly this session
- DSO/DIO/DPO formulas: HIGH — multiple corroborating finance-industry sources, standard textbook formulas
- Concept-tag naming for `cost_of_revenue`/`accounts_payable` fallback lists: MEDIUM — primary concepts verified live; secondary/fallback concepts partially assumed (see A2, A3)

**Research date:** 2026-07-01
**Valid until:** ~2026-08-01 (30 days) for the codebase-structure findings; the coverage
numbers are a point-in-time CY2023 snapshot and should be treated as directionally stable
for planning purposes but not re-cited as "current" data indefinitely — a re-measurement
takes one `curl` call per concept and costs nothing to refresh at plan/execute time if the
30-day window has passed.
