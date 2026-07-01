# Roadmap: Fundamental Factors V2 (Growth, Profitability, Returns)

workstream: fundamental-factors-v2
status: active (starting at Phase 2 per suggested build order)
milestone: v1.0 Fundamental Factors V2
updated: 2026-06-29

---

## Milestone Goal

Extend `FINANCIAL_FACTORS` (shipped 2026-06-26, PR #102, accounting-only V1) with growth
(CAGR), profitability, and returns factors — using only dbt gold-layer SQL plus, for one
sub-feature (cash conversion cycle), a silver parser addition that reads fields already
present in the `companyfacts` JSON the existing loader fetches. No new loader, no new SEC
fetch path, no bronze change.

**Activated 2026-06-29.** Execution starts with Phase 2 (Profitability And Returns
Factors) rather than Phase 1, per the "Suggested order" note below — Phase 2 has zero
silver risk and no research gate, since every required input already exists in
`financial_derived`. Phase numbers below are unchanged from the original proposal.

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

## Phases

- [ ] **Phase 1: CAGR Macro And Multi-Year Joins** — add `cagr()` dbt macro, extend
      `financial_factors.sql` with N-year self-joins (3yr, 5yr) for revenue, net income,
      total assets. **2/2 plans executed and code-verified (dbt compile), HELD OPEN
      pending live `dbt test`** — see Phase 1 detail below.

- [ ] **Phase 2: Profitability And Returns Factors** — add gross/operating/net margin,
      ROE, ROA to `financial_factors.sql`; surface existing `roic` column. **2/2 plans
      executed and code-verified (dbt compile), HELD OPEN pending live `dbt test`** —
      see Phase 2 detail below.

- [ ] **Phase 3: Cash Conversion Cycle** — research `cost_of_revenue` XBRL-tag coverage,
      then conditionally parse it and add DSO/DIO/DPO.

**Suggested order:** Phase 2 first (zero risk, immediate value, no research needed),
then Phase 1 (needs sign-change/gap-handling care but no silver risk), then Phase 3
(only phase with real feasibility risk — research gates the build).

---

## Phase Details

### Phase 1: CAGR Macro And Multi-Year Joins

**Goal:** Consumers can query 3-year and 5-year CAGR for revenue, net income, and total
assets per `(cik, fiscal_year)`, computed from existing multi-year history with no new
loader or fetch path.

**Requirements:** GROW-01, GROW-02, GROW-03

**Depends on:** Nothing in this workstream (can run independently of Phase 2/3, but
recommended after Phase 2 — see "Suggested order").

**Plans:** 2/2 plans executed (code + dbt compile verified); phase HELD OPEN pending live `dbt test`

- [x] 01-01-PLAN.md — Create the `cagr()` macro; extend `financial_factors.sql` with 3yr/5yr CAGR CTEs/joins/columns; document in `gold.yml`
- [x] 01-02-PLAN.md — Add dbt unit tests covering GROW-01/02/03 and extend the D-01 quarterly-exclusion test

**Verification status (2026-07-01):** Both plans executed, committed, and merged. `dbt parse`
and `dbt compile --select financial_factors` both succeed against real Snowflake credentials
— SQL/Jinja confirmed valid, compiled SQL confirmed `1.0 / 3` / `1.0 / 5` float division (no
integer-truncation bug). **Live `dbt test --select financial_factors` could not run**: same
pre-existing dev source-schema gap as Phase 2 — `Invalid column name: 'current_assets' in
unit test fixture for 'financial_derived'`. Confirmed unrelated to this phase's code: all
11 test failures, including the pre-existing unmodified `financial_factors_complete_fy_ratios`
and `financial_factors_negative_equity_nulls_roe` cases, hit the identical root cause.
**Decision: phase held open, not marked complete, until live `dbt test` passes against an
environment with a fully-synced source schema** — same precedent as Phase 2. Success
criterion 5 below is NOT yet verified live for real.

**Success criteria:**

1. ✅ New `cagr()` dbt macro added to `infra/snowflake/dbt/edgartools_gold/macros/`, following the same pattern as `yoy_growth()` (case/null guard, no division-by-zero or negative-base errors). (compile-verified)
2. ✅ `financial_factors.sql` extended with N-year self-joins (`fiscal_year - 3`, `fiscal_year - 5`) for revenue, net income, total assets — same join shape as the existing `prior_fy_values` CTE. (compile-verified)
3. ✅ Sign-change handling verified (GROW-02): negative-to-positive or positive-to-negative spans produce null, not a misleading or complex-valued result. (test written, parse-verified; live-test blocked)
4. ✅ Fiscal-year-gap handling verified (GROW-03): a missed `FY` filing in the N-year window produces null, not an incorrectly-spanning calculation. (test written, parse-verified; live-test blocked)
5. ⏸ **NOT YET VERIFIED LIVE** — dbt schema tests cover at least one real multi-year company fixture for each of 3yr and 5yr CAGR; tests are written (`financial_factors_cagr_happy_path`, `financial_factors_cagr_fiscal_year_gap_nulls`, etc.) but have never executed successfully against a real Snowflake target, due to the source-schema gap above.

### Phase 2: Profitability And Returns Factors

**Goal:** Consumers can query gross margin, operating margin, net margin, ROE, ROA, and ROIC from `FINANCIAL_FACTORS` — all computable from columns already present in `financial_derived`, zero parser changes.

**Requirements:** PROF-01, PROF-02, PROF-03

**Depends on:** Nothing in this workstream. Lowest-risk phase — recommended starting point.

**Plans:** 2/2 plans executed (code + dbt compile verified); phase HELD OPEN pending live `dbt test`

- [x] 02-01-PLAN.md — Create the `safe_ratio_signed` dbt macro (ROE negative-equity null guard, D-01)
- [x] 02-02-PLAN.md — Add gross/operating/net margin, ROE, ROA + surface `roic` in `financial_factors.sql`; extend unit tests; document ROIC simplification in `gold.yml`

**Verification status (2026-06-30):** Both plans executed, committed, and merged. `dbt parse`
and `dbt compile --select financial_factors` both succeed against real Snowflake credentials
— SQL/Jinja confirmed valid, all structural acceptance criteria pass. **Live `dbt test
--select financial_factors` could not run**: this dev Snowflake account's deployed
`SEC_FINANCIAL_DERIVED` source table is missing columns (`current_assets`, etc.) that
`financial_derived.sql` already selects — a pre-existing schema-sync gap in this account,
confirmed unrelated to this phase's code (reproduced the identical failure against the
*unmodified* pre-existing test case in isolation; also tried `dbt run --select
financial_derived --full-refresh`, which fails one level deeper because the underlying
source table itself lacks the column). **Decision: phase held open, not marked complete,
until live `dbt test` passes against an environment with a fully-synced source schema** —
see Phase 4 success criterion 4 is NOT yet satisfied for real.

