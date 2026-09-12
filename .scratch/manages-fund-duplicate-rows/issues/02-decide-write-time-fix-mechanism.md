Type: grilling
Status: open
Blocked by: 01

## Question

Using Ticket 01's root-cause finding, decide the actual fix mechanism for
`ensure_relationship`'s (or `_derive_manages_fund_batch`'s) failure to
dedupe identical-evidence inserts:

1. Should the fix live in `ensure_relationship` itself (a shared fix
   benefiting every relationship type, if the mechanism turns out to be
   general), or scoped to `_derive_manages_fund`/`_derive_manages_fund_batch`
   specifically (if the mechanism is batching-specific, per Ticket 01's
   finding)?
2. Does the fix change `GraphSyncEngine`'s caching/priming contract in a
   way other callers (the other 10 relationship types' `_derive_*`
   methods) need to be re-verified against, or is it fully isolated?
3. What test proves the fix — a regression test reproducing the exact
   live shape (same adviser+fund pair, same properties, processed twice
   within one call), at whatever seam Ticket 01 finds the failure at?

Use `/grilling` and `/domain-modeling` per this map's Notes.

## Answer

_(pending)_
