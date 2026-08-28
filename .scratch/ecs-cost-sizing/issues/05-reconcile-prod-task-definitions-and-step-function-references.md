# Reconcile Prod Task Definitions and Step Functions References

Type: research
Status: resolved
Blocked by: 01

## Question

What is the canonical production inventory of active task-definition revisions,
image digests, and Step Functions references after Claude's handoff? Reconcile
the live references to `small:159`, `medium:164`, `large:157`, `mdm-small:137`,
`mdm-medium:138`, and `mdm-large:72` against the intended release candidate.
Identify stale active revisions, orphaned definitions, missing families, and
any state machine that points at a revision or digest outside the canonical
release. Produce a fail-closed retirement and update order.

## Answer

The combined live and repository reconciliation is recorded in
[`task-definition-reference-reconciliation-2026-08-09.md`](../research/task-definition-reference-reconciliation-2026-08-09.md).

The stale references named in the question have been superseded. All 26 live
state machines now reference only warehouse `small:166`, `medium:170`, and
`large:163` on digest
`sha256:86f511031d3fdf790f44d4308bb40157d97adbfd2c1b9fdcd4a9755d1e81c625`,
and MDM `small:143`, `medium:143`, and `large:77` on digest
`sha256:9f55a0a7910cb55d1a88190c7642ccfc55b6c4f0210deccb956f6750c3711de2`.
No Step Functions version, alias, running execution, ECS task/service,
Scheduler target, or EventBridge target references another revision.

The live cohort is internally consistent but has no durable Git-tracked
release manifest. Its role images come from separate supported source tags;
the current MDM image includes the latest MDM runtime correction, while the
warehouse image predates the `gold-verify-live` correction on current `main`.
Ordinary deployment registers six new revisions and updates 26 state machines
sequentially, so it can leave a mixed cohort and does not retire old revisions.

Of 472 active revisions, classify six as current-protected, six from the last
captured pre-handoff live cohort as provisionally rollback-protected, and two
object-version-specific silver utility revisions as evidence-protected pending
review. The remaining 458 are provisional retirement candidates, not an
approved deregistration manifest.

Follow-up ticket 21 subsequently rejected the provisional pre-handoff cohort
as known-good after binding its sole deployment-window execution to an exact
failed run. Those six remain temporarily evidence-protected only until ticket
20 persists the replacement control-plane and code-rollback decision; the 458
count is therefore still only a reconciliation check.

Cleanup must first designate a complete rollback cohort, re-read every
reference, generate exact ARN set subtraction, and stop with zero targets on
any drift or incomplete API read. Deregister reviewed ARNs in bounded batches,
verifying protected revisions and all 26 state-machine hashes/references after
each batch. Do not combine deregistration with deployment or permanent
deletion. No AWS resource was changed while resolving this ticket.
