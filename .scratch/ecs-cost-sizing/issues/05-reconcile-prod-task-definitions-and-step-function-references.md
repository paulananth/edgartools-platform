# Reconcile Prod Task Definitions and Step Functions References

Type: research
Status: open
Blocked by: 01

## Question

What is the canonical production inventory of active task-definition revisions,
image digests, and Step Functions references after Claude's handoff? Reconcile
the live references to `small:159`, `medium:164`, `large:157`, `mdm-small:137`,
`mdm-medium:138`, and `mdm-large:72` against the intended release candidate.
Identify stale active revisions, orphaned definitions, missing families, and
any state machine that points at a revision or digest outside the canonical
release. Produce a fail-closed retirement and update order.
