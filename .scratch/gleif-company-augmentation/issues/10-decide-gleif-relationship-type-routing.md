# Decide GLEIF relationship-type routing

Type: research
Status: resolved
Blocked by: 09

## Question

How should every official GLEIF Level 2 relationship type route into the
platform's MDM domains without changing its meaning?

## Required evidence

- Cover `IS_DIRECTLY_CONSOLIDATED_BY`,
  `IS_ULTIMATELY_CONSOLIDATED_BY`, `IS_INTERNATIONAL_BRANCH_OF`,
  `IS_FUND-MANAGED_BY`, `IS_SUBFUND_OF`, and `IS_FEEDER_TO` separately.
- Map source and target node domains, direction, temporal periods, source-record
  status, registration evidence, and permitted reporting exceptions.
- Compare each type with current MDM relationship definitions and identify
  whether it maps exactly, needs a new typed relationship, or cannot yet be
  published.
- Define behavior when either endpoint has no accepted local MDM identity.
- Never collapse accounting consolidation, branch, fund-management, umbrella,
  or feeder semantics into a generic parent relationship.

## Done when

The specification has one explicit, evidence-backed routing and publication
decision for every GLEIF relationship type, including unsupported endpoints and
retirement behavior.

## Answer

Resolved by [`../research/10-gleif-relationship-routing.md`](../research/10-gleif-relationship-routing.md).

Direct and ultimate accounting consolidation require distinct new Company
relationship types. Branch and the three Fund relationships remain captured
source evidence but publish only through their own future domain consumers.
Existing `HAS_PARENT_COMPANY` and `MANAGES_FUND` have different source,
direction, and semantic contracts and are not reused. Missing local endpoints
block publication without creating generic entities; retirement requires an
explicit change or complete reconciliation, never absence from a partial
delta.
