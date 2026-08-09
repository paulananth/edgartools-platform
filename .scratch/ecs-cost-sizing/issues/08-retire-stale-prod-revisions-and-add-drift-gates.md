# Retire Stale Prod Revisions and Add Drift Gates

Type: grilling
Status: open
Blocked by: 05, 07

## Question

How should deployment retire superseded prod task-definition revisions and
detect Step Functions that still point at stale revisions or image digests?
Define an immutable release manifest, active-reference audit, rollback
protection, atomic update order, and a read-only drift check. The cleanup must
fail closed when a running task, state machine, rollback cohort, or release
candidate reference cannot be resolved.
