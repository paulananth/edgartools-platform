---
phase: 02-profitability-and-returns-factors
plan: 01
subsystem: database
tags: [dbt, snowflake, jinja-macro, gold-layer]

# Dependency graph
requires: []
provides:
  - "safe_ratio_signed(numerator_col, denominator_col) dbt macro — sign-checked sibling of safe_ratio, nulls the ratio when the denominator is negative, zero, or null"
affects: [02-profitability-and-returns-factors plan 02 (return_on_equity factor)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "safe_ratio_signed: sibling macro pattern — copy safe_ratio.sql structure verbatim, change only the denominator comparison operator (<> 0 to > 0) to encode a sign guard"

key-files:
  created: [infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql]
  modified: []

key-decisions:
  - "Mirrored safe_ratio.sql exactly except the denominator guard operator (<> 0 to > 0), per D-01 (Damodaran ROE treatment) and RESEARCH.md's explicit YAGNI guidance against a parameterized sign-check flag."

patterns-established:
  - "Sign-checked ratio macros: when a denominator's sign is meaningful (e.g. negative equity), add a dedicated sibling macro rather than a flag-driven variant of the existing safe-division macro."

requirements-completed: [PROF-02]

coverage:
  - id: D1
    description: "safe_ratio_signed dbt macro exists, takes (numerator_col, denominator_col), and nulls the ratio unless the denominator is strictly greater than zero"
    requirement: "PROF-02"
    verification:
      - kind: other
        ref: "grep -q 'macro safe_ratio_signed' macros/safe_ratio_signed.sql && grep -q '> 0' macros/safe_ratio_signed.sql && grep -c '<> 0' macros/safe_ratio_signed.sql returns 0"
        status: pass
      - kind: other
        ref: "Jinja2 static parse of macros/safe_ratio_signed.sql (env.parse) — confirms valid {% macro %} block syntax"
        status: pass
      - kind: integration
        ref: "dbt compile --select financial_factors"
        status: unknown
    human_judgment: false

# Metrics
duration: 8min
completed: 2026-06-30
status: complete
---

# Phase 2 Plan 1: safe_ratio_signed Macro Summary

**New `safe_ratio_signed` dbt macro — sign-checked sibling of `safe_ratio` that nulls a ratio when the denominator is negative, zero, or null, implementing D-01's ROE negative-equity null guard.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-06-30T05:49:00Z
- **Completed:** 2026-06-30T05:57:11Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Created `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql`, a new dbt Jinja macro mirroring `safe_ratio.sql` with a single business-logic diff: the denominator guard changed from `<> 0` to `> 0`.
- This is the prerequisite macro for `return_on_equity`'s D-01 negative-equity null guard (Damodaran ROE treatment), to be wired into `financial_factors.sql` in Plan 02.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create the safe_ratio_signed macro** - `39992d9` (feat)

## Files Created/Modified
- `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql` - New macro: `safe_ratio_signed(numerator_col, denominator_col)` returns `numerator_col / denominator_col` only when the denominator is not null and strictly greater than 0; otherwise null (no `else` branch).

## Decisions Made
- Matched `safe_ratio.sql`'s exact structure, 4-space indentation, continuation-line `and` alignment, and trailing blank line — no stylistic deviation.
- Used `> 0` as the single comparison (excludes both zero and negative in one condition) rather than a redundant `and denominator <> 0` clause or a separate `case when denominator < 0` branch, per the plan's explicit instruction and RESEARCH.md's "Don't Hand-Roll" guidance.
- Did not generalize into a parameterized macro with a sign-check boolean flag (YAGNI, per RESEARCH.md and the plan's action block).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

`dbt compile --select financial_factors` could not run to completion in this environment: no `~/.dbt/profiles.yml` exists and no `DBT_SNOWFLAKE_*` credentials are configured in this worktree's environment (dbt's profile resolution failed with `Path 'C:\Users\paula\.dbt' does not exist` before it could reach Jinja parsing). This is an environment/credential limitation, not a defect in the new macro file. As a substitute verification, the macro file was validated for correct Jinja syntax via a static `jinja2.Environment().parse()` call (confirmed `{% macro %}`/`{% endmacro %}` block parses cleanly) and all plan-specified grep-based structural acceptance criteria passed (macro name, `> 0` guard present, zero stray `<> 0`, single `case`/`when`/`then` block, no `else`, no literal column names). The live `dbt compile` integration check is marked `unknown` (not `fail`) in the coverage block above — a downstream wave or the orchestrator's environment (with Snowflake credentials configured) should re-run `dbt compile --select financial_factors` to close this out before Plan 02 proceeds, since Plan 02 needs `safe_ratio_signed` to resolve inside `financial_factors.sql`.

## Next Phase Readiness
- `safe_ratio_signed` macro is ready for Plan 02 to wire into `financial_factors.sql` as `{{ safe_ratio_signed('l.net_income', 'l.total_equity') }} as return_on_equity`.
- Recommend Plan 02's executor (or the orchestrator, if it has Snowflake credentials) confirm `dbt compile --select financial_factors` succeeds with the new macro in place, since this plan could not verify that live in its sandboxed environment.

---
*Phase: 02-profitability-and-returns-factors*
*Completed: 2026-06-30*

## Self-Check: PASSED

- FOUND: infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql
- FOUND: commit 39992d9
