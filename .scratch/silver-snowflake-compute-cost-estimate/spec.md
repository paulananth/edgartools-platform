# Spec: Estimate Snowflake Compute Cost for Native Silver

**Status:** ready-for-agent
**Type:** spec
**Date:** 2026-08-18
**Repo:** edgartools-platform
**Related:** [Silver-on-Snowflake Migration map](../silver-snowflake-migration/map.md) · [08 — Estimate Snowflake Compute Cost for Native Silver](../silver-snowflake-migration/issues/08-estimate-snowflake-compute-cost.md)

## Problem Statement

From the perspective of whoever resolves the next two tickets on the Silver-on-Snowflake
Migration map — [Decide Consumer Cutover Order](../silver-snowflake-migration/issues/09-decide-consumer-cutover-order.md)
and [Decide Cutover/Rollback Mechanics](../silver-snowflake-migration/issues/10-decide-cutover-rollback-mechanics.md)
(blocked by it) — today silver's clean/dedupe/merge transformation logic runs as local
DuckDB CPU inside an already-paid-for ECS Fargate task: effectively free marginal compute.
Moving that transformation onto Snowflake-native dbt `dynamic_table` models (the
architecture Phase 1 of this migration already locked) makes it billed Snowflake warehouse
compute for the first time, and nobody currently has a real number for what that costs.
Without it, Ticket 09/10 would be committing to a migration path — and picking a
`TARGET_LAG` refresh cadence — blind to its ongoing dollar cost, the same kind of blind
spot that already burned real credits once on this platform (CLAUDE.md's manifest-task
1-minute-poll-vs-6-hour-poll incident: roughly 67 credits/week from a warehouse that never
got to suspend).

## Solution

Produce a single, citation-backed research findings document that gives a real, derived
(not guessed) Snowflake credit-cost estimate for running ~30 new silver dbt
`dynamic_table` models, grounded in:

1. Actual `WAREHOUSE_METERING_HISTORY` credit consumption for the existing gold-refresh
   warehouse (the only real analog already running the same `dynamic_table`/`TARGET_LAG`
   mechanism in this account) — used as the per-table cost baseline.
2. Actual row counts for the 30 `EDGARTOOLS_SILVER_LANDING` tables that would feed these
   models, so the baseline is scaled to real data volume rather than assumed to be "small."
3. The Fargate vCPU-second/GB-second compute cost this migration would *eliminate* (today's
   DuckDB transformation work), reusing `ecs-cost-sizing`'s already-gathered rate/
   methodology where available, so the estimate is a genuine net comparison, not just an
   added-cost number in isolation.
4. A small sensitivity table across 2-3 plausible `TARGET_LAG` settings (15 min / 1 hour /
   6 hour), since refresh cadence is the dominant cost lever for dynamic tables and this
   repo has already lived through getting that tradeoff wrong once (the manifest-task
   incident).

Every dollar/credit figure in the deliverable must show the query or command that produced
it — no bare numbers. Where a number genuinely can't be obtained (retention window
exceeded, missing permission), the deliverable says so explicitly rather than estimating
silently.

## User Stories

1. As the agent resolving Decide Consumer Cutover Order, I want a grounded monthly
   credit-cost range for the new silver dynamic tables, so that I can factor real ongoing
   cost into which consumer (MDM or gold-building) migrates first and how urgently.
2. As the agent resolving Decide Cutover/Rollback Mechanics, I want a per-`TARGET_LAG`
   cost table, so that I can bound the dual-write window's cost (that ticket's
   rollback-window question) instead of leaving it open-ended.
3. As the platform operator who already lived through the `SNOWFLAKE_RUN_MANIFEST_TASK`
   credit-consumption incident, I want this migration's refresh-cadence tradeoff
   quantified in dollars before it's chosen, so that this platform doesn't repeat that
   mistake with the new silver layer.
4. As a future engineer auditing this platform's Snowflake spend, I want every cost claim
   in this document traceable to the query that produced it, so that I can verify or
   refresh the estimate later without re-deriving it from scratch.
5. As the agent resolving this ticket, I want the deliverable to explicitly separate "cost
   added" (new Snowflake warehouse compute) from "cost removed" (DuckDB/Fargate compute
   this migration eliminates), so that downstream tickets see the net cost impact, not
   just one side of the ledger.
6. As an engineer reviewing this spec before the underlying research agent's findings
   land, I want the deliverable's required shape and location pinned down now, so that
   whichever agent (the one already dispatched, or a fresh one resuming this spec)
   produces a file conforming to the same contract.

