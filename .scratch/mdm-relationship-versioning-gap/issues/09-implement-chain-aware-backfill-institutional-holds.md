Type: task
Status: resolved
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

Implemented (not yet run against prod -- see "Remaining" below).
`backfill_relationship_id()` in `relationship_quarantine_backfill.py`
rewritten from Ticket 05's pairwise "one active row vs one quarantined
row" walk into a chronological, date-grouped chain walk: loads the full
row set (active + quarantined) for a relationship_id, groups rows sharing
the exact same `effective_from` (avoids order-dependent tie-breaking on
same-date rows), walks groups in ascending date order maintaining an
`open_set`, and closes/reopens via the same `relationships_conflict`/
`confirmed_chronologically_after`/`resolve_source_priority` guards Ticket
05 already used -- never inserting a new row, always UPDATE in place.

**Sub-decision (a) -- identical-properties dedup: answered by the existing
discriminator, not a new dedup step.** `relationships_conflict` already
requires *differing* properties to register as a conflict, so two
chronologically-adjacent same-source rows with genuinely identical
properties never appear as conflicts to each other and are left exactly
as they are -- correct by the existing design, no additional dedup logic
needed or added.

**Sub-decision (b) -- out-of-order arrival: resolved by walk order, no
special-case needed.** Processing strictly in business-date
(`effective_from`) order rather than write/quarantine order means a
late-arriving amendment for an earlier period is naturally slotted into
its correct chronological position when the walk reaches it, correctly
compared against only the rows genuinely earlier than it. No additional
handling beyond the existing `confirmed_chronologically_after` guard was
needed.

**Bug found and fixed during the mandatory 3-axis `/code-review` (Spec
axis) before commit, not caught by the pre-code `/gof-refactor-reviewer`
consult:** a row that stays quarantined after an unresolved conflict in
its own group (e.g. an irreconcilable same-date sibling tie) was still
unconditionally added to `open_set` -- so a later, cleanly-resolving row
could select it as the `conflict` it closes. `close_relationship_version`
only ever sets `valid_to_date`/`effective_to`, never `quarantined` -- so
without a fix, that row would end up permanently stuck `quarantined=True`
forever with a `valid_to_date` already set, a self-contradictory state no
future run could ever correct (a closed row's own dates never change
again). Fixed: closing a previously-quarantined row now also clears
`quarantined`/`quarantine_reason` and counts toward `summary.reopened`
(mirroring the dry-run-safe counter/mutation split the rest of the
function already used). New regression test,
`test_closing_a_row_via_later_supersession_also_clears_its_own_stale_quarantine_flag`,
confirmed to fail before the fix (`reopened=0` instead of `2`) and pass
after.

Full `tests/mdm/` suite green (752 passed) after the fix. Standards and
GoF review axes came back clean (no hard violations; GoF verdict "leave
it" -- one cohesive function, no repeated-change evidence to justify a
structural split).

**Second bug found live during the real prod dry-run, unrelated to the
walk logic above:** `resolve_source_priority()` had no per-call caching,
and the chain walk's own conflict-guard loop called it once per
conflicting row pair -- with `rel_type_id` constant for the whole
type-scoped run and `(existing_source, new_source)` pairs repeating
constantly, the dry-run ran 8.5+ hours without finishing (~9 uncached
Postgres round trips/sec, ~270,000+ estimated redundant queries) before
being manually stopped. Fixed with a `priority_cache` shared across the
entire `run_backfill()` call (not per relationship_id), mirroring the
existing `_ensure_thirteenf_manager` per-batch memoization pattern. Full
detail: CLAUDE.md's "Quarantine backfill uncached priority lookup
5-whys". Re-verified via a fresh dry-run after the fix: completed in
~10 minutes (previously 8.5+ hours, unfinished).

**Real (non-dry-run) backfill executed against prod 2026-09-10, scoped to
`--relationship-type INSTITUTIONAL_HOLDS`.** Task
`f3add6d39f0345f6b9c86dde2a4c67f5`, 06:32-08:18 ET (~1h46m), exit code 0.
Final summary:

```json
{
  "closed": 84212,
  "relationship_ids_examined": 8525,
  "reopened": 62947,
  "skipped_ambiguous_date": 0,
  "skipped_ambiguous_order": 458139,
  "skipped_cross_source": 0,
  "skipped_multiple_conflicts": 62947,
  "skipped_priority_now_configured": 0
}
```

Verified directly against live Postgres (not just log trust): quarantined
`INSTITUTIONAL_HOLDS` rows dropped 65,778 -> 21,704 between two direct
queries taken before and after the run. The remaining 21,704 are expected,
not a bug -- they're the `skipped_ambiguous_order`/`skipped_multiple_conflicts`
cases the design deliberately leaves for manual review rather than
guessing at chronological order or an unconfigured priority.

**Still open, not part of this ticket's scope:** the Snowflake graph
(`sync-graph`) is quarantine-blind (Ticket 04's finding) and still shows
the pre-backfill duplicate edges for every reopened/closed row until a
fresh generation sync + `mdm reconcile` runs -- tracked as the next step
on this map, not blocking this ticket's resolution.

