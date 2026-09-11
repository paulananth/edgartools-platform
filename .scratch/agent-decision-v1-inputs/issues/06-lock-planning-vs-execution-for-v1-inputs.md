# Lock planning versus execution for v1 inputs

Type: grilling
Status: open
Blocked by: none

## Question

Does this map stay planning-only (decision-complete plan, then hand off),
or does a Notes override carry execution — for example running the
financial-factors `--full-refresh`, or any identity backfill tickets 04 /
05 later specify?

Standing default for wayfinder is planning only. Sibling Agent Decision
Contract is also planning-only. Fundamentals-daily and change-propagation
are the precedent for carrying implementation when the destination is a
shipped change.

Decide:

1. Planning-only until the way is clear, then stop.
2. Planning plus a bounded operator task (refresh / verify columns) on
   this map.
3. Full execution map (refresh, any identity work, live verify) before
   Agent Decision Contract implements contract objects.
