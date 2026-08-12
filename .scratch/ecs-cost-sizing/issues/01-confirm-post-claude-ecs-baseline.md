# Confirm Post-Claude ECS Baseline and Ownership Boundary

Type: task
Status: resolved
Handoff confirmed: 2026-08-09 by operator

## Question

After Claude's work completes, what is the canonical live ECS/Step Functions
inventory for `edgartools-prod`? Reconcile running tasks, active task-definition
families and revisions, state-machine task references, image digests, and
operator changes. Record immutable evidence so sizing decisions do not target
stale or another runtime's work.

## Answer

The canonical post-handoff inventory is recorded in
[`post-handoff-baseline-2026-08-09.md`](../post-handoff-baseline-2026-08-09.md).

Live account `690839588395` has one active production cluster with zero ECS
services, zero running tasks, and zero pending tasks. All 26 production state
machines reference one six-definition cohort: warehouse `small:166`,
`medium:170`, and `large:163` on immutable warehouse digest
`sha256:86f511031d3fdf790f44d4308bb40157d97adbfd2c1b9fdcd4a9755d1e81c625`;
MDM `small:143`, `medium:143`, and `large:77` on immutable MDM digest
`sha256:9f55a0a7910cb55d1a88190c7642ccfc55b6c4f0210deccb956f6750c3711de2`.

The six latest MDM validation tasks used that cohort and exited zero. The live
image source tags are warehouse commit `e244a5712f65` and MDM commit
`1492ec26be2e`, while current `main` is `96daa74e`; later reconciliation must
decide whether subsequent main-only changes are intentionally undeployed.

Eight prod task-definition families contain 472 active revisions. Step
Functions reference six revisions; the remaining 466 include rollback history
and two unreferenced one-off silver inspect/repair definitions. They are
cleanup candidates, not an approved deletion manifest. No live resource was
changed while resolving this ticket.
