Type: grilling
Status: open
Blocked by: 01

**Spawned by:** the map's own charting session — the map's two "Not yet specified" fog items, both requiring Ticket 01's evidence before they can be decided.

## Question

Using Ticket 01's per-type findings (actual filtering shape, real data-volume risk, available source-table timestamp/versioning columns):

1. **Which of the 11 relationship types actually need a real incremental filter**, versus which are low-enough volume that the current full-scan-bounded-by-write-count approach is fine to leave as-is? Not every type necessarily needs to change — the destination is "the ones that need it get fixed," not "all 11 get touched."
2. **For each type that does need it, what checkpoint/filter mechanism** — a dedicated checkpoint table mirroring `sec_daily_index_checkpoint`'s shape, a per-type high-water-mark column already available on the source table (per Ticket 01's inventory), or something else? Different types may reasonably get different mechanisms if their source tables differ enough.
3. Does this decision change state-machine-consolidation Ticket 08's conservative "leave all 4 higher-risk types operator-triggered-only" call, or does it stay right pending implementation of whatever this ticket decides?

Use `/grilling` and `/domain-modeling` per this map's Notes.

## Answer

_(pending)_
