# Decide the Optimization Rollout and Acceptance Gates

Type: grilling
Status: open
Blocked by: 04, 13, 14, 15, 16, 17, 18

## Question

In what waves should workflow portfolio, loop, concurrency, telemetry, and
machine-profile changes be implemented and validated, and what evidence blocks
promotion or triggers rollback?

Define an immutable baseline and candidate, one-variable-at-a-time canaries
where practical, representative bounded and full-volume executions, record-
funnel equality, output and integrity checks, OOM/failure/retry thresholds,
duration and freshness tolerances, cost-per-output targets, state-machine
reference audits, and protected rollback revisions. Require a new post-change
execution; never use a redrive of pre-change work as acceptance evidence.
Make end-to-end completion speed a promotion gate alongside correctness: each
candidate must report critical-path and total duration against the immutable
baseline, with an explicit operator-approved exception for any material
slowdown even if AWS cost falls.
