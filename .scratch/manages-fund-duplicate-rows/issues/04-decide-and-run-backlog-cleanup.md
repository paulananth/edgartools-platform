Type: grilling
Status: resolved
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

Resolved via `/grilling`, all 6 questions accepted as recommended. Also
verified live (not just the map's 5-sample) before grilling: **all**
140,907 duplicate-active-row groups, including the 3,960 that also have a
quarantined row, have fully byte-identical active rows (`properties`,
`valid_from_date`, `valid_to_date`, `source_system`, `source_accession`)
— zero exceptions. The simple-dedup design fully holds across the whole
backlog; it does not need widening.

1. **Kept-row selection:** the ticket's own "keep the earliest
   `instance_id`" premise is corrected — `instance_id` is a random UUIDv4
   (`database.py:71`, no temporal ordering) and every row in a group
   shares one identical `created_at` to the microsecond, so there is no
   meaningful "earliest." Pick deterministically (`min(instance_id)` as a
   plain string sort) purely for idempotent reruns — which row survives
   has zero semantic effect, since all evidence fields are identical.
2. **Marking mechanism:** use the existing, currently-uncalled
   `supersede_relationship_version(session, old_id, new_id)` helper
   (`graph.py:644`) — set `superseded_by_version_id` only. Do not call
   `close_relationship_version`/set `valid_to_date`: `is_active` is never
   flipped to `False` anywhere in this codebase for
   `mdm_relationship_instance` rows (verified — zero write-sites do it);
   "genuinely current" is `is_active=TRUE AND quarantined=FALSE AND
   superseded_by_version_id IS NULL` per `snowflake_graph.py`'s own
   `_active_relationship_filter` docstring. These rows never had a real
   "stopped being true" moment — a `valid_to_date` would misleadingly
   imply one.
3. **Scope:** all 140,907 relationship_ids, including the 3,960 with a
   quarantined row (their active-row sets are equally clean duplicates).
   Explicitly do not touch/un-quarantine/reconsider the quarantined rows
   themselves — that stays `mdm-relationship-versioning-gap`'s domain if
   ever revisited.
4. **Implementation shape:** a new, dedicated write-capable
   module/CLI command, separate from Ticket 03's read-only monitor —
   mirroring the existing `mdm check-fence` (read) vs.
   `relationship_quarantine_backfill.py` (write) split.
5. **Rollout:** a bounded `--limit`/dry-run-then-small-batch first pass
   before the full 140,907-row run, even though the data shape carries no
   risk — insurance against a script-level bug, per this repo's own
   documented `--dry-run` lesson.
6. **Graph resync:** none forced — the next regularly-scheduled
   `sync-graph`/`publish-relationships` run is sufficient; no active
   workflow depends on immediate reflection.

Graduates into [Ticket 05](05-implement-and-run-manages-fund-duplicate-backfill.md)
for the actual implementation + rollout.
