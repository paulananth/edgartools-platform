---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Fundamental Factors V2 (Growth, Profitability, Returns)
current_phase: 1
current_phase_name: cagr-macro-and-multi-year-joins
status: executing
stopped_at: Phase 1 context gathered (advisor-mode discuss-phase, research-backed
  decisions on quarterly scope, negative-value handling, fiscal-year tolerance).
  Phase 2 remains separately blocked (see Blockers) — not complete, not counted below.
last_updated: "2026-06-30T06:38:36.094Z"
progress:
  total_phases: 3
  completed_phases: 0
  total_plans: 2
  completed_plans: 2
  percent: 0
---

# Project State — fundamental-factors-v2

## Current Position

Phase: 1 (cagr-macro-and-multi-year-joins) — context gathered, ready for research/planning.
Phase 2 (profitability-and-returns-factors) — BLOCKED (verification incomplete), running
  concurrently with Phase 1 since they have no dependency on each other per ROADMAP.md.
Status (Phase 2): Both plans (02-01, 02-02) executed, committed, and merged to main.
  Code-level verification passed (dbt parse, dbt compile --select financial_factors both
  succeed). Live dbt test blocked by a dev-environment source-sync gap — see Blockers
  below. Phase is explicitly NOT marked complete per operator decision (2026-06-30): hold
  open until live dbt test passes somewhere with a synced source schema.
Status (Phase 1): Context gathered via /gsd-discuss-phase 1 (advisor mode). 3 decisions
  locked, 2 research-backed (quarterly-scope rejection, confirmed via web search against
  practitioner consensus). Next step: /gsd-plan-phase 1.

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

## Pending Todos

- Resolve the Phase 2 live-dbt-test blocker above, then mark Phase 2 complete.
- After Phase 2 closes, write the Phase 1 plan (CAGR) — needs sign-change (GROW-02) and
  fiscal-year-gap (GROW-03) handling designed before implementation, not just the join.

- Phase 3 (cash conversion cycle) needs a coverage-research spike on `CostOfRevenue`/
  `CostOfGoodsAndServicesSold` XBRL tag prevalence before any implementation commitment.

## Session Continuity

Last session: 2026-06-30T06:38:36.086Z
Stopped at: Phase 1 context gathered
Resume file: .planning/workstreams/fundamental-factors-v2/phases/01-cagr-macro-and-multi-year-joins/01-CONTEXT.md
