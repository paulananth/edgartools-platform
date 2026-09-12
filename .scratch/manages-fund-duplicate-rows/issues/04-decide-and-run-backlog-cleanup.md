Type: grilling
Status: open
Blocked by: 03

## Question

With the write-time fix confirmed deployed and not regrowing the backlog
(Ticket 03), decide how the existing ~140,907-relationship_id backlog of
duplicate active rows gets resolved:

1. Confirm live whether the backlog is genuinely static now (no new
   duplicates appearing) before designing a cleanup — if the fix somehow
   only partially closed the gap, that changes the cleanup design.
2. Design mechanism: per Ticket 02's Q5 recommendation from this map's
   charting session, this should be a simple dedup pass (per
   `relationship_id`, group rows by identical properties/validity window,
   keep the earliest `instance_id`, mark the rest inactive/superseded) —
   not `mdm-relationship-versioning-gap`'s chain-aware backfill, which
   solves a harder, different problem (genuinely conflicting evidence
   needing priority resolution). Confirm this simpler design still holds
   once Ticket 01's root cause is known — if the duplicates turn out to
   have subtly different properties in some subset (not caught by this
   map's small sample), the simpler dedup may need widening.
3. Rollout scope: all 140,907 at once, or a bounded first pass mirroring
   `mdm-relationship-versioning-gap` Ticket 08's own
   largest-case-first rollout discipline?

Use `/grilling` and `/domain-modeling` per this map's Notes.

## Answer

_(pending)_
