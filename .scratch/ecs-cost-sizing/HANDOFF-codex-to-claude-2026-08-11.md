# Codex to Claude Handoff: ECS Cost and Workflow Audit

Date: 2026-08-11  
Branch: `codex/ecs-cost-sizing`  
Base: `c137ebc4ab440af242da9dd0e69648489b482e68`  
Status: in progress; planning and read-only audit only

## Ownership

Claude owns this ECS cost-sizing and Step Functions audit after this handoff.
Continue in the isolated `edgartools-platform-ecs-cost-sizing` worktree. The
main checkout contains unrelated dirty work and is protected. Preserve every
tracked and untracked planning artifact in this worktree; do not reset, clean,
stage, commit, or overwrite files outside this effort without a new operator
instruction.

Codex will not continue this edit surface unless the operator explicitly hands
it back.

## Goal and priority

Produce an evidence-backed optimization and rollout policy for production ECS
and Step Functions. Correctness/recovery and end-to-end completion speed are
co-primary. Optimize cost only after a workflow proves its output or operator
value. The Wayfinder map is
[`map.md`](map.md).

## Base synchronization

The worktree, local `main`, and `origin/main` are synchronized at
`c137ebc4ab440af242da9dd0e69648489b482e68`. The latest base includes:

- removal of the `bootstrap-batched` and `mdm-seed-from-silver` definitions and
  live state machines;
- the consolidated `mdm-utility` state machine and shared MDM-tail sequencing
  skeleton; and
- an out-of-order graph-generation activation guard.

No branch-only commit exists. All current ECS planning and research changes are
uncommitted. No files are staged.

## Settled decisions

Treat these decisions as constraints unless the operator explicitly reopens
them:

- Keep warehouse and MDM as separate Runtime Variants with distinct images,
  dependencies, IAM/logging identities, task families, and rollback identity.
  Share one `small` / `medium` / `large` CPU-memory tier vocabulary.
- Every production release records one exact immutable warehouse-plus-MDM
  Release Runtime Cohort. Changing either image creates a new cohort and needs
  compatibility and full-chain validation.
- Full-canonical seed work is high-risk and remains warehouse `large` after a
  live 4-GiB OOM. Bounded seed/parse work is a separate class.
- MDM ordinary work remains `medium`. Residual/security work remains
  `mdm-large` until three current-image, representative, non-zero-data medium
  canaries pass correctness, output parity/completeness, recovery,
  idempotency, zero workload retry/failure, memory, speed, and cost gates.
- A cheaper profile may slow p95 end-to-end completion by at most 5% and must
  reduce successful validated-output cost by at least 10%. Any OOM rejects a
  candidate.
- Parallel-safe fan-out targets 8-20 tasks. Correctness-bound loops may remain
  below 8. Admission is bounded by the lower of 32 vCPUs and live quota after a
  20% reserve; a profile change cannot silently consume more capacity.
- Profile, canary, concurrency, failure, rollback, and drift decisions fail
  closed on missing task-bound evidence or identity drift.
- Source policy/configuration must not hardcode usernames, home paths, account
  IDs, regions, secret identifiers, environment-specific names, task ARNs, or
  mutable image references. Exact live identities belong in generated evidence
  and manifests.

The resolved decisions and rationale are in tickets 01-07, 09, 10, and 21
under [`issues/`](issues/). Do not infer current AWS state from their historical
revision counts.

## Current frontier: Ticket 11 remains open

Continue
[`11-inventory-every-production-workflow-and-consumer.md`](issues/11-inventory-every-production-workflow-and-consumer.md).
It intentionally remains `Status: open` for independent and output-level
audit. Do not add it to the map's closed decisions until every closure gate in
the ticket passes.

The August 10 research report is
[`production-workflow-consumers-source-trace-2026-08-10.md`](research/production-workflow-consumers-source-trace-2026-08-10.md).
It is a historical snapshot bound to the previous 26-machine portfolio. Its
execution aggregates, definition hashes, task references, source line
citations, zero-execution list, and consumer classifications require refresh
after the latest consolidation and activation-guard commits.

A read-only 2026-08-11 recheck found 25 live production state machines:

- `bootstrap-batched` is absent;
- `mdm-seed-from-silver` is absent; and
- `mdm-utility` is present.

This recheck only established the name set. It did not refresh definitions,
task/image identities, execution history, output correctness, trigger
provenance, or downstream freshness. It made no AWS mutation.

## Required continuation

1. Refresh the complete 25-machine live inventory against the synchronized
   base: definition revision and canonical hash, every ECS state/command,
   task-definition revision, immutable image digest, triggers, parent
   executions, retries, status, duration, and recency.
   **Complete when:** all 25 live names appear exactly once and no stale
   26-machine facts remain labeled current.
2. Re-trace repository consumers after the MDM utility consolidation and graph
   activation guard. Revalidate every cited source line semantically, not only
   that the line number exists.
   **Complete when:** every output has a proven, inferred, or unknown consumer
   label supported by current source.
3. Resolve trigger provenance for executions whose input omits a trigger
   identity. Distinguish human, script, CI, scheduler, and unknown callers.
   **Complete when:** unknown provenance is explicitly counted and never
   presented as operator-triggered evidence.
4. Bind at least one current-cohort successful execution per workflow class to
   the expected durable output and actual consumer: S3 manifest, Snowflake
   load, dbt freshness, active graph pointer, dashboard object,
   reconciliation row, or operator artifact.
   **Complete when:** a Step Functions `SUCCEEDED` status is never the sole
   proof of usable output.
5. Re-audit graph candidate creation, activation, active-pointer behavior, and
   stale/out-of-order delivery for every MDM composite path under the new guard.
   **Complete when:** each candidate is proven active, intentionally retained,
   discarded, or orphaned.
6. Present the refreshed inventory to the operator for audit. Keep Ticket 11
   open until accepted. Portfolio keep/merge/reshape/retire decisions belong to
   Ticket 14, not this inventory ticket.

## Other open work

- Ticket 12 can independently measure loop and record funnels after its live
  identities are refreshed.
- Ticket 20 remains open and unblocked for designating a protected rollback
  cohort. Ticket 08 cleanup remains blocked by Ticket 20. Do not deregister
  task revisions from provisional counts.
- Tickets 13-19 remain dependency-blocked as recorded in their headers.

## Safety and verification

- Use read-only AWS commands during Ticket 11. Do not deploy, stop tasks,
  update state machines, alter schedules, deregister task definitions, or
  activate graph candidates as part of the inventory.
- Use `uv` for Python execution.
- Preserve the dirty main checkout and this worktree's uncommitted artifacts.
- Re-query live state immediately before any current-state claim.
- Run `git diff --check`, validate every relative link, verify Ticket 11 is
  still open, and confirm the map has no closed Ticket 11 entry before handing
  findings to the operator.

## Start here

```bash
cd ../edgartools-platform-ecs-cost-sizing
git status --short
git rev-parse HEAD main origin/main
sed -n '1,220p' .scratch/ecs-cost-sizing/issues/11-inventory-every-production-workflow-and-consumer.md
sed -n '1,320p' .scratch/ecs-cost-sizing/research/production-workflow-consumers-source-trace-2026-08-10.md
```

Then perform the 25-machine read-only refresh before editing Ticket 11 or its
research report.
