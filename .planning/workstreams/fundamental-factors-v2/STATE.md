---
gsd_state_version: 1.0
workstream: fundamental-factors-v2
milestone: proposed
milestone_name: Fundamental Factors V2 (Growth, Profitability, Returns)
status: proposed
last_updated: "2026-06-29T00:00:00.000Z"
last_activity: 2026-06-29 -- Research completed confirming the no-new-loader constraint is satisfiable for CAGR and profitability/returns factors via gold-layer SQL alone; cash conversion cycle needs one new silver parser field (cost_of_revenue), feasibility unverified pending Phase 3 research.
progress:
  total_phases: 3
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State — fundamental-factors-v2

## Current Position

Phase: none started — proposed milestone, not yet activated
Status: Research complete (see ROADMAP.md "Research Evidence"); awaiting decision to activate and begin phase planning.

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

- None. Not yet activated — no phase has started.

## Pending Todos

- Decide whether to activate this milestone and begin Phase 1/2 planning.
- Phase 3 (cash conversion cycle) needs a coverage-research spike on `CostOfRevenue`/
  `CostOfGoodsAndServicesSold` XBRL tag prevalence before any implementation commitment.

## Session Continuity

Last session: 2026-06-29T00:00:00.000Z
Stopped at: Research and requirements/roadmap written; no phases planned yet.
Resume file: .planning/workstreams/fundamental-factors-v2/ROADMAP.md
