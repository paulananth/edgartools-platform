# Confirm Post-Claude ECS Baseline and Ownership Boundary

Type: task
Status: open
Blocked by: Claude completion and explicit handoff

## Question

After Claude's work completes, what is the canonical live ECS/Step Functions
inventory for `edgartools-prod`? Reconcile running tasks, active task-definition
families and revisions, state-machine task references, image digests, and
operator changes. Record immutable evidence so sizing decisions do not target
stale or another runtime's work.
