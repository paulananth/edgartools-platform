Type: grilling
Status: open

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
