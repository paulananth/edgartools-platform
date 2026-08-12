# Codex to Claude Handoff Addendum: Main Resync

Date: 2026-08-11 20:00 EDT  
Branch: `codex/ecs-cost-sizing`  
Base: `13f5ad92b48a354020b4b4768ffd7e592726f1a6`  
Status: ownership transferred to Claude; Ticket 11 remains open

## Read first

This is the current handoff pointer after resynchronizing with `main`. Read the
[full ECS audit handoff](HANDOFF-codex-to-claude-2026-08-11.md) for settled
decisions, safety boundaries, and Ticket 11 closure gates. This addendum only
records what changed in the newer base and how that changes the continuation.

Claude owns this workstream after this handoff. Continue in the isolated ECS
cost-sizing worktree. Preserve its tracked and untracked artifacts and the
unrelated dirty main checkout. Do not reset, clean, stage, commit, or overwrite
either edit surface without an explicit operator instruction.

## Synchronization result

The isolated branch, local `main`, and `origin/main` are synchronized at
`13f5ad92b48a354020b4b4768ffd7e592726f1a6`, the merge commit for PR #401.
The resync was a fast-forward. One overlapping local planning edit in
`.scratch/ops-cost-control/map.md` was isolated and reapplied; its open ECR
repository-topology question remains intact. No branch-only commit exists and
no file is staged.

PR #401 adds:

- bounded command-result logging for large `raw_writes` payloads;
- durable seven-day retention for ECS, Step Functions, and Container Insights
  CloudWatch log groups; and
- a durable ECR rollback-cohort registry plus fail-closed audit and cleanup
  planning machinery.

The incoming diff does not change the production state-machine portfolio,
state-machine generators, workload-to-profile selectors, or task-definition
CPU/memory tiers. The earlier read-only 25-machine name-set recheck therefore
was not invalidated by this source merge, but it is still a point-in-time
observation rather than proof of current AWS state.

## Continuation impact

1. Continue [Ticket 11](issues/11-inventory-every-production-workflow-and-consumer.md)
   as the frontier. Refresh all live identities and output consumers before
   editing the historical 26-machine report.
   **Complete when:** all current production state machines appear exactly
   once, every current-state claim is query-bound, and the operator has audited
   the refreshed inventory.
2. Capture CloudWatch-derived evidence promptly and record the exact query
   interval. PR #401 enforces a seven-day operational-forensics window, so
   older logs must not be assumed available.
   **Complete when:** every utilization or loop metric identifies its source,
   start/end time, and any missing interval caused by retention.
3. Reuse the new ECR rollback registry and fail-closed reconciliation engine
   for Ticket 20. Do not create a second protected-cohort format or infer
   rollback safety from tag age alone.
   **Complete when:** the proposed warehouse-plus-MDM cohort maps to immutable
   digests, current ECS/workflow references, live tasks, and explicit retained
   rollback evidence through the canonical registry.
4. Keep Ticket 08 cleanup blocked until Ticket 20 is operator-designated and a
   fresh exact-reference audit passes. Do not deregister task definitions or
   delete images from provisional counts.

## Safety boundary

- Ticket 11 remains read-only: no deploys, task stops, state-machine updates,
  schedule changes, task-definition deregistration, image deletion, or graph
  activation.
- Re-query AWS immediately before presenting any fact as current.
- Use `uv` for Python execution.
- Keep usernames, home paths, account IDs, regions, secret identifiers,
  environment-specific identities, ARNs, and mutable image references out of
  source policy and planning configuration.
- A Step Functions `SUCCEEDED` status is not output acceptance; bind executions
  to durable outputs and actual consumers.

## Start here

```bash
cd ../edgartools-platform-ecs-cost-sizing
git status --short --untracked-files=all
git rev-parse HEAD main origin/main
sed -n '1,240p' .scratch/ecs-cost-sizing/HANDOFF-codex-to-claude-2026-08-11.md
sed -n '1,260p' .scratch/ecs-cost-sizing/issues/11-inventory-every-production-workflow-and-consumer.md
```

Then perform the read-only current-production refresh before changing Ticket
11 or its research report.
