# Validate the Proposed Rollback Cohort Evidence

Type: research
Status: resolved
Blocked by: 05

## Question

Does the last captured pre-handoff live cohort have enough immutable and
end-to-end success evidence to serve as the protected rollback release, or is a
new bounded rollback rehearsal required before cleanup?

Trace the proposed warehouse `small:159`, `medium:164`, `large:157` and MDM
`small:137`, `medium:138`, `large:72` cohort through ECR source tags, task
definitions, Step Functions execution history, ECS/CloudWatch logs, release
evidence, rollback rehearsal artifacts, and downstream completion gates.
Distinguish successful individual stages from a complete validated workflow.
Report missing evidence explicitly and recommend the minimum additional
rehearsal needed; do not designate the cohort or mutate production.

## Resolution

The exact pre-handoff cohort is rejected as the known-good rollback candidate.
The only production execution in its exact registration window was bound by
preserved Step Functions parameters to warehouse `medium:164` and MDM
`medium:138`; it failed after four `mdm export` attempts because the production
Snowflake MDM mirror object did not exist or was not authorized. It never
validated BatchSilver children, graph completion, or gold completion. Nearby
successful executions used newer images and revisions.

Both proposed images also predate production-observed fixes. Keep the six
revisions temporarily protected as recovery evidence until ticket 20 records
the replacement, but do not label them known-good. Two earlier six-revision
cohorts are canonically identical to the current task definitions and are
better control-plane recovery candidates; they are not independent code
rollback releases. Full evidence and the minimum rehearsal contract are in
[`rollback-cohort-validation-2026-08-09.md`](../research/rollback-cohort-validation-2026-08-09.md).
