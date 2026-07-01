---
phase: 01-cagr-macro-and-multi-year-joins
plan: 01
subsystem: database
tags: [dbt, snowflake, gold, cagr, growth-factors]

requires:
  - phase: 02-profitability-and-returns-factors
    provides: safe_ratio_signed.sql sign-guard pattern precedent (Damodaran ROE null-guard reasoning reused for CAGR's strict-positive guard)
provides:
  - cagr() dbt macro (strict-positive dual-operand guard, float-division exponent)
  - financial_factors.sql extended with prior_fy_values_3y/_5y CTEs, two exact-offset joins, 6 new FY-gated CAGR columns
  - gold.yml column-level documentation for all 6 CAGR columns citing D-01/D-02/D-03
affects: [01-02-unit-tests]

tech-stack:
  added: []
  patterns:
    - "cagr(current_col, prior_col, years) macro: case/strict-positive-guard/power(x, 1.0/years)-1 shape, mirrors safe_ratio_signed.sql"
    - "N-year self-join: dedicated CTE per offset (prior_fy_values_3y, prior_fy_values_5y), exact equi-join on fiscal_year - N, no between/tolerance"

key-files:
  created:
    - infra/snowflake/dbt/edgartools_gold/macros/cagr.sql
  modified:
    - infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql
    - infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml

key-decisions:
  - "Guard requires BOTH operands strictly > 0 (not a same-sign check) — a negative-to-negative span is mathematically computable but D-02 prohibits it as misleading for a still-unprofitable company."
  - "Exponent rendered as 1.0 / {{ years }} (float division) — bare 1 / years truncates to 0 in Snowflake integer division, silently zeroing every CAGR via power(x, 0) = 1."
  - "Exact equi-join (= fiscal_year - N) only, never between/tolerance — a fiscal-year gap must null via left join, not fuzzy-match to a nearby year (D-03/GROW-03)."
  - "Two new CTEs added rather than unifying with the existing prior_fy_values (1yr) CTE — kept the phase change conservative per CONTEXT.md; unification flagged in RESEARCH.md as a future option, not taken here."

patterns-established:
  - "N-year CAGR: dedicated CTE + macro call wrapped in a FY-gating case, matching the asset_growth_yoy precedent — FY-gating and macro-internal positivity guard are two distinct, both-required layers."

requirements-completed: [GROW-01, GROW-02, GROW-03]

coverage:
  - id: D1
    description: "cagr() macro computes (current/prior)^(1/years)-1, guards both operands strictly positive, uses float-division exponent"
    requirement: GROW-02
    verification:
      - kind: unit
        ref: "dbt parse (macro registers, no Jinja error); grep '> 0' macros/cagr.sql count=2; grep '1.0 /' present; grep 'sign(' absent"
        status: pass
    human_judgment: false
  - id: D2
    description: "financial_factors.sql adds 2 exact-offset CTEs, 2 joins, 6 FY-gated CAGR columns for revenue/net_income/total_assets at 3yr and 5yr"
    requirement: GROW-01
    verification:
      - kind: unit
        ref: "dbt compile --select financial_factors (live Snowflake, dev target) succeeds; compiled SQL contains 1.0 / 3 and 1.0 / 5, no bare 1 / 3 or 1 / 5"
        status: pass
    human_judgment: false
  - id: D3
    description: "Exact fiscal_year - N equi-join with no between/tolerance — a fiscal-year gap nulls via left join rather than fuzzy-matching"
    requirement: GROW-03
    verification:
      - kind: unit
        ref: "grep -c 'fiscal_year - 3' and 'fiscal_year - 5' >= 1 each; grep -i 'between' financial_factors.sql returns nothing"
        status: pass
    human_judgment: false
  - id: D4
    description: "All 6 CAGR columns documented in gold.yml citing D-01 (FY-only), D-02 (strict-positive null), D-03/GROW-03 (exact-N-year-match)"
    requirement: GROW-03
    verification:
      - kind: unit
        ref: "dbt parse succeeds; Python yaml check confirms all 6 column names present under financial_factors.columns; grep -c 'D-03' gold.yml >= 6"
        status: pass
    human_judgment: false

duration: unknown (executor process was interrupted mid-run; resumed and closed out in orchestrator session)
completed: 2026-07-01
status: complete
---

# Phase 01-01: CAGR Macro And Multi-Year Joins (Implementation) Summary

**New `cagr()` dbt macro plus 3yr/5yr revenue/net-income/total-assets CAGR columns added to `financial_factors.sql`, with strict-positive null guards and exact fiscal-year-offset joins.**

## Performance

- **Started:** 2026-07-01 (exact start time lost — executor process exited mid-run before returning)
- **Completed:** 2026-07-01T17:00Z (verification + commit completed in orchestrator session after resume)
- **Tasks:** 3 completed
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- `cagr()` macro: `(current/prior)^(1/years) - 1`, guarded so both operands must be strictly positive (not merely same-sign), using float-division exponent `1.0 / years` to avoid Snowflake integer-division truncation.
- `financial_factors.sql` extended with `prior_fy_values_3y` / `prior_fy_values_5y` CTEs (byte-for-byte structural copy of the existing `prior_fy_values` CTE), two new exact-offset left joins (`= fiscal_year - 3`, `= fiscal_year - 5`), and 6 new FY-gated columns: `revenue_cagr_3y`, `net_income_cagr_3y`, `total_assets_cagr_3y`, `revenue_cagr_5y`, `net_income_cagr_5y`, `total_assets_cagr_5y`.
- `gold.yml` documents all 6 new columns, each citing D-01 (FY-only scope), D-02 (strict-positivity null guard), and D-03/GROW-03 (exact-N-year-match requirement).

## Task Commits

Each task was committed atomically:

1. **Task 1: Create the cagr() dbt macro** - `0e4d160` (feat)
2. **Task 2: Extend financial_factors.sql with 3yr/5yr CAGR CTEs, joins, and columns** - `5c86f05` (feat)
3. **Task 3: Document the 6 new CAGR columns in gold.yml** - `adecb3e` (docs)

## Files Created/Modified
- `infra/snowflake/dbt/edgartools_gold/macros/cagr.sql` - New macro: strict-positive guard, float-division CAGR formula
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` - 2 new CTEs, 2 new joins, 6 new FY-gated columns
- `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` - 6 new column descriptions

## Decisions Made
- Both operands must be strictly `> 0` (D-02) — deliberately broader than a same-sign check, since a negative-to-negative span is mathematically computable but misleading for a still-unprofitable company.
- Exponent uses literal `1.0` numerator to force float division — the single highest-risk silent-bug vector identified in RESEARCH.md (Pitfall 1).
- Kept the two new CTEs separate from the existing 1-year `prior_fy_values` CTE rather than unifying all three offsets into one parameterized CTE — conservative scope per CONTEXT.md; unification is a flagged-but-deferred option in RESEARCH.md Open Question 1.

## Deviations from Plan

### Auto-fixed Issues

**1. [Process interruption] Executor process exited mid-Task-3; resumed and closed out from orchestrator session**
- **Found during:** Wave 1 dispatch — the spawned `gsd-executor` subagent had committed Tasks 1 and 2 (`0e4d160`, `5c86f05`) and finished editing `gold.yml` for Task 3, but the Claude Code process exited before running `git commit` for Task 3 or writing this SUMMARY.md.
- **Issue:** Task 3's `gold.yml` edit existed as an uncommitted working-tree diff; `01-01-PLAN.md`/`01-02-PLAN.md`/`01-PATTERNS.md` and `.planning/workstreams/fundamental-factors-v2/config.json` were untracked; `STATE.md`/`ROADMAP.md` had partial, non-canonical manual edits from the interrupted run (a hand-written `- [ ] 01-01-PLAN.md` checklist in ROADMAP.md rather than the `roadmap update-plan-progress` tool's canonical format).
- **Fix:** Re-verified all 3 tasks' acceptance criteria against the actual file state (all passed — Task 1's macro correctly guards and float-divides; Task 2's `dbt compile --select financial_factors` succeeds against live dev Snowflake with confirmed `1.0 / 3` / `1.0 / 5` in compiled SQL; Task 3's `gold.yml` is valid YAML with all 6 columns and 6+ `D-03` citations). Committed the `gold.yml` diff as Task 3 (`adecb3e`). Reverted the non-canonical manual `ROADMAP.md` edit and re-ran `gsd-tools roadmap update-plan-progress` after this SUMMARY.md existed, so the canonical `X/2 plans executed` format is used instead.
- **Files modified:** `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` (committed as-is, no changes to its content — the interrupted executor's edit was already correct).
- **Verification:** `dbt parse`, `dbt compile --select financial_factors` (live dev Snowflake), and all plan-specified grep/YAML assertions re-run and confirmed passing after resume.
- **Committed in:** `adecb3e` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (process-interruption recovery; no code changes beyond completing the already-correct in-progress edit)
**Impact on plan:** No scope creep — all task content matches the plan exactly. The only orchestrator-side work was verifying, committing, and reconciling shared-file state after an unplanned process interruption.

## Issues Encountered
- `dbt compile`/`dbt parse` require `DBT_SNOWFLAKE_ACCOUNT`/`DBT_SNOWFLAKE_USER`/`DBT_SNOWFLAKE_PASSWORD` env vars with no defaults (per `~/.dbt/profiles.yml`); these were not set in the resumed shell session. Resolved by sourcing account/user from the `snowconn` SnowCLI connection (`~/.snowflake/config.toml`) and setting `DBT_SNOWFLAKE_WAREHOUSE=EDGARTOOLS_DEV_REFRESH_WH` / `DBT_SNOWFLAKE_ROLE=EDGARTOOLS_DEV_DEPLOYER` for the verification run only (not persisted to any file).
- Task 1's own literal verify command (`grep -E "[^.]1 */ *\{\{ *years"` expected to find nothing) produces a false-positive match against the macro's own explanatory head-comment ("Float exponent: uses 1.0 / {{ years }} (not 1 / {{ years }})"), which explains the anti-pattern in prose. This is a plan/verify-command precision gap, not an implementation defect — manually confirmed the macro body itself (not the comment) uses only `1.0 / {{ years }}`. Not a plan-code deviation; noted here as a residual reference for whoever tightens the verify regex.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Plan 01-02 (Wave 2, unit-test coverage for GROW-01/02/03) depends on the 6 columns and `cagr()` macro this plan created — both are now committed and verified against live dev Snowflake. Ready to execute 01-02.

Known environment risk carried forward (not a blocker for this plan, per its own `<environment_risk>` note): live `dbt test` may still fail at the `financial_derived` source-schema level due to the pre-existing dev `SEC_FINANCIAL_DERIVED` source-sync gap (STATE.md Blockers) — this plan's own verification bar (`dbt parse` + `dbt compile --select financial_factors`) was achieved and is unaffected, since `revenue`/`net_income`/`total_assets` are in the original `CREATE TABLE` block, not the stale `ALTER TABLE ADD COLUMN` set.

---
*Phase: 01-cagr-macro-and-multi-year-joins*
*Completed: 2026-07-01*
