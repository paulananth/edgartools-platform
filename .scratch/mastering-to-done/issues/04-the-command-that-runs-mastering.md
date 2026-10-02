# The command that runs mastering

Type: grilling (HITL)
Status: open
Blocked by: none

## Question

The adopted mode names (platform validation, 2026-09-30) are:
- **Bookkeeping:** init, migrate, plan, validate, run, status, recover;
- **Change Journal:** init, migrate, plan, validate, deploy, status, recover-delivery.

The enabled CLI has none of plan, validate, deploy or recover-delivery. Today mastering is submitted through `rules run`, and `bookkeeping` has no `run` (review finding 3).

The decision has two parts:
- whether the operator runs mastering with `bookkeeping run --target mdm`, or keeps `rules run`;
- which of the missing modes get built and which get dropped from the skills.
