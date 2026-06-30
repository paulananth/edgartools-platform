---
phase: 02-profitability-and-returns-factors
plan: 02
subsystem: database
tags: [dbt, snowflake, gold-layer, financial-factors]

# Dependency graph
requires:
  - phase: 02-profitability-and-returns-factors plan 01
    provides: "safe_ratio_signed(numerator_col, denominator_col) dbt macro"
provides:
  - "Six new columns on FINANCIAL_FACTORS: gross_margin, operating_margin, net_margin, return_on_equity, return_on_assets, roic"
  - "Unit-test coverage for the negative-equity ROE null guard (D-01) and quarterly (non-FY) factor computation (D-02)"
  - "gold.yml column-level documentation of the ROIC pre-tax simplification (D-03)"
affects: [model-builder-contract-gaps (future valuation/market-derived factors phase), any consumer querying FINANCIAL_FACTORS for profitability ratios]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Profitability/returns ratios computed in financial_factors.sql via safe_ratio()/safe_ratio_signed(), never reusing financial_derived's pre-computed (unguarded) gross_margin/net_margin/roe/roa columns — recomputed fresh to apply the D-01 sign guard."
    - "New single-period factors are never wrapped in `case when fiscal_period = 'FY'` — that gate is reserved for factors needing a prior-year join (YoY growth), not single-period ratios."

key-files:
  created: []
  modified:
    - infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql
    - infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml
    - infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml

key-decisions:
  - "Recomputed margins/ROE/ROA fresh in financial_factors.sql via safe_ratio()/safe_ratio_signed() rather than reusing financial_derived's existing (unguarded) gross_margin/net_margin/roe/roa — those upstream columns lack the D-01 negative-equity sign guard."
  - "roic is the sole pass-through column (l.roic, no macro, no recomputation) per D-03 — it was already computed correctly upstream and needs no sign-sensitivity guard."
  - "Documented the ROIC pre-tax simplification at the gold.yml column level (Option 2 from PATTERNS.md/RESEARCH.md), establishing the first per-ratio-column description precedent in this file, rather than appending a sentence to the model-level description."
  - "Added l.gross_profit and l.ebit to the 'Base accounting inputs' debugging-visibility block for consistency with how every other ratio's raw inputs are already exposed there."

patterns-established:
  - "When an upstream model already computes an unguarded version of a ratio, and downstream needs a stricter guard (sign check), recompute in the downstream model using the established macro convention rather than patching the upstream computation or branching consumer-side."

requirements-completed: [PROF-01, PROF-02, PROF-03]

coverage:
  - id: D1
    description: "gross_margin, operating_margin, and net_margin are queryable on FINANCIAL_FACTORS, computed via safe_ratio() from gross_profit/ebit/net_income over revenue, for every fiscal_period (not FY-gated)."
    requirement: "PROF-01"
    verification:
      - kind: other
        ref: "dbt compile --select financial_factors (confirms safe_ratio() macro expansion and column presence in compiled SQL)"
        status: pass
      - kind: unit
        ref: "_financial_factors_unit_tests.yml#financial_factors_complete_fy_ratios, #financial_factors_quarterly_cross_year_factors_are_null, #financial_factors_negative_equity_nulls_roe"
        status: unknown
    human_judgment: true
    rationale: "dbt unit tests could not execute in this worktree: the financial_derived model's unit-test fixture validation rejects fields (e.g. current_assets) against this dev Snowflake account's live SEC_FINANCIAL_DERIVED source schema — a pre-existing environment data-gap (confirmed to also affect the prior, unmodified financial_factors_complete_fy_ratios test case, not something this plan introduced). dbt parse and dbt compile both succeed, confirming the SQL/Jinja is correct; live unit-test execution needs an environment whose SEC_FINANCIAL_DERIVED source table matches the full financial_derived select list."
  - id: D2
    description: "return_on_equity (safe_ratio_signed, nulls on total_equity <= 0 per D-01) and return_on_assets (safe_ratio, no sign guard) are queryable on FINANCIAL_FACTORS."
    requirement: "PROF-02"
    verification:
      - kind: other
        ref: "dbt compile --select financial_factors (confirms safe_ratio_signed() used only for return_on_equity; safe_ratio() used for return_on_assets with no extra guard)"
        status: pass
      - kind: unit
        ref: "_financial_factors_unit_tests.yml#financial_factors_negative_equity_nulls_roe (return_on_equity: null, return_on_assets: -0.1 on a fixture with net_income=-30, total_equity=-20, total_assets=300)"
        status: unknown
    human_judgment: true
    rationale: "Same environment data-gap as D1 — unit test fixture cannot resolve against this dev account's SEC_FINANCIAL_DERIVED source schema. SQL correctness verified via dbt compile; live execution needs a matching source schema."
  - id: D3
    description: "roic is surfaced on FINANCIAL_FACTORS as a pass-through of financial_derived.roic (no recomputation), and gold.yml documents the pre-tax/no-NOPAT-adjustment simplification at the column level."
    requirement: "PROF-03"
    verification:
      - kind: other
        ref: "grep -Eq 'l\\.roic,' models/gold/financial_factors.sql (plain column ref, no macro/case wrapper) && grep -A4 'name: roic' models/gold/gold.yml | grep -iq 'tax|pre-tax|NOPAT|simplif'"
        status: pass
      - kind: other
        ref: "dbt parse (validates gold.yml YAML schema)"
        status: pass
    human_judgment: false

