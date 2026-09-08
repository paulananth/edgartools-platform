Type: task
Status: resolved

Blocked by: 01, 02, 03

## Question

Decide and implement how the ~199,252 already-quarantined
`mdm_relationship_instance` rows in prod get corrected, now that Tickets
01-03 have landed the real fix for all 5 affected types. A targeted SQL
correction pass (walk each affected `relationship_id`, re-apply the
corrected close/supersede logic retroactively against existing rows) vs. a
full re-derivation (`derive-relationships` rerun for all 5 types against
already-captured silver data) are the two candidate shapes -- not decided
yet, deliberately blocked until the corrected logic exists (backfilling
under the still-buggy logic would just re-quarantine the same rows, as
Ticket 01's own traced example already shows happening for fresh writes
today).

## Answer

Chose the targeted SQL correction pass, not a full re-derivation rerun.
A full re-derivation reads from silver (not from `mdm_relationship_instance`
itself), so it would insert brand-new synthetic rows for every corrected
fact while leaving the original ~199K quarantined rows sitting as orphaned
duplicates needing their own separate cleanup anyway -- with no
correctness benefit over directly correcting the existing rows, and at
the cost of an expensive full watermark reset/rescan of already-captured
silver data.

**Design** (`edgar_warehouse/mdm/relationship_quarantine_backfill.py`,
new module -- mirrors `mdm_entity_backfill.py`'s precedent of a dedicated
one-off backfill module separate from the regular derivation pipeline):
for every `relationship_id` with at least one quarantined row, walk its
quarantined rows in chronological order and, for each one, find whichever
currently-active row has an OVERLAPPING window and DIFFERING properties
(the exact discriminator `ensure_relationship`'s own conflict-detection
uses). If found: close the conflicting row and un-quarantine the
candidate IN PLACE (repurposing its own `instance_id`, not inserting a
new row) -- but only when (a) a `mdm_relationship_source_priority` rule
still resolves to "none" for the pair (checked via `resolve_source_priority`,
not assumed from `source_system` equality alone -- a rule may have been
added since the row was quarantined, in which case this is a different
resolution axis, supersession by authority, not versioning, and is left
for separate handling), (b) both rows share the same `source_system`
(a genuine cross-source disagreement needs a priority rule or manual
review, not an automated "newer wins" override), and (c) the candidate's
`effective_from` can be positively confirmed at or after the conflicting
row's `valid_from_date` (the same chronological guard
`_deactivate_if_properties_changed` already uses). Any ambiguity defaults
to leaving both rows exactly as they are, counted in a dedicated
`skipped_*` bucket for manual review rather than force-resolved.

Keyset-paginated on `relationship_id` (not "still has a quarantined row"),
so a batch loop correctly advances past relationship_ids whose rows get
deliberately skipped, instead of looping forever on exactly the ones it
can't safely resolve.

Implemented + thoroughly tested (12 tests, SQLite-backed) but **not
executed against real prod** as part of this ticket's resolution --
mirroring how Tickets 01-03 on this branch are committed but not
deployed; running it against the real 199,252-row set is a separate,
higher-stakes action needing its own explicit go-ahead. A CLI entry point
(`mdm backfill-quarantined-relationships --dry-run`) is wired so an
operator can run a dry-run report first.

**Deliberately not automated:** a fresh Snowflake `sync-graph` rebuild.
Ticket 04 found the graph materialization is quarantine-blind, so a
Postgres-side backfill alone leaves stale duplicate edges in the graph
until either a fresh `sync-graph` generation rebuild runs or the separate
query-filter fix (also identified in Ticket 04, not yet implemented)
lands. `run_backfill` prints an explicit reminder of this at the end of
a real (non-dry-run) run.

## 3-axis code review

Ran the mandatory 3-axis `/code-review` (Standards/Spec/GoF). Both
Standards and GoF independently converged on the same real finding:
the overlap+properties-diff conflict check and the chronological guard
were reimplemented inline in the new module instead of calling the
already-proven functions in `graph.py`/`pipeline.py` -- GoF cited this
repo's own repeated "sibling path silently diverged from its proven
pattern" 5-whys shape (documented multiple times in CLAUDE.md) as direct
precedent for why this matters. Fixed by extracting two shared, pure
functions into `graph.py` -- `relationships_conflict()` and
`confirmed_chronologically_after()` -- and switching `ensure_relationship`,
`_deactivate_if_properties_changed`, and this new module to all call the
same functions; confirmed a pure refactor via the full existing
`tests/mdm/test_pipeline_relationships.py`/`test_graph.py` suites passing
unchanged (83 + 29 tests, zero edits needed).

Standards also flagged: (a) the source_system-equality check should
actually call `resolve_source_priority` (renamed from `_resolve_source_priority`
for cross-module reuse) rather than assume "same source_system = always
safe" -- fixed, with a new `skipped_priority_now_configured` bucket and
test for the case where a priority rule has since been configured; (b) no
audit trail for the ~199K mutations -- fixed, but NOT via `MdmChangeLog`
as literally suggested (verified that table never tracks relationships
at all, per `_derive_employed_by`'s own docstring and this repo's
"mdm_change_log had no write-side diff" CLAUDE.md entry) -- instead each
correction appends a marker to the row's own `source_evidence` JSON list,
the mechanism this table already uses for provenance.

Spec confirmed all the load-bearing correctness details independently
(`_intervals_overlap` argument order, the close-boundary date field,
the chronological guard, and the keyset-pagination forward-progress
guarantee) all match the live code exactly, and flagged that this ticket's
own Answer section was still blank -- addressed by this entry. Also noted
Ticket 04's "should trigger a sync-graph re-run afterward" suggestion
wasn't automated -- addressed with the end-of-run reminder print above
(deliberately not auto-triggering sync-graph itself -- out of this
ticket's scope).

Final test count: 12 in `tests/mdm/test_relationship_quarantine_backfill.py`.
Full `tests/mdm/` suite green: 719 passed. Full repo suite green: 3179
passed, 8 failed (the same pre-existing, unrelated Postgres-integration
gaps this repo's suite always shows without a local Postgres), 7 skipped.

**Not yet done:** deploy, and (separately, much later, needing its own
explicit go-ahead) actually execute against real prod.
