Type: task
Status: open
Blocked by: 08

## Question

Implement and run, against real prod, the chain-aware quarantine backfill
for INSTITUTIONAL_HOLDS (7,966 relationship_ids, per Ticket 08's design):
extend `relationship_quarantine_backfill.py` to walk each relationship_id's
full chronological row history (active + quarantined together) and
correct existing rows in place via UPDATE, rather than the current
pairwise single-conflict check.

Two open sub-decisions Ticket 08 deferred, to resolve during
implementation (not blocking the ticket, but needing a concrete answer
before the walk logic is finalized):

- Chronologically-adjacent same-source rows with genuinely identical
  properties (no conflict by definition) -- dedupe as redundant, or leave
  untouched since they're not incorrect, just redundant?
- Any special handling needed for out-of-business-date-order arrival (a
  late amendment for an earlier period arriving after later periods were
  already processed), beyond the existing `confirmed_chronologically_after`
  guard?

Per this repo's CLAUDE.md hard rule: `/gof-refactor-reviewer` before any
code change, full 3-axis `/code-review` before any commit. Per this map's
own standing preference: real measurements against live prod data, not
estimates -- a dry-run first, then a real run, with before/after
`skipped_multiple_conflicts` counts captured directly from prod.

Does NOT cover MANAGES_FUND (ruled out of scope by Ticket 08 -- a
different root cause, needs its own future map) or the remaining 5
relationship types beyond INSTITUTIONAL_HOLDS (Ticket 08's rollout
sequencing decision -- prove the mechanism here first).

## Answer

