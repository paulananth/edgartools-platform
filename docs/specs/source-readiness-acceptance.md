# Source readiness: acceptance and invalidated inputs

Status: all four decisions and final shared understanding confirmed by the
operator, 2026-10-17 07:54 ET. These are requirements; recording them does not
implement or enable their behavior.

This extends [the approved source-readiness design](source-readiness.md), merged
in PR #1036. Its settled common-command, automatic declared local dependencies,
frozen consumer versions and waiting-relationship decisions remain in force.

## 1. Local qualification

Verified retained local captures can qualify a source for local processing
before its AWS capture producer is qualified. Require genuine provenance,
complete declared delivery evidence and the normal Rules validation and
registration lifecycle. Missing evidence still blocks processing.

This does not make a declaration in configuration equivalent to qualification.
First check whether actual retained evidence satisfies the existing proof
contract. Do not fabricate an acquisition manifest, reuse synthetic test
authority in shared stores or bypass activation checks. If the existing
contract cannot express legitimate retained-capture evidence, address that as a
separate governed implementation change. This decision does not choose a new
authority schema or enable provider requests.

## 2. Evidence required for readiness

A source earns local readiness only after both proofs:

1. Its common configured path processes the entire available retained delivery
   and verifies the result. Every input record is accounted for, including
   accepted, waiting and rejected outcomes with their reasons and provenance.
   An arbitrary cohort or first-N limit is not full-delivery proof.
2. Repeating the unchanged delivery with the same relevant processing inputs
   selects zero files and starts no new mastering work.

Passing code and fixture tests is implementation evidence; it does not replace
these delivery proofs. The original design's per-source behavior tests for
dependency blocking, waiting links, pinned resume and verified Journal recording
are still required. A waiting relationship is permitted and explicitly counted;
it is not silently dropped to claim completion.

Readiness is scoped to the source, declared capture inventory, configuration and
evidence actually qualified. Full retained capture and full provider history
remain distinct claims. New or changed processing dependencies must trigger the
appropriate Journal selection rather than reusing stale processing evidence.

## 3. Explicit invalidation overrides continued execution

An ordinary newly published version leaves a running or paused consumer on its
original versions, as already agreed. If a pinned rule or reference-data version
is explicitly declared invalid, affected work must stop with an explicit reason.
Preserve verified progress and provenance for repair; do not silently switch
the existing run to a different version.

Repair uses valid approved inputs and the normal processing path. Preserve the
original run evidence and invalidation reason. This requirement does not select
a revocation API, a database schema or an automatic rollback mechanism.

## 4. Already-produced results and dependent work

Results affected by an invalidated input cannot be used as dependencies until
repaired. Identify the affected provenance and dependent work; keep its history,
schedule correction through the normal processing path, and let unrelated
sources continue. Do not delete shared MDM data or invalidate the entire server
as a substitute for identifying affected work.

This addresses use as a processing dependency. It does not introduce an
unreviewed policy for unrelated presentation or publication surfaces.

## Implementation boundary

The mapping-pin slice in Claude's ticket 103 addresses one part of run version
consistency. It does not by itself implement this acceptance/invalidation
contract or establish any source's complete common-command readiness.

Keep source implementation, per-source tests, retained-delivery qualification,
shared data loading and AWS deployment as separate evidence claims. New work
must respect active branch/worktree boundaries, consult the relevant existing
code and use affected behavior tests under five minutes per local run. No
provider request, shared-store write or activation was performed here.

Tracking: [interview checklist](../../.planning/workstreams/source-readiness-acceptance/TICKET.md).
