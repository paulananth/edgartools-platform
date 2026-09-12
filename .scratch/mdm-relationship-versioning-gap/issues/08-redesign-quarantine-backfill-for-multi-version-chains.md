Type: grilling
Status: resolved
Blocked by: 05

## Question

A dry-run of Ticket 05's real backfill against live prod (2026-09-09) found
that its "one active row vs. one quarantined row" design does not match
reality: `closed: 0, reopened: 0` -- every one of the 219,247 quarantined
rows examined hit a skip bucket, 90% of them (`skipped_multiple_conflicts`,
219,247 rows across 20,157 relationship_ids) because more than one
currently-active, non-quarantined row already conflicts with the
quarantined candidate. Ticket 05's design deliberately bails out rather
than guess which one to close.

A live-Postgres diagnostic (read-only) confirmed the real shape: for
every relationship type, the multiple simultaneously-"active" rows on one
`relationship_id` are ~100% same-`source_system` (not a genuine
cross-source disagreement -- ruling out the "needs a priority rule"
explanation Ticket 05's design anticipated). By type:

| Type | relationship_ids with 2+ active rows | ...and also >=1 quarantined row |
|---|---|---|
| MANAGES_FUND | 140,907 | 3,960 |
| INSTITUTIONAL_HOLDS | 63,591 | **7,966** |
| COMPANY_HOLDS | 4,767 | 2,568 |
| EMPLOYED_BY | 2,486 | 1,466 |
| IS_INSIDER | 2,254 | 162 |
| HOLDS | 1,424 | 831 |

The number of simultaneously-active rows per `relationship_id` (among
those with >=1 quarantined row) ranges from 2 up to 353 -- a real chain of
never-closed versions, not a single stuck row. Does the backfill mechanism
need to change to handle this, and if so, how?

## Answer

Yes. Confirmed via `/domain-modeling` + `/grilling` (this ticket) that
`CONTEXT.md`'s existing "Generation-Eligible Relationship Version" term
implicitly assumes at most one *current* version at a time ("ended
history remains eligible") -- the live data breaks that invariant at
scale, so this needed an explicit design decision, not just an execution
step.

**MANAGES_FUND ruled explicitly out of scope for this ticket/map.** Its
root cause is structurally different: it silently accumulates duplicate
active rows instead of reaching quarantine (140,907 relationship_ids,
far larger blast radius than this map's 199K-quarantined-rows
destination). This is a distinct write-time bug, not a backfill-design
gap, and needs its own future wayfinder map.

**Correction (2026-09-12, [manages-fund-duplicate-rows](../../manages-fund-duplicate-rows/map.md)):**
the specific mechanism named above ("empty `properties` dict, discriminator
can never fire") is wrong -- the real, live `_derive_manages_fund_batch`
code path passes a full properties dict and has since before this ticket
was written. Direct MDM Postgres sampling instead found every duplicated
`relationship_id` has 2-4 rows with byte-identical properties/validity
window/`source_system`/`source_accession`/`created_at` -- a different,
not-yet-root-caused failure of `ensure_relationship`'s identical-evidence
merge check. The "needs its own future wayfinder map" conclusion still
holds; only the named mechanism was wrong. See the new map for the
corrected investigation.

**Mechanism: extend Ticket 05's existing module, not full re-derivation,
not a call to `ensure_relationship`.** Two mechanism candidates were
considered and rejected before landing here:

- Full re-derivation (`derive-relationships` rerun from silver) --
  rejected again, same reason Ticket 05 already gave: it inserts
  brand-new synthetic rows, leaving every original row (now up to 353 per
  relationship_id) as an orphaned duplicate needing its own separate
  cleanup, with no correctness benefit over correcting in place.
- Literal replay of `ensure_relationship` itself over each
  relationship_id's full chronological row history -- also rejected.
  `ensure_relationship` (`graph.py:231`) always *inserts* a new row for
  anything it doesn't merge as identical evidence; replaying it would
  create a fresh `instance_id` for every historical row and leave the
  originals as orphaned duplicates -- the exact same failure mode as full
  re-derivation, just reached through a different door. Caught and
  corrected mid-session before charting this ticket.

**Chosen mechanism:** extend `relationship_quarantine_backfill.py`'s
existing per-`relationship_id` walk (already using the shared
`relationships_conflict`/`confirmed_chronologically_after`/
`resolve_source_priority` functions `ensure_relationship` itself uses) so
that instead of comparing one quarantined row against the current active
candidates, it:

1. Loads the relationship_id's FULL row set (both currently-active and
   currently-quarantined -- quarantined rows represent legitimate
   historical write attempts that were wrongly rejected, not noise to
   discard).
2. Sorts the full set by the same chronological key Ticket 05 already
   uses (`effective_from`, falling back to `valid_from_date`).
3. Walks chronologically, maintaining the set of rows currently
   considered "open" as it goes, and for each row: checks it against
   every still-open row it overlaps with (not just a single current
   candidate), applying the same conflict/priority/chronological-guard
   rules Ticket 05 already extracted -- closing (via UPDATE, never
   INSERT) whichever open row(s) it supersedes, un-quarantining itself in
   place if it wins, or leaving both untouched (counted in the existing
   `skipped_*` buckets) when the same ambiguity conditions Ticket 05
   already defined apply (cross-source with no priority rule, ambiguous
   same-day ordering, a priority rule now configured).
4. Never inserts a new row and never discards an old one -- every
   correction is an UPDATE against an existing `instance_id`, preserving
   Ticket 05's original design property that the ~199K (now understood to
   be more, given the chain depth) original rows are corrected in place,
   not orphaned.

**Rollout scoped to INSTITUTIONAL_HOLDS first** (7,966 relationship_ids,
the dominant and best-understood case), not all 6 affected types at once
-- proves the chain-walk mechanism on the largest real case before
generalizing to COMPANY_HOLDS/EMPLOYED_BY/IS_INSIDER/HOLDS, which may have
subtly different property shapes/edge cases not yet examined.

**Not yet specified, deferred to the implementation ticket:** exact
handling of chronologically-adjacent rows with genuinely identical
properties (no conflict by definition, so both would correctly stay
simultaneously "active" under the existing discriminator -- worth
deciding whether the redesign additionally dedupes these as harmless
redundancy, or leaves them, since they're not wrong, just redundant); and
whether out-of-business-date-order arrival (a late-filed amendment for an
earlier quarter, arriving after later quarters were already processed)
needs any special handling beyond the existing `confirmed_chronologically_after`
guard.
