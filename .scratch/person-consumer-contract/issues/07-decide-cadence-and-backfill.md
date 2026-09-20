# Decide Person processing cadence and the initial backfill scope

Type: grilling
Status: open
Blocked by: 05-decide-person-relationships.md

## Question

Ownership filings already flow through `daily_incremental`; proxy and 8-K
through the fundamentals stages. Does the Person consumer run per
`daily_incremental` execution on impacted issuers only, with a periodic
full reconciliation like GLEIF's monthly one? And is the initial backfill
"every reporting owner in silver" (deterministic CIK binds only), or a
bounded cohort first, the way Company's first slice was bounded?
