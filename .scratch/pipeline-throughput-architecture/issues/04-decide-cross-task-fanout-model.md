Type: grilling
Status: resolved

Blocked by: 01, 02

## Question

Should the execution unit for the largest sequential stages -- notably
`daily-incremental`'s own submissions-bronze-capture phase (10,491 CIKs in
one ECS task, ~0.42s/CIK, ~64 min observed live) and `gold-refresh` (single
task, all ~24 gold tables) -- move from "one large sequential ECS task" to
a fan-out model (Step Functions Distributed Map across more, smaller
parallel tasks, the same primitive `load_history`'s Stage 1 already uses
via `bootstrap-batch` xN), given the SEC rate-limit ceiling ticket 02
establishes and `BOOTSTRAP_BATCH_CONCURRENCY`'s existing 2-5 recommended
range?

Consider explicitly: does `daily-incremental`'s own impacted-CIK universe
(10,491, see [release-readiness ticket
73](../../release-readiness/issues/73-why-daily-incremental-recomputes-impacted-ciks.md))
lend itself to the same Map-state sharding `load_history` already uses, or
does its narrower 7-day-window scope make a different fan-out granularity
more appropriate? Also weigh operational cost: more parallel tasks means
more ECS task-start overhead and more surface for partial-failure/retry
logic, not a free win.

## Done when

A decision -- which stages (if any) should move to a fan-out model, at
what granularity/concurrency, backed by ticket 01's measured breakdown and
ticket 02's rate-limit ceiling.

## Answer (2026-08-03, grilling with user)

**Submissions-bronze-capture: no fan-out.** While grilling this ticket, a
critical finding surfaced first and had to be resolved before this stage's
question made sense: `bootstrap-batch`'s *existing* cross-task fan-out
(`BOOTSTRAP_BATCH_CONCURRENCY=3` in prod) already risks exceeding SEC's
stated 10 req/sec aggregate ceiling (3 tasks x 9 req/sec independent
limiters = up to 27 req/sec) -- live in production today, not hypothetical.
Filed and resolved as its own urgent ticket,
[ticket 06](06-fix-cross-task-sec-rate-limit-compliance.md): fix via the
same intra-task `ThreadPoolExecutor` pattern ticket 03 already decided,
not by tuning concurrency (the per-task limiter is a hardcoded literal, so
the only compliant task-count-only fix would be
`BOOTSTRAP_BATCH_CONCURRENCY=1`, which eliminates the fan-out entirely).
Ticket 06 further found `daily-incremental`'s own submissions-bronze-capture
loop and `bootstrap-batch`'s SEC-fetch loop are **the same shared function**
(`_capture_submission_bronze_snapshot`, also used by `bootstrap`,
`bootstrap_full`, `targeted_resync`) -- so this ticket's own
submissions-bronze-capture question and ticket 06's compliance fix resolve
together: one intra-task-concurrency fix to that shared function, no
fan-out needed for any of the five callers.

**Gold-refresh: deferred, not decided.** Unlike submissions-bronze-capture,
`gold-refresh` makes zero SEC calls, so the rate-limit compliance concern
doesn't apply -- but ticket 01 never profiled `gold-refresh` (it profiled
`daily-incremental`, the pipeline running live at the time), and there's a
real tradeoff (N tasks means N copies of the 1GB+ canonical silver file)
that can't be judged without per-table timing data. Rather than guess,
split into [ticket 07](07-profile-gold-refresh-stage-breakdown.md) (profile
first, unblocked) and [ticket 08](08-decide-gold-refresh-fanout.md) (decide,
blocked by 07) -- keeping this map's standing rule that every decision is
backed by real measured data, not structural reasoning alone.

**New broader finding, also split off:** fixing each command's *own*
internal concurrency (ticket 03, ticket 06) only guarantees compliance in
isolation -- nothing today prevents two *different* SEC-fetching commands
(e.g. a manual `bootstrap-batch` overlapping a scheduled `daily-incremental`)
from running concurrently and jointly exceeding SEC's ceiling. No
cross-command lock exists (`pipeline_run_lease` is generic but only one
lease name, `daily_identity_refresh`, is actually registered anywhere).
Filed as [ticket 09](09-decide-cross-command-sec-fetch-mutual-exclusion.md)
-- a genuine, separate architecture decision (real throughput-vs-safety
tradeoffs), not a mechanical fix.
