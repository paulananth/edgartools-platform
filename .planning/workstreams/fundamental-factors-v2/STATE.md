---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Fundamental Factors V2 (Growth, Profitability, Returns)
current_phase: 01
current_phase_name: cagr-macro-and-multi-year-joins
status: executing
stopped_at: Phase 1 both plans (01-01, 01-02) executed, committed, and code-verified
  (dbt parse/compile). Held open pending live dbt test, same as Phase 2 — not complete.
last_updated: "2026-07-01T17:35:00.000Z"
progress:
  total_phases: 3
  completed_phases: 0
  total_plans: 4
  completed_plans: 4
  percent: 33
---

# Project State — fundamental-factors-v2

## Current Position

Phase: 01 (cagr-macro-and-multi-year-joins) — Both plans (01-01, 01-02) executed and
  code-verified. HELD OPEN (not complete) pending live dbt test — see Blockers below.
Phase 2 (profitability-and-returns-factors) — BLOCKED (verification incomplete), running
  concurrently with Phase 1 since they have no dependency on each other per ROADMAP.md.
Status (Phase 2): Both plans (02-01, 02-02) executed, committed, and merged to main.
  Code-level verification passed (dbt parse, dbt compile --select financial_factors both
  succeed). Live dbt test blocked by a dev-environment source-sync gap — see Blockers
  below. Phase is explicitly NOT marked complete per operator decision (2026-06-30): hold
  open until live dbt test passes somewhere with a synced source schema.
Status (Phase 1): Plan 01-01 (2026-07-01) — new `cagr()` macro (strict-positive guard,
  float-division exponent) and 6 new FY-gated CAGR columns in `financial_factors.sql`
  (3yr/5yr revenue, net income, total assets), documented in `gold.yml`. Plan 01-02
  (2026-07-01) — 6 dbt unit tests covering GROW-01/02/03 (happy-path, insufficient-history,
  all 3 negative-endpoint forms, fiscal-year-gap offset-independence) plus extended the
  existing quarterly-exclusion test for D-01. Both plans verified live against dev
  Snowflake at the parse/compile level (`dbt compile --select financial_factors` succeeds;
  compiled SQL confirmed `1.0 / 3` / `1.0 / 5`, no integer-division truncation). Live
  `dbt test --select financial_factors` blocked by the SAME pre-existing dev source-schema
  gap as Phase 2 (see Blockers) — all 11 test failures, including unmodified pre-existing
  tests, share the identical `current_assets` root cause, confirming it is unrelated to
  this phase's code. See 01-01-SUMMARY.md, 01-02-SUMMARY.md. Held open per the same
  operator precedent as Phase 2 until the source-sync gap resolves and a live test run
  confirms green.

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

- **Phase 1 + Phase 2 live dbt test verification — same root cause (2026-06-30, confirmed
  affecting Phase 1 too on 2026-07-01).** `dbt test --select financial_factors`
  fails with `Invalid column name: 'current_assets' in unit test fixture for
  'financial_derived'` — the `snowconn` dev Snowflake account's deployed `EDGARTOOLS_DEV.
  EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED` source table is missing columns that
  `financial_derived.sql` already selects from it. Confirmed pre-existing and unrelated to
  Phase 2's code: reproduced the identical failure against the unmodified pre-existing
  `financial_factors_complete_fy_ratios` test case in isolation. Also attempted
  `dbt run --select financial_derived --full-refresh` to fix it directly — failed one
  level deeper (`invalid identifier 'W.CURRENT_ASSETS'`) because the underlying source
  table itself, not just the dynamic table, lacks the column.

  **Correction (2026-06-30):** an earlier version of this note speculated this was a
  "non-canonical"/unrelated personal Snowflake account, not the project's real dev
  environment. That claim was unsupported and has been retracted — `infra/scripts/
  go-live.sh`'s `default_snow_connection_for_env()` defines `snowconn` as THE canonical
  dev Snowflake CLI connection name (prod uses `edgartools-prod`); the repo never commits
  a literal Snowflake account locator to compare against (always a placeholder like
  `<account_locator.region.cloud>` in `CLAUDE.md`/`docs/runbook.md`), so there was no
  basis for the mismatch claim. `snowconn` pointing at `ixkyqwk-yw12138` is, per the
  project's own tooling, correctly "the dev Snowflake account" — and its
  `EDGARTOOLS_DEV` database holds substantial real data (11,002 companies, 5.7M filings),
  not sandbox/toy data. The real finding stands on its own without that framing: **the
  actual dev Snowflake environment's `SEC_FINANCIAL_DERIVED` source table is stale**,
  missing columns that `financial_derived.sql` (shipped via PR #102, 2026-06-26) already
  expects. This is a genuine native-pull/source-sync gap in dev, not a sandbox quirk.
  (Note: the AWS account mismatch finding from earlier this session is unrelated and
  remains valid — that one IS grounded in literal account IDs `CLAUDE.md` hardcodes
  throughout, e.g. `077127448006` in ECR/S3 bucket names, verified against this machine's
  actual `aws sts get-caller-identity` output.)

  `SEC_FINANCIAL_DERIVED` is a native S3 pull source (per CLAUDE.md's architecture), not
  a dbt model — `dbt run`/`--full-refresh` cannot repopulate it. Resolving this needs the
  Snowflake native-pull pipeline (S3 stage → stream-processor task → source table) to
  re-run against current silver data for this dev account, then `dbt run --select
  financial_derived financial_factors --full-refresh` to redeploy the dynamic tables on
  top of the refreshed source.

  **2026-07-01 confirmation:** ran the full live `dbt test --select financial_factors`
  suite after Phase 1's plan 01-02 landed — 11/11 tests failed, and every failure
  (including the pre-existing, unmodified `financial_factors_complete_fy_ratios` and
  `financial_factors_negative_equity_nulls_roe` cases) hit the identical `current_assets`
  root cause. This is one blocker affecting both phases, not two separate issues —
  resolving the native-pull source-sync gap unblocks live-test verification for both
  Phase 1 and Phase 2 simultaneously.

## Pending Todos

- Resolve the shared Phase 1 + Phase 2 live-dbt-test blocker above (native-pull source-sync
  gap), then run `dbt test --select financial_factors` live and mark both phases complete.
- Phase 3 (cash conversion cycle) needs a coverage-research spike on `CostOfRevenue`/
  `CostOfGoodsAndServicesSold` XBRL tag prevalence before any implementation commitment.

## Session Continuity

Last session: 2026-07-01T17:35:00.000Z
Stopped at: Phase 1 both plans executed and code-verified; held open pending live dbt test
Resume file: .planning/workstreams/fundamental-factors-v2/phases/01-cagr-macro-and-multi-year-joins/01-02-SUMMARY.md
