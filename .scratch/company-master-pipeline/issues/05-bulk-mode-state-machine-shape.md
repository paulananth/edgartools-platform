# 05 — Bulk mode state machine shape

Type: grilling
Status: open
Blocked by: 03, 04

## Question

Design the bulk/backfill state machine for the full historical company
universe, in the shape of the platform's existing `load_history` (parallel
bronze/silver Map, then sequential MDM entity resolution, then gold), but
scoped to company-identity data only:

- Parallel Map over the company-identity Bronze/Silver capture mechanism
  ticket 04 settles, at what concurrency?
- `mdm run --entity-type company` + `mdm sync-graph --entity-type company`
  as the MDM/graph stage (pending ticket 03's confirmation these behave
  cleanly company-only).
- Does this need its own gold-refresh step, or does company data feed the
  existing gold tables without a dedicated refresh?
- New state machine name/identity, or a new mode of an existing one?

## Blocked by

03, 04