**Success criteria:**

1. ✅ `financial_factors.sql` adds `gross_margin` (`gross_profit / revenue`), `operating_margin` (`ebit / revenue`), `net_margin` (`net_income / revenue`) using the existing `safe_ratio()` macro. (compile-verified)
2. ✅ `financial_factors.sql` adds `return_on_equity` (`net_income / total_equity`, sign-guarded via `safe_ratio_signed`), `return_on_assets` (`net_income / total_assets`) using `safe_ratio()`. (compile-verified)
3. ✅ Existing `financial_derived.roic` column is surfaced in `financial_factors.sql` (not recomputed). (compile-verified)
4. ⏸ **NOT YET VERIFIED LIVE** — dbt schema tests cover representative companies including at least one with negative net income; tests are written (`financial_factors_negative_equity_nulls_roe` etc.) but have never executed successfully against a real Snowflake target, due to the source-schema gap above.
5. ✅ No changes to `financials_derived.py`, `silver_store.py`, or any loader/runtime file — gold-layer SQL only. (confirmed via `git diff --stat`)

### Phase 3: Cash Conversion Cycle

**Goal:** Consumers can query Days Sales Outstanding, Days Inventory Outstanding, and Days Payable Outstanding — or this is explicitly declared out of scope if `cost_of_revenue` XBRL-tag coverage is too poor to be useful.

**Requirements:** CCC-01, CCC-02

**Depends on:** Nothing in this workstream. Run last — the only phase with real feasibility risk (research-gated).

**Plans:** TBD

**Success criteria:**

1. Research spike measures `CostOfRevenue`/`CostOfGoodsAndServicesSold` (and close variant) XBRL concept tag prevalence across a representative filer sample, before any implementation commitment.
2. If coverage is acceptable (threshold defined during the research spike): `cost_of_revenue` is parsed in `financials_derived.py` from the same already-fetched `companyfacts` JSON (no new loader), added to the silver schema, and DSO/DIO/DPO are added to `financial_factors.sql`.
3. If coverage is poor: CCC-01 is formally declared out of scope in `REQUIREMENTS.md` with the measured coverage rate as evidence, per CCC-02 — no low-coverage factor ships.

---

## Out of Scope

See `REQUIREMENTS.md` — market-derived factors (beta, P/E, EV/EBITDA) are explicitly
deferred to the held `model-builder-contract-gaps` Phase 5 charter decision, not this
milestone.
