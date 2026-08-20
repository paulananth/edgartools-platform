# 02 — Decide the Parallelism Shape (or Decide Not To)

Labels: wayfinder:grilling

**Blocked by:** None — Measure Per-Step Timing and Connection-Pool Ceiling
(ticket 01) resolved 2026-08-19 with real numbers; this ticket is now the
frontier.

**Status:** resolved (2026-08-20)

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

Grilled 2026-08-20, user-confirmed across two rounds. Full decision:

**Build it — yes.** Ticket 01's real numbers make the case narrow but
real: `company` (2h14m) and `security` (1h50m) sum to ~4h and dominate
wall-clock time; `person` (~1m55s), `fund` (53s), `adviser` (31s) are
collectively under 3 minutes and barely move the needle either way.
Overlapping `company` and `security` with each other is where essentially
all of the achievable win lives — roughly halving the ~4h dominant chunk
down to ~max(company, security) ≈ 2h14m.

**New fact found before grilling (not previously known — carried as an
open fact-check from ticket 01):** MDM Postgres's real server-side
`max_connections` is **500**, with only 13 connections active at check
time (confirmed live via a direct read-only `SELECT current_setting(...)`
against the prod DSN). The app-side pool ceiling ticket 01 flagged as a
risk (`pool_size=15` + `max_overflow=15` = 30 per ECS task, via
`MDM_DB_POOL_SIZE`/`MDM_DB_MAX_OVERFLOW` in `edgar_warehouse/mdm/database.py`)
is a tunable client-side setting we chose, not a real external limit.
This materially changed the shape decision below — the connection-pool
risk that made the multi-task shape look safer turned out to be cheap to
just raise.

**Shape: in-process concurrency, not multi-ECS-task Step Functions
`Parallel`.** `run_all()` (`edgar_warehouse/mdm/pipeline.py`) launches all
5 entity-resolution steps as concurrent top-level futures within the
existing single `MdmRun` ECS task, instead of the current
`run_companies -> run_advisers -> run_securities -> run_persons ->
run_funds` sequential chain. Rejected the multi-task/`Parallel`-state
shape: its main advantage (per-step connection-pool isolation) isn't
buying much now that the pool ceiling is known to be a tunable setting
with 500-connection headroom, and in-process avoids a new Step Functions
state shape, a second Fargate task to size/monitor, and native-fan-in
wiring.

**Worker-pool structure:** each of the 5 steps keeps its own existing
bounded `ThreadPoolExecutor` (`company`/`security` at up to 16 workers
each, `person`/`adviser`/`fund` already light or bulk-batched) completely
unchanged — reuses already-proven per-step concurrency code as-is. The 5
steps just run as concurrent top-level futures instead of sequential
calls.

**Fast steps fold into the same batch.** `person`/`adviser`/`fund` join
the same "launch all 5, await all" step rather than staying specially
sequenced around `company`/`security` — they're cheap enough that
special-casing them out adds complexity for no real wall-clock benefit.

**Partial-failure semantics: fail fast.** If any of the 5 concurrent steps
raises, the remaining futures get cancelled and the error propagates
immediately — matches today's implicit sequential behavior (if
`run_companies` raises now, `run_advisers` never starts) and mirrors the
exact cancel-on-exception pattern `run_companies` already uses internally
for its own per-row worker futures.

**`derive_relationships()` (step 6) trigger: unchanged.** It still waits
for all 5 entity-resolution futures to complete before starting — same
effective ordering as today, just with the 5 running concurrently instead
of sequentially before it. The separate, bigger question this map's "Not
yet specified" section flagged (could some relationship types start
before all 5 entity steps finish, since not every type depends on every
entity type) stays deliberately deferred as its own future ticket, not
folded into this decision.

**Concrete pool sizing: `MDM_DB_POOL_SIZE=40` / `MDM_DB_MAX_OVERFLOW=20`**
(60 total per ECS task) — comfortably covers the worst case (~50 combined
worker sessions across all 5 concurrent steps) with real margin, nowhere
near the 500-connection server ceiling.

**Not built here** — per this map's own Mode (decision-spec only, not
overridden into execution), this ticket records the decision; implementing
it (the actual `run_all()` concurrency change, the pool-size env var
update, and updated tests) is follow-on work, not done in this session.