# Metrics
duration: 26min
completed: 2026-06-30
status: complete
---

# Phase 2 Plan 2: Profitability and Returns Factors Summary

**Added gross_margin, operating_margin, net_margin, return_on_equity, return_on_assets, and a roic pass-through to the FINANCIAL_FACTORS gold model, with unit-test coverage for the negative-equity ROE null guard and quarterly (non-FY) factor computation.**

## Performance

- **Duration:** 26 min
- **Started:** 2026-06-30T05:42:00Z (approx, per branch base)
- **Completed:** 2026-06-30T06:08:13Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- `financial_factors.sql` now selects six new factor columns: `gross_margin`, `operating_margin`, `net_margin` (via `safe_ratio()`), `return_on_equity` (via the new `safe_ratio_signed()` macro, implementing D-01's negative-equity null guard), `return_on_assets` (via `safe_ratio()`, no sign guard per Claude's Discretion), and `roic` (plain pass-through of `financial_derived.roic`, per D-03).
- None of the six new columns is gated on `fiscal_period = 'FY'` — they compute for every reporting period (D-02), unlike the existing `asset_growth_yoy`/`shares_outstanding_yoy_change` factors which need a prior-year join.
- `_financial_factors_unit_tests.yml` extended with a new `financial_factors_negative_equity_nulls_roe` test case and additional assertions on the two existing test cases (FY and quarterly), covering all three Phase 2 requirements (PROF-01/02/03).
- `gold.yml` documents the ROIC pre-tax simplification (no NOPAT tax adjustment, referencing `financials_derived.py` line 279) as a new column-level `description:` under `financial_factors.roic` — the first per-ratio-column doc precedent in this file.
- `l.gross_profit` and `l.ebit` added to the "Base accounting inputs" debugging-visibility block for consistency with how every other ratio's raw inputs are already exposed.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add unit-test cases for the new factors (RED first)** - `7a250b8` (test)
2. **Task 2: Add the six profitability/returns factors to financial_factors.sql (GREEN)** - `7ec2512` (feat)
3. **Task 3: Document the ROIC pre-tax simplification in gold.yml (D-03)** - `21d45cd` (docs)

