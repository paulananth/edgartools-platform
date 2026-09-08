Type: task
Status: open

## Question

`mdm_entity_attribute_stage` has no pruning anywhere in this codebase (already
flagged in `SecurityResolver.resolve_one`'s own 2026-08-21 comment,
`edgar_warehouse/mdm/resolvers/security.py:71-88`). A handful of heavily-refiled
securities have accumulated thousands of duplicate candidate rows across every
past `mdm mastering` run, and `run_survivorship_for_entity`'s SELECT re-scans
that entire, ever-growing candidate set every single time the entity is
touched (even by a single new row). Should this be pruned/bounded, and how?

## Context

Spawned while directly measuring live production data during
[Ticket 04](04-run-grouped-concurrent-single-end-of-group-commit.md)'s
verification run (`mdm-mastering-groupcommit-verify-1788827772`,
2026-09-08), after the user asked whether Postgres CPU or concurrency
explained the run's slow, bursty write pattern.

Live evidence gathered directly (not estimated):

- **Postgres CPU: idle.** Zero active queries at every point checked during
  the run; all ~18 worker sessions sat `idle` (last statement `COMMIT`).
  `pg_locks` showed zero blocked queries throughout.
- **ECS task CPU: ~20-35% of the allocated 1 vCPU** (`edgartools-prod-mdm-medium`,
  1024 CPU units), one brief startup spike to ~99%, otherwise well under
  capacity the whole run.
- **`pg_stat_statements` (extension 1.10, live in prod)** shows the exact
  `SELECT mdm_entity_attribute_stage...` query `run_survivorship_for_entity`
  issues has a **mean execution time of 0.15-0.51ms** across millions of
  calls, but a **max execution time of 611-619ms** — a long tail two to
  three orders of magnitude past the mean, on the identical query shape.
- **Confirmed the long tail's source directly:** total (all-history, not
  just this run) accumulated stage-row counts per entity/field:
  - `91c364bb-0ee3-4e06-9ae9-648c4747b054`: 5,048
  - `a31e1bdf-523e-4911-bc5b-413e8103376c`: 2,753 (the exact entity from
    Ticket 04's own investigation)
  - `9ce0c694-dc23-4fed-9aa0-2b51c41aa135`: 1,888
  - `6a237335-ff0a-488a-91ba-418dbef07796`: 1,025
  - `1e9ebe91-a507-4ce8-b8dd-40b1f01fa77b`: 829
- **Confirmed this map's own already-documented flat cross-region round-trip
  cost is real and additive, not the sole explanation:** a direct connection
  test against the live `EDGARTOOLS_PROD_MDM` endpoint measured 20 trivial
  `SELECT 1` round trips at 80-198ms each (median ~102ms) — consistent with
  this map's own Notes section (~68ms flat round trip, us-west-2 vs.
  us-east-1 cross-region). This flat cost applies to *every* row regardless
  of candidate-set size; the *additional* multi-hundred-ms cost specifically
  on hyper-refiled entities is the candidate-accumulation problem this
  ticket is about, layered on top of (not instead of) the already-accepted,
  already-out-of-scope round-trip latency.

**Why this isn't Ticket 04's concern:** Ticket 04 fixes commit
*durability/visibility* (how much progress is lost if an oversized group's
processing is interrupted) — it does not, and was never meant to, address
*processing speed*. A group that is slow because a handful of its rows hit
an unusually expensive SELECT scan is unaffected by commit cadence; it's
still slow, just now with bounded data-loss risk instead of unbounded.

**Why concurrency reduction (the user's other live question this session)
doesn't apply here either:** no CPU or lock contention evidence exists at
any level checked (Postgres, ECS). The bottleneck is per-statement latency
on a specific, identifiable minority of entities, not resource contention
concurrency tuning would relieve.

## Answer

Not yet resolved — this ticket documents the finding. Candidate directions,
not yet evaluated against each other:

- Prune `mdm_entity_attribute_stage` to keep only the most-recent N candidate
  rows per `(entity_id, field_name)`, or only rows within some retention
  window, since `run_survivorship_for_entity` only ever needs the current
  set of live candidates to pick a winner -- historical duplicate rows from
  long-superseded runs serve no read purpose once `_skip_if_unchanged`
  already prevents re-staging an unchanged row.
- Investigate whether `_skip_if_unchanged`'s existing fast path (Ticket 03)
  should have already prevented most of this accumulation for entities that
  are genuinely unchanged run-over-run, and if not, why these specific
  entities keep bypassing it (e.g. genuinely distinct ownership-transaction
  `source_id`s each run, which Ticket 03's own design deliberately doesn't
  collapse -- would need to check whether that's the actual mechanism here).
- Whether a bounded/batched read in `run_survivorship_for_entity` itself
  (e.g. only reading the top-K most relevant candidates instead of the full
  set) is safe without changing survivorship's winner-selection correctness.

## Not yet specified / open follow-up

- Whether the round-trip-latency figure measured this session (80-198ms
  from this session's own network path) matches the real ECS-task-to-Postgres
  path, or whether it should be re-measured from inside a running ECS task
  for a more authoritative number matching this map's own "real measurements"
  standing preference. Not done in this pass -- the existing ~68ms figure
  already on this map's Notes section, gathered independently, is closer to
  authoritative than this session's opportunistic measurement.
