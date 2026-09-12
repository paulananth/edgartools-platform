Type: grilling
Status: open
Blocked by: 01

**No longer blocked by 03** — [Ticket 02](02-decide-write-time-fix-mechanism.md)
decided the backlog cleanup doesn't need to wait on Ticket 03's monitoring
check; Ticket 01 already confirmed the backlog is static (0 new duplicate
groups in 3+ weeks of continued writes).

## Question

Decide how the existing ~140,907-relationship_id backlog of duplicate
active rows gets resolved:

1. ~~Confirm live whether the backlog is genuinely static now~~ — already
   confirmed by Ticket 01: 0 new duplicate groups across 4,116 new
   MANAGES_FUND rows written in the 3+ weeks since the CRD-batching
   refactor.
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
