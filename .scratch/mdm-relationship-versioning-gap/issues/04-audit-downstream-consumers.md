Type: research
Status: resolved

## Question

Do the downstream consumers of "current" `mdm_relationship_instance` state
(the Snowflake gold export via `mdm export`, graph sync via
`mdm sync-graph`/`mdm publish-relationships`, and the operator MDM/graph
review dashboard) already reflect this quarantine bug's stale data as their
own "current" state, or is there some independent correction path that
already masks it? Bears directly on how urgent this map's fix is --
199,252 quarantined rows in Postgres is one thing; whether that has already
propagated into gold tables/the graph/the dashboard operators and
downstream consumers actually look at is another.

## Context

Every "current" reader found so far in the MDM codebase (`coverage.py`,
`generation.py`, `neighbor_expansion.py`, `pipeline.py`'s own
`current_relationships()`) filters `quarantined = False` -- so structurally,
nothing currently reads a quarantined row as "current." The open question is
whether that's actually a *problem* for downstream freshness (a
quarantined-away newer version means the *older*, non-quarantined version
is what gold/graph/dashboard already show as current -- stale but not
literally invisible) versus something worse (e.g. a relationship
disappearing from exports entirely in some edge case). Not yet traced end
to end.

## Answer

Worse than the Context section's working hypothesis. It is not "stale but
not literally invisible" — quarantined rows actively leak into the
Snowflake graph as duplicate, conflicting active edges, and the parity
monitoring meant to catch drift is itself blind to the same gap, so this
has been silently self-consistent (and undetected) rather than masked by
some independent correction path.

**Gold export (`mdm export`'s default writer, `DOMAIN_TO_TABLE`):** not
implicated at all. It exports only the 5 entity-domain golden tables
(`MDM_COMPANY_ENTITY`/`MDM_ADVISER`/`MDM_PERSON`/`MDM_SECURITY`/`MDM_FUND`)
— relationships are never part of the gold export path.

**Postgres→Snowflake mirror (`export_pending_relationships`,
`edgar_warehouse/mdm/export.py:396`):** not implicated either. `_serialize`
generically copies every column, `quarantined` included, into the
Snowflake `MDM_RELATIONSHIP_INSTANCE` mirror table (confirmed the column
exists there: `infra/snowflake/sql/bootstrap/09_mdm_mirror_schema.sql:306`).
The data reaches Snowflake intact.

**Graph materialization (`edgar_warehouse/mdm/snowflake_graph.py`) is where
it actually breaks.** The edge-build query that populates
`MDM_GRAPH_EDGES` filters `WHERE RI.IS_ACTIVE = TRUE AND RT.IS_ACTIVE =
TRUE` (line ~1487) — no `RI.QUARANTINED = FALSE` anywhere. Traced why this
matters: `quarantine_relationship_version`/`ensure_relationship`'s
conflict-quarantine branch (`graph.py:348`) only ever sets
`row.quarantined = True`; nothing anywhere in the codebase ever sets
`is_active = False` for a quarantined row (confirmed via a full grep of
every `is_active` write site) — the column defaults to `TRUE` at the
schema level and stays `TRUE` for the row's whole life. So a quarantined
row and the pre-existing row it conflicted with are **both**
`is_active = TRUE` and **both** get materialized as separate graph edges
for the same logical (source, target, rel_type) triple with different
properties — not one stale edge, but two simultaneously-live, conflicting
ones. The edge's own `PROPERTIES` JSON blob
(`OBJECT_CONSTRUCT_KEEP_NULL(...)`, line ~1453) doesn't even carry a
`quarantined` key, so nothing downstream of the materialization step (BFS,
WCC, the dashboard) has any way to tell the two apart after the fact.

**The parity/reconcile monitoring that should have caught this is blind to
the same gap, not independent of it.** Both the eligible-edge preflight
count (`snowflake_graph.py:283-287`, used for release-readiness Ticket 94's
capped-sync detection) and the reconcile parity check's own
`MDM_ACTIVE_COUNT` (`snowflake_graph.py:1651-1653`, the "expected" side of
`active_mdm_relationship_parity`) filter only `RI.IS_ACTIVE = TRUE` — the
identical omission. Since both the "expected" count and the "actual" graph
count include quarantined rows the same way, they match each other and
report `MDM_MINUS_GRAPH = 0` — a clean parity result that is clean only
because both sides are wrong in the same direction. This is why 199,252
quarantined rows in Postgres never surfaced as a reconcile mismatch: not
masked by a correction path, but invisible to the only check that would
have flagged it.

**What's actually clean:** the Postgres-native "current" readers
(`coverage.py`, `generation.py`, `neighbor_expansion.py`,
`pipeline.py`'s `current_relationships()`, and the live API's
`api/routers/graph.py:212`) all correctly filter `quarantined = False` —
confirmed by re-reading each, not just trusting the ticket's own Context
section. The operator MDM/graph review dashboard
(`examples/mdm_graph_dashboard/`) inherits whatever `mdm reconcile`
publishes via `graph_review_publish.py` (confirmed: that module has zero
quarantine-related logic of its own, it purely persists
`SnowflakeGraphVerifier.verify()`'s payload) — so the dashboard shows the
same falsely-clean parity numbers, not a corrected view.

**Urgency reassessment:** this raises this map's priority. The original
question was "is 199,252 quarantined rows already stale-but-tolerable, or
worse" — it's worse: every quarantined row is a live, duplicate, wrong
edge in the graph today, invisible to the monitoring built to catch
exactly this class of drift. Fixing Tickets 01-03's write-side bugs stops
the bleeding for new rows going forward but does nothing for the ~199K
rows already quarantined and already double-materialized in the graph —
reinforcing that Ticket 05's backfill (walking each already-quarantined
`relationship_id` and re-deriving it under the corrected logic) needs to
also trigger a `sync-graph` re-run afterward, not just a Postgres-side
correction, or the graph-side duplicates survive the Postgres fix.

**Not fixed here — deliberately out of this research ticket's scope, but a
concrete, scoped fix path for whoever picks it up:** add
`AND RI.QUARANTINED = FALSE` to exactly three query sites in
`snowflake_graph.py` — the `MDM_GRAPH_EDGES` build (~line 1487), the
eligible-edge preflight count (~line 286), and the reconcile parity
`MDM_ACTIVE_COUNT` join (~line 1653). All three already have `RI` in
scope; this is a pure filter addition, no schema change needed (the column
already exists on the mirror table). Flagged in the map's fog rather than
ticketed here, since it needs its own decision about whether a fresh
generation rebuild is required to correct the ~199K already-materialized
duplicate edges, or whether the next regular `sync-graph` run (which does
a full generation rebuild, not an incremental patch, per the
generation-scoped design) naturally self-heals once the query fix lands.
