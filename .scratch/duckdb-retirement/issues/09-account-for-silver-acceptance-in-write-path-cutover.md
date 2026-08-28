# Account for `silver_acceptance.py`'s `SilverDatabase` coupling in the write-path cutover

Type: grilling
Status: open
Blocked by: none

## Question

Surfaced by [change-propagation's Ticket 45](../../change-propagation/issues/45-coordinate-with-duckdb-retirement-cutover.md):
this map's Domain list and its resolved [Ticket 01](01-decide-write-path-cutover-sequence.md)
(atomic write-path cutover, rollback bundles "the write path + MDM's and
gold's reader cutovers together") never account for
`edgar_warehouse/acquisition/silver_acceptance.py` — because that module
didn't exist as a live production caller until 2026-08-27
(`feat(acquisition): wire filing_artifact's gated capture into
daily_incremental`, PR #481), 11 days after this map's tickets were all
resolved (2026-08-16). It's a real, hard dependency: both of its entry
points take `silver: SilverDatabase` (DuckDB) directly, by design — its own
docstring explains it's the deliberate seam that re-acquires the
`SilverDatabase` coupling `discovery.py` otherwise avoids, so it can write
and read back `sec_raw_object` as the `filing_artifact` family's one Silver
producer.

This ticket exists to close that gap before this map can honestly claim
"ready to hand off for implementation" again. Decide:

- Does `silver_acceptance.py` get ported to target wherever silver lives
  post-cutover (Snowflake), added explicitly to this map's in-scope Domain
  and to Ticket 01's atomic-cutover bundle alongside the MDM/gold readers —
  or is there a reason to treat it differently (e.g. sequence it with
  change-propagation's own Ticket 27 acquisition-path cutover instead of
  this map's write-path cutover)?
- Are there other new callers of `SilverDatabase` introduced by
  change-propagation's map since 2026-08-16 that this same gap applies to —
  check that map's Domain/file list and its own resolved tickets for any
  other direct `silver_store`/`SilverDatabase` imports, not just this one
  already-found instance.
- Does this change Ticket 01's rollback story (currently: write path + MDM's
  and gold's reader cutovers move atomically together)? If
  `silver_acceptance.py` joins that atomic bundle, say so explicitly in
  Ticket 01's own answer rather than leaving it implied by this ticket
  alone.

Resolve with the same discipline Ticket 45 used: check live code and commit
history, not just docstrings, since this whole gap exists because a plan
written on one date didn't know about code written 11 days later.