## Implementation Decisions

- **No code changes.** This is a research/analysis deliverable, not a feature build —
  there is no module, interface, or schema to modify.
- **Deliverable location and shape are fixed by the originating ticket's own text**: a
  single Markdown file at
  `.scratch/silver-snowflake-migration/research/compute-cost-estimate-<date>.md`,
  containing (a) real `WAREHOUSE_METERING_HISTORY` figures for the existing gold-refresh
  warehouse over a representative recent window, (b) row counts for all 30
  `EDGARTOOLS_SILVER_LANDING` tables, (c) the Fargate-cost-eliminated comparison, and (d) a
  `TARGET_LAG` sensitivity table (15 min / 1 hour / 6 hour).
- **Primary evidence sources**: `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY` (via
  the `edgartools-prod` SnowCLI connection or equivalent), `INFORMATION_SCHEMA.TABLES` row
  counts for `EDGARTOOLS_SILVER_LANDING`, and — if it exists —
  `.scratch/ecs-cost-sizing/research/workflow-unit-economics-2026-08-12.md` for Fargate
  rate/methodology reuse (do not re-derive Fargate pricing from scratch if that file
  already has it).
- **Relationship to the already-running research agent**: a background agent was already
  dispatched against the originating ticket's text with materially the same instructions
  before this spec existed. This spec formalizes the same deliverable contract; it does
  not need a second, duplicate agent run unless the first one's output fails the
  verification seam below (missing citations, wrong location, missing sensitivity table).
- **This spec does not resolve the originating wayfinder ticket itself** — per this map's
  wayfinder convention, resolving a ticket means posting the answer as a resolution
  comment, setting `Status: resolved`, and appending a one-line gist to the map's
  Decisions-so-far. That happens once a findings file conforming to this spec exists and
  has been reviewed, as a separate step.

## Testing Decisions

- **No unit/integration tests apply** — there is no code under test.
- **Verification seam: citation coverage.** The findings file is "passing" when every
  numeric cost/credit/row-count claim in it is immediately preceded or followed by the
  literal query or command that produced it. A reviewer (human or agent) can check this by
  scanning the document for bare numbers with no adjacent query block — any such number
  fails the seam and the deliverable is incomplete.
- **Verification seam: explicit gap-marking.** Any figure the research agent could not
  obtain (e.g., a metric outside `ACCOUNT_USAGE`'s retention window, or a CLI call that
  failed on permissions) must be stated as "not obtainable — <reason>" rather than
  silently omitted or replaced with a guess. A reviewer checks this by confirming the four
  required sections (metering history, row counts, Fargate-eliminated comparison,
  `TARGET_LAG` table) are each either populated-with-citations or explicitly marked as a
  gap — never silently missing.
- **Prior art**: this repo's `/research` skill convention (background agent, single
  Markdown file, cite every claim's source) is the direct precedent this spec's
  verification approach is modeled on.

## Out of Scope

- Actually deciding the `TARGET_LAG` value or consumer cutover order — that's the
  downstream tickets' job; this spec only produces the cost data they need.
- Building or provisioning any new Snowflake warehouse, dynamic table, or dbt model —
  Phase 1 already specified the model shape; this spec is estimation only.
- Re-deriving Fargate/ECS pricing methodology from scratch if `ecs-cost-sizing`'s
  workflow-unit-economics research already covers it — reuse, don't duplicate.
- Historical or projected cost for the *existing* 20 `EDGARTOOLS_GOLD` dynamic tables
  beyond what's needed as this estimate's baseline — that spend is already happening and
  isn't what's being decided here.

## Further Notes

- The originating ticket's research agent (dispatched moments before this spec was
  written, same session) is running in the background against materially the same brief.
  Once it completes, its output should be checked against this spec's Testing Decisions
  (citation coverage, explicit gap-marking) before the ticket is marked resolved — if it
  already satisfies both, no rework is needed; this spec exists to pin the contract down
  formally, not to imply the prior dispatch was wrong.
- The map's Notes (Silver-on-Snowflake Migration, Phase 2) already record the live
  shard-publish race (`bronze-seed-silver-gold` ETag conflicts) as motivating evidence for
  why this migration matters — this spec doesn't re-litigate that; it only produces the
  cost side of the decision.
- If the existing gold-refresh warehouse turns out to be under-metered (e.g., mostly idle,
  most refreshes triggered by manual `dbt run` rather than steady `TARGET_LAG` ticks), say
  so in the findings — that would itself be a material caveat on how well it works as a
  baseline analog, not just a data point to report flatly.
