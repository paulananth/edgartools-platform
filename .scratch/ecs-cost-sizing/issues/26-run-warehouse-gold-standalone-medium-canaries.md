# Run `warehouse.gold_standalone` Medium Canaries

Type: task
Status: open
Blocked by: none

## Question

Run and record the outcome of two representative `medium`-profile canaries
for `gold_refresh` (the `warehouse.gold_standalone` workload class),
required by Ticket 03's standard two-canary downgrade gate before `large`
can be reconsidered as the operational tier.

Zero canaries have run as of this ticket — the only executions on record
(Ticket 02, reused by Ticket 13) are both the existing `large`-profile
baseline, not a `medium` trial. Given `gold_refresh`'s own measured shape
(Ticket 13: a flat ~$0.005/invocation, ~151s billed, cost and duration
essentially independent of the ~20.87M-row snapshot size it re-exports),
this looks like a low-risk, cheap canary to run relative to the other
pending cohorts in this map — worth scheduling promptly.

Record execution ARNs, task-bound CPU/memory peaks, duration, and pass/fail
against Ticket 03's gate (memory peak ≤85%, memory p95 ≤75%, p95 end-to-end
time regression ≤5%, no correctness/completeness/idempotency regression) on
resolution.
