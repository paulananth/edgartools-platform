# Confirm `generation_build` Was Not Abandoned

Type: task
Status: open
Blocked by: none

## Question

Was `generation_build` deliberately left dormant after its one-ever
execution (2026-07-22, per Ticket 12/13), or is its near-total absence of
use (21 days, zero repeats) evidence of an abandoned capability nobody
noticed had gone quiet?

Raised by [Decide the Production Workflow Portfolio](14-decide-the-production-workflow-portfolio.md),
which decided to keep this workflow on capability grounds — it is the only
machine in the portfolio that can produce a new graph generation at all,
and retiring it on a zero-recent-execution technicality would be an
accidental capability loss. That reasoning is sound regardless of the
answer here, but an owner's explicit confirmation is still needed before
this is treated as fully settled, and before
[Decide the Loop, Batch, and Concurrency Policy](15-decide-loop-batch-and-concurrency-policy.md)'s
deferred `BuildPartitions` `MaxConcurrency` sizing work is worth doing in
earnest.
