# Decide the GLEIF augmentation boundary

Type: grilling
Status: resolved
Blocked by: 03, 04
Resolution: superseded by 16

## Question

Given the adjudicated 1,000-company evidence, should EdgarTools stop, revise the
matching proof, or proceed to a tracer-bullet implementation, and which exact
GLEIF attributes and relationship semantics belong in that first slice?

## Decision inputs

- Identity coverage, precision, ambiguity, rejection, no-candidate, and replay
  results from Ticket 02.
- Attribute lift, conflict, usefulness, and freshness from Ticket 03.
- Direct/ultimate accounting-parent and reporting-exception coverage from
  Ticket 04.
- Existing fail-closed rules: CIK remains authoritative; no name-only merge;
  source-grained provenance and run identity are mandatory; unmatched and
  unresolved cases remain explicit.

## Done when

The user accepts one explicit outcome: stop, revise with named missing evidence,
or proceed with a bounded implementation surface and measurable production
gates.

## Resolution

The evidence supports a bounded tracer bullet. The exact field, relationship,
backfill, mapping, and release boundary is recorded only in
[Select the first GLEIF MDM delivery slice](16-select-first-delivery-slice.md),
which supersedes this overlapping ticket.
