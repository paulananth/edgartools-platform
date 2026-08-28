# Account for `silver_acceptance.py`'s `SilverDatabase` coupling in the write-path cutover

Type: grilling
Status: resolved
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

## Answer

**(a) — `silver_acceptance.py` gets ported to target wherever silver lives
post-cutover (Snowflake) and joins Ticket 01's atomic-cutover bundle
explicitly.** Not treated as a special case sequenced against
change-propagation's Ticket 27 instead: it's structurally the same shape as
the MDM/gold readers already in that bundle — a Silver consumer that must
move in lockstep with the write path, not before or after it — and
splitting it onto a different map's schedule risks reintroducing the exact
kind of silent, undocumented gap this ticket exists to close, just shifted
elsewhere instead of eliminated. [Ticket 01](01-decide-write-path-cutover-sequence.md)'s
own answer has been edited in place to say so (see its new bullet), rather
than leaving this decision recorded only here.

**Sweep for other post-2026-08-16 `SilverDatabase` callers — found four
more, same coupling, currently dormant.** Grepped `edgar_warehouse/` for
`SilverDatabase` and checked creation dates via `git log --follow
--diff-filter=A`: alongside `silver_acceptance.py` (filing_artifact,
created 2026-08-23), change-propagation's map introduced four sibling
family-specific modules, all created 2026-08-25, all sharing the identical
hard `silver: SilverDatabase` parameter shape:

- `edgar_warehouse/acquisition/reference_catalog_silver_acceptance.py`
- `edgar_warehouse/acquisition/company_facts_silver_acceptance.py`
- `edgar_warehouse/acquisition/submissions_silver_acceptance.py`
- `edgar_warehouse/acquisition/adv_bulk_dataset_silver_acceptance.py`

Each has its own driver (`drive_reference_catalog_discovery.py`,
`drive_company_facts_discovery.py`, `drive_submissions_discovery.py`,
`drive_adv_bulk_dataset_discovery.py`, mirroring `drive_filing_discovery.py`
for filing_artifact) — but unlike filing_artifact, **none of the other four
are wired into any live scheduled command today.** Checked
`warehouse_orchestrator.py`'s `daily_incremental` capture path directly
(~line 1758-1772): the only gated-capture call site is
`_run_filing_artifact_gated_capture` (behind the off-by-default
`enable_filing_artifact_gated_capture` flag added by Ticket 46) — no
equivalent call site exists for any of the other four families. So the
*immediate* live-break risk this ticket originally found (an atomic cutover
landing before a real production caller is accounted for) is scoped to
`silver_acceptance.py` alone, today. But all five modules carry the
identical structural coupling, and the same risk reappears for any of the
other four the instant it's wired the same way `silver_acceptance.py` just
was — so the cutover plan treats all five uniformly rather than fixing only
the one that happens to be live right now.

**Rollback story:** yes, this changes it, and it's now stated explicitly on
Ticket 01 rather than left implied here — all five acquisition-family
`*_silver_acceptance.py` modules join the atomic write-path-cutover bundle
alongside MDM's and gold's reader cutovers.
