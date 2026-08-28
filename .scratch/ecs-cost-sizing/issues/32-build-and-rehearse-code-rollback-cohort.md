# Build and Rehearse a Code Rollback Cohort

Type: task
Status: open
Blocked by: none

## Question

Build a separately attested prior warehouse/MDM image pair and rehearse it
through the bounded full-chain contract (real bronze → silver → MDM →
graph → gold completion, not a partial or synthetic smoke test) before
designating it as this portfolio's Code Rollback cohort.

Raised by [Decide and Capture the Protected Rollback Cohort](23-decide-and-capture-protected-rollback-cohort.md),
which adopted a Configuration Rollback cohort (current six task-definition
revisions plus a canonically identical earlier six-revision cohort) as an
immediate, cheap baseline, but confirmed nothing today satisfies Ticket
04's separate Code Rollback requirement — a genuinely different, validated
prior code cohort. Ticket 24 already ruled out the obvious pre-handoff
candidate: its only in-window execution failed at `mdm export` and never
reached graph or gold completion.

Not a blocker for the rollout in [Ticket 19](19-decide-optimization-rollout-and-acceptance-gates.md) —
genuinely new code risk (as opposed to configuration/wiring risk) is
primarily Wave 4's (machine-profile) concern, and Configuration Rollback's
15-minute restore is already the fast primary safety net there too. This
ticket is real, slower-moving follow-up work: choose a candidate prior
image pair (likely the last known-good digest pair before this session's
current fixes landed), run it through a genuine bounded end-to-end
execution, and record the same evidence class Ticket 23 captured for the
Configuration Rollback cohort (exact ARNs, digests, role source
commits/tags, evidence hashes, operator attestation).
