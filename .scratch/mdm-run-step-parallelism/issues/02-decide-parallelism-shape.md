# 02 — Decide the Parallelism Shape (or Decide Not To)

Labels: wayfinder:grilling

**Blocked by:** 01 — Measure Per-Step Timing and Connection-Pool Ceiling
(need real numbers before choosing a shape, or before declining to build
this at all).

**Status:** blocked

## Question

Given ticket 01's real per-step timing and connection-pool ceiling
findings: is parallelizing MDMPipeline's five entity-resolution steps
against each other actually worth building, and if so, in what shape?

Candidates to weigh (not exhaustive — grill for others):

- **Do nothing.** If one step (e.g. `security`, per the live data point
  already seen while charting this map) dominates wall-clock time, the
  achievable win from overlapping the other four may not justify new
  complexity.
- **In-process concurrency**: one ECS task, `run_all()` launches its five
  steps as concurrent futures/threads instead of sequential calls, sharing
  one Postgres connection pool sized for N steps' combined worker demand.
- **Multi-ECS-task / Step-Functions Parallel state**: `edgartools-prod-mdm-
  run`'s definition changes from a single Task state to a `Parallel` state
  with up to 5 branches (mirroring how this session verified `person`/
  `security` independently), each its own Fargate task with its own pool.
  `derive_relationships()` becomes a separate downstream Task state that
  waits on all branches (Step Functions' native fan-in), rather than a
  step inside one long-running task.
- **Partial parallelism**: only overlap the steps ticket 01's numbers show
  are genuinely fast/independent (e.g. company + adviser + fund), leaving
  the dominant step(s) to run alone, still faster than full sequential but
  without the complexity of a 5-way fan-out.

## Answer

<!-- filled in on resolution -->
