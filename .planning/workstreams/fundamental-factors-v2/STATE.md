---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Fundamental Factors V2 (Growth, Profitability, Returns)
current_phase: 2
current_phase_name: profitability-and-returns-factors
status: blocked
stopped_at: Phase 2 both plans executed and merged (02-01 safe_ratio_signed macro,
  02-02 six factors + tests + gold.yml docs). dbt parse/compile verified against real
  Snowflake credentials. HELD OPEN — live dbt test cannot run because this dev Snowflake
  account's SEC_FINANCIAL_DERIVED source table predates financial_derived.sql's current
  column set (missing current_assets etc.), confirmed unrelated to this phase's code.
last_updated: "2026-06-30T06:20:00.000Z"
progress:
  total_phases: 3
  completed_phases: 0
  total_plans: 2
  completed_plans: 2
  percent: 0
---

# Project State — fundamental-factors-v2

## Current Position

Phase: 2 (profitability-and-returns-factors) — BLOCKED (verification incomplete)
Status: Both plans (02-01, 02-02) executed, committed, and merged to main. Code-level
  verification passed (dbt parse, dbt compile --select financial_factors both succeed).
  Live dbt test blocked by an environment data-gap in this Snowflake account — see
  Blockers below. Phase is explicitly NOT marked complete per operator decision
  (2026-06-30): hold open until live dbt test passes somewhere with a synced source schema.

## Milestone Context

Extends the V1 accounting-only `FINANCIAL_FACTORS` gold model (shipped 2026-06-26,
PR #102) with CAGR, profitability, and returns factors, under an explicit constraint:
no new loader, no new SEC fetch path, only silver/gold changes.

## Decisions

- Requested constraint ("no additional loaders, only change to silver and snowflake
  gold") is achievable for 2 of 3 proposed factor groups purely via gold-layer dbt SQL
  (CAGR, profitability/returns) because every required input field already exists in
  `financial_derived`. The third group (cash conversion cycle) needs one new silver
  parser field but still no new loader, since it reads from data the existing loader
  already fetches.

- Suggested phase order is profitability/returns first (zero risk) before CAGR
  (needs sign-change/gap-handling care) before cash conversion cycle (feasibility-gated
  on XBRL tag coverage research).

## Blockers

- **Phase 2 live dbt test verification (2026-06-30).** `dbt test --select financial_factors`
  fails with `Invalid column name: 'current_assets' in unit test fixture for
  'financial_derived'` — this dev Snowflake account's deployed `EDGARTOOLS_DEV.
  EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED` source table is missing columns that
  `financial_derived.sql` already selects from it. Confirmed pre-existing and unrelated to
  Phase 2's code: reproduced the identical failure against the unmodified pre-existing
  `financial_factors_complete_fy_ratios` test case in isolation. Also attempted
  `dbt run --select financial_derived --full-refresh` to fix it directly — failed one
  level deeper (`invalid identifier 'W.CURRENT_ASSETS'`) because the underlying source
  table itself, not just the dynamic table, lacks the column. This Snowflake account was
  never kept in sync with the project's schema evolution (it is not the project's
  documented canonical dev/prod account — see go-live workstream's account-mismatch
  finding from earlier this session). Resolving this needs either: (a) access to the
  project's actual documented dev/prod Snowflake account, or (b) a full native-pull +
  silver re-sync of this account's source data.

## Pending Todos

- Resolve the Phase 2 live-dbt-test blocker above, then mark Phase 2 complete.
- After Phase 2 closes, write the Phase 1 plan (CAGR) — needs sign-change (GROW-02) and
  fiscal-year-gap (GROW-03) handling designed before implementation, not just the join.
- Phase 3 (cash conversion cycle) needs a coverage-research spike on `CostOfRevenue`/
  `CostOfGoodsAndServicesSold` XBRL tag prevalence before any implementation commitment.

## Session Continuity

Last session: 2026-06-30T06:20:00.000Z
Stopped at: Phase 2 plans executed and merged; held open pending live dbt test (see Blockers).
Resume file: .planning/workstreams/fundamental-factors-v2/phases/02-profitability-and-returns-factors/02-02-SUMMARY.md