## Files Created/Modified
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` - Added six new factor columns (gross_margin, operating_margin, net_margin, return_on_equity, return_on_assets, roic) to the final select list; added `l.gross_profit`/`l.ebit` to the base accounting inputs block.
- `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml` - New `financial_factors_negative_equity_nulls_roe` test case; extended `financial_factors_complete_fy_ratios` and `financial_factors_quarterly_cross_year_factors_are_null` with new factor assertions.
- `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` - New `roic` column-level `description:` under the `financial_factors` model documenting the pre-tax ROIC simplification.

## Decisions Made
- Recomputed margins/ROE/ROA fresh using `safe_ratio()`/`safe_ratio_signed()` in `financial_factors.sql` rather than reusing `financial_derived`'s already-computed (unguarded) `gross_margin`/`net_margin`/`roe`/`roa` columns, because those upstream columns lack the D-01 negative-equity sign guard and `financial_factors.sql`'s 100% established convention is "every ratio factor calls a macro in this model."
- Used `safe_ratio_signed` exclusively for `return_on_equity` (the only consumer of that macro in the file) per D-01; left `return_on_assets` on plain `safe_ratio()` per CONTEXT.md's explicit "Claude's Discretion" guidance (negative total_assets is not a realistic balance-sheet state).
- Chose column-level (not model-level) `gold.yml` documentation for the ROIC simplification per RESEARCH.md/PATTERNS.md's explicit recommendation (Option 2) — more semantically precise than a model-level sentence, even though it's the first per-ratio-column doc precedent in this file.
- Computed exact decimal expected values for the unit-test fixtures by hand (e.g. `-10/150 = -0.0666666666666667`) rather than the RESEARCH.md placeholder `-0.0667`, since the live `dbt test` run could not execute in this environment to confirm Snowflake's returned precision (see Issues Encountered) — used Snowflake's standard double-precision division behavior as the basis; flagged for re-verification once unit tests can run end-to-end.

## Deviations from Plan

None - plan executed exactly as written. The `safe_ratio_signed` macro referenced by this plan was already created and committed in Plan 01 (`39992d9`), confirmed present at `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql` before this plan's Task 1 began.

## Issues Encountered

**Unit tests could not execute end-to-end in this worktree (pre-existing environment data-gap, not a defect in this plan's code).** `dbt test --select financial_factors` fails with:

```
Compilation Error in model financial_derived (models\gold\_financial_factors_unit_tests.yml)
Invalid column name: 'current_assets' in unit test fixture for 'financial_derived'.
Accepted columns for 'financial_derived' are: ['cik', 'accession_number', ..., 'gross_margin', 'ebitda_margin', 'net_margin', 'roic', 'roe', 'roa', ...]
```

Root cause: `financial_derived.sql`'s `base` CTE does `select d.* from {{ source("edgartools_source", "SEC_FINANCIAL_DERIVED") }} d`, and dbt validates unit-test fixture columns against this dev Snowflake account's *live* `SEC_FINANCIAL_DERIVED` source table schema, not against the model's `select` list. This dev account's source table is missing columns like `current_assets` that the model and its tests reference.

This is confirmed to be **pre-existing and unrelated to this plan's changes**: running `dbt test --select financial_factors_complete_fy_ratios` in isolation (the existing test case, unmodified in its `current_assets`-bearing rows by this plan beyond adding `gross_profit`/`ebit`/`roic`) produces the identical error. The dbt_verification_note's caveat anticipated exactly this class of issue ("EDGARTOOLS_DEV in this Snowflake account may not have the exact same historical data/schema state as the project's documented dev account").

What WAS verified successfully in this environment:
- `dbt parse` — succeeds after every task's edits (Task 1's YAML, Task 2's SQL, Task 3's YAML), confirming valid dbt project structure and Jinja syntax throughout.
- `dbt compile --select financial_factors` — succeeds, and the compiled SQL output confirms: `safe_ratio_signed` macro correctly expands for `return_on_equity` with the `> 0` guard; `safe_ratio` macro correctly expands for the other four ratios; `l.roic` appears as a plain pass-through with no wrapping case/macro; none of the six new columns has a `fiscal_period = 'FY'` gate.
- All grep-based structural acceptance criteria from the plan (column presence, macro usage, no FY gate, no raw division) pass.

Recommendation for the orchestrator/next wave: re-run `dbt test --select financial_factors --target prod` (or any environment with a `SEC_FINANCIAL_DERIVED` source matching `financial_derived.sql`'s full select list) to close out live unit-test verification and confirm the exact floating-point precision of the hand-computed expected values (`net_margin: 0.1333333333333333`, `return_on_assets: 0.0666666666666667`, `operating_margin: -0.0666666666666667`, etc.) against Snowflake's actual returned numeric type.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Six profitability/returns factors are in place on `financial_factors.sql`, satisfying PROF-01/02/03 at the SQL level (confirmed via `dbt compile`); only live unit-test execution and the dynamic-table `--full-refresh` deploy remain as environment-dependent follow-ups, not blockers to plan completion.
- Per CLAUDE.md's "dbt gold model SQL changes — smoke test convention," deploying this SQL body change to a live `FINANCIAL_FACTORS` dynamic table requires `dbt run --select financial_factors --full-refresh` (a plain `dbt run` is a silent no-op for body-only changes) — this is a phase-verification/handoff concern per the plan's own `<verification>` section, not part of this plan's task scope.
- No blockers for Phase 2 completion at the planning/code level; the orchestrator should confirm live `dbt test` results once merged to an environment with full Snowflake source-schema parity.

---
*Phase: 02-profitability-and-returns-factors*
*Completed: 2026-06-30*

## Self-Check: PASSED

- FOUND: infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql
- FOUND: infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml
- FOUND: infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml
- FOUND: .planning/workstreams/fundamental-factors-v2/phases/02-profitability-and-returns-factors/02-02-SUMMARY.md
- FOUND: commit 7a250b8
- FOUND: commit 7ec2512
- FOUND: commit 21d45cd
