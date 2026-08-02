# Decide a Durable Daily-Artifact Resume and Disposition Contract

Type: grilling
Status: resolved
Blocked by: (none — Root-cause Daily Artifact Retry Amplification resolved)

## Question

Ticket 59 established that a correctly fail-closed pair of artifact failures
caused Step Functions to rerun an entire `daily-incremental` task that had
already completed 5,120 of 5,122 selected candidates. Decide the durable
boundary that lets an operator recover safely without making partial success
look complete or repeating hours of successful work.

The decision must specify:

1. A run-bound immutable candidate manifest and per-accession outcome ledger,
   including identity binding (daily-index inputs, application image, and run
   identity) and the statuses which can transition.
2. Which errors may receive a bounded candidate-level retry, which become a
   terminal repair disposition (including immutable-content mismatch), and
   which remain a task-level transient retry.
3. How the state machine resumes only outstanding candidates while preserving
   exactly-once/immutable capture behavior and the canonical silver publication
   boundary.
4. The operator-visible failure evidence and repair/replay procedure, including
   how a repaired candidate is bound back to the original run rather than
   silently accepted by a new selection.
5. Acceptance evidence proving no completed candidate is needlessly refetched,
   no unresolved candidate is omitted, and the six-hour full-chain gate remains
   fail-closed.

This is an operator architecture decision. Do not implement a checkpoint,
weaken the immutable-object guard, or enable the schedule until the decision
and a subsequent implementation/evidence ticket are complete.

## Answer

Accepted 2026-08-01: preserve the original daily-artifact run after an
immutable-content conflict only through an explicit, immutable operator repair
attestation. A fresh selection must not silently absorb the repaired
candidate.

The implementation contract is:

1. The daily-artifact run writes one immutable candidate manifest before
   processing. It binds the run identity, ordered daily-index input identity
   (dates and source checksums), selected canonical accessions, warehouse image
   digest, and relevant parser/configuration versions. It is never regenerated
   for resume.
2. Each candidate emits append-only outcome records keyed by the original run
   and accession. A candidate may move from `pending` to `in_progress` and
   then to `succeeded`, `retryable_failed`, or
   `terminal_repair_required`. `succeeded` is final for that run. A terminal
   repair requires a separate immutable attestation containing the accession,
   conflicting object/checksum evidence, operator identity, reason, and repair
   action; only that evidence may make the candidate eligible for a bounded
   replay under the same manifest.
3. Candidate-scoped transient SEC/network failures consume a bounded
   candidate retry budget and record `retryable_failed` when exhausted.
   Immutable-object/content mismatch and integrity/contract conflicts are
   `terminal_repair_required`; unknown errors fail closed. Task-infrastructure
   transients may retry the task, but its next invocation resumes the same run
   ledger rather than re-running completed candidates.
4. Resume reads the original manifest and ledger, dispatching only pending,
   retryable, or explicitly repair-authorized candidates. It cannot add an
   accession, replace the image/input identity, or treat an unrecorded
   candidate as complete. Canonical silver publication remains downstream and
   occurs only after the complete manifest has a terminal acceptable outcome.
5. Operator evidence must show the manifest identity, per-accession outcomes,
   retry counts and dispositions, the repair attestation when present, and the
   replay result. Acceptance must prove completed candidates were not refetched,
   every manifest candidate has an outcome, repaired work remained bound to the
   original run, and an unresolved candidate prevents the six-hour full-chain
   gate from passing.

This does not weaken immutable capture and does not authorize enabling the
schedule. Implementation and immutable-image production evidence are tracked
separately in ticket 63.
