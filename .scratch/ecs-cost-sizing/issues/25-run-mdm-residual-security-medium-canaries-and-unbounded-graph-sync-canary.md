# Run `mdm.residual_security` Medium Canaries and the Unbounded `sync-graph` Canary

Type: task
Status: open
Blocked by: none

## Question

Run and record the outcome of two related, currently-unscheduled MDM canary
cohorts, both raised by [Decide the Machine Profile for Every Workflow Stage](16-decide-machine-profile-per-workflow-stage.md):

1. **`mdm.residual_security`→`mdm-medium` downgrade canaries.** Per Ticket
   09's standing policy, `mdm-large` stays the operational profile for
   residual-holds/security work until three current-image, representative
   `mdm-medium` canaries process non-zero 13F/residual-security data and
   pass the full correctness/parity/completeness/recovery/idempotency/
   zero-failure gate set. Zero of the three have run as of this ticket.
2. **The first unbounded `mdm sync-graph` run** (`--mdm-graph-limit 0`),
   per [Decide the Loop, Batch, and Concurrency Policy](15-decide-loop-batch-and-concurrency-policy.md)'s
   decision to raise the default from 200 for production runs. No execution
   at real (~193K-node) scale exists yet. Ticket 16 decided this first
   canary should run on `mdm-large`, not `mdm-medium`, given the complete
   absence of duration/memory evidence at this scale.

Both are MDM-runtime canaries blocked on the same kind of missing evidence
(a representative, non-zero-data, current-image execution) — grouped here
rather than split, since resolving one is likely to inform scheduling the
other. Record execution ARNs, task-bound CPU/memory peaks, duration, and
pass/fail against each cohort's own gate criteria (Ticket 03/09 for #1,
Ticket 15 for #2) on resolution.
