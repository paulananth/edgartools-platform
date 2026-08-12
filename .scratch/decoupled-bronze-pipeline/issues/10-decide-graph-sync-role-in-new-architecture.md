# Decide graph sync's role in the decoupled architecture

Type: grilling
Status: resolved
Blocked by: (none)

## Question

[Decide MDM's role in the decoupled architecture](06-decide-mdm-role-in-new-architecture.md)
resolved entity resolution's (`mdm run`) role — async, independent,
system-of-record for master data — but explicitly excluded relationship
derivation and graph sync from its scope, since [Map which gold tables
depend on MDM output](03-research-mdm-gold-dependency-mapping.md) found
zero relationship types reach gold at all. Graph sync is a genuinely
separate decoupling boundary: 3 live consumers (the main dashboard's
Relationships tab, its freshness strip, the Decision Contract's Agent
View) read `NEO4J_GRAPH_MIGRATION` directly, bypassing gold entirely.

This is graph sync's mirror of ticket 06 — same question, different
consumer set:

1. Does relationship derivation (`backfill-relationships`) become an
   independent async consumer of silver-write events (or of MDM's own
   entity-resolution output, since relationships are derived from resolved
   entities), on its own cadence?
2. Does `sync-graph`/`verify-graph` follow the same async model, publishing
   a fresh `GRAPH_ACTIVE_POINTER` generation whenever relationship data
   changes, independent of both silver/gold's and MDM's own schedules?
3. The three live graph consumers found by ticket 03 currently read
   `GRAPH_ACTIVE_POINTER`-gated tables directly — does that generation-scoped
   pattern already provide what's needed for a decoupled design, or does it
   need extending (e.g. per-CIK freshness, not just a global generation
   pointer)?
4. How does this interact with [Decide the completeness/watermark signal
   for async silver and gold](07-decide-completeness-watermark-signal.md),
   which already notes graph needs its own freshness signal separate from
   silver/gold's?

## Answer

**Symmetric split with ticket 06's principle: MDM is system of record for
entities, graph is system of record for relationships.** Decided
2026-08-11. Neither store duplicates the other's authority — MDM's own
`mdm_relationship_instance` table is a working/staging area en route to
graph, not itself a queryable system of record; nothing should be built to
read relationships from MDM's Postgres directly. This is already consistent
with ticket 03's finding that zero gold consumers and zero dbt models ever
read `mdm_relationship_instance` or its Snowflake `MDM` schema mirror — only
`sync-graph` reads it, to publish into the graph.

**Concrete answers:**

1. **Relationship derivation (`backfill-relationships`) becomes an
   independent async consumer — triggered by MDM's own entity-resolution
   output changing, not directly by silver-write events.** Relationships
   are computed *from* resolved entities, so this consumer sits downstream
   of ticket 06's entity-resolution consumer, on its own cadence, not
   gold's or silver's.
2. **`sync-graph`/`verify-graph` also becomes async** — publishing a fresh
   graph generation whenever relationship derivation produces a meaningful
   change, independent of gold/silver/MDM's schedules. This is the actual
   "publish" step that makes relationship data visible to graph's
   system-of-record store; before this step, derived relationships are
   working data, not yet authoritative.
3. **`GRAPH_ACTIVE_POINTER`'s existing generation-scoped pattern already
   provides the mechanism needed — extend it to fire per-event, don't
   invent a new one.** All 3 live consumers (ticket 03) already read
   through this pointer; it just needs to advance per relationship-change
   event instead of per manual/batched `sync-graph` run. This is the same
   shape of fix as ticket 09's DuckDB reducer (generalize an existing
   one-shot-per-run mechanism to fire per-event) and ticket 06's MDM export
   — a consistent implementation pattern recurring across three tickets on
   this map, worth keeping in mind as one shared piece of work rather than
   three independent ones when this gets implemented.
4. **This resolves ticket 07's graph-watermark question**, not just notes
   it: `GRAPH_ACTIVE_POINTER`'s `graph_generation_id` *is* the graph
   completeness signal, already live in production, already exactly the
   kind of generation-scoped watermark this repo's `CONTEXT.md` precedent
   (Relationship Generation Snapshot) describes. No new mechanism needed —
   ticket 07 just needs to formalize "advances per-event" as part of its
   overall watermark design, alongside silver's and MDM's own signals.
