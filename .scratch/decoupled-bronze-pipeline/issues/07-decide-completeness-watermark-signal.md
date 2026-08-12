# Decide the completeness/watermark signal for async silver and gold

Type: grilling
Status: resolved
Blocked by: 04

## Question

Today "silver is complete for this run" is knowable because one Step
Functions execution walked through all its windows sequentially before
gold-refresh ran. In a fully async, message-driven world, how does
anything (gold, MDM, an operator) know "silver has caught up to bronze" or
"gold reflects all silver as of X"? Real prior art exists in this repo's
own `CONTEXT.md` (Decision Watermark, Release Data Watermark, Relationship
Generation Snapshot) — this ticket should build on that pattern, not invent
a new one from scratch. Depends on ticket 04's event-granularity decision,
since the watermark's unit of progress follows from what the trigger
granularity actually is.

**Scope addition, from [Map which gold tables depend on MDM
output](03-research-mdm-gold-dependency-mapping.md) (2026-08-11):** graph
sync (`NEO4J_GRAPH_MIGRATION`) needs its own freshness/completeness signal,
separate from gold's — confirmed it already has one in production today
(`GRAPH_ACTIVE_POINTER`'s `graph_generation_id`, surfaced by the main
dashboard's freshness strip alongside, but distinct from, gold's
`updated_at`). Don't design this ticket's watermark as if "silver + gold"
covers everything that needs a completeness signal — graph sync has 3 live
consumers (main dashboard's Relationships tab, its freshness strip,
Decision Contract's Agent View) that bypass gold entirely and need their
own answer to "is the graph caught up," reusing `GRAPH_ACTIVE_POINTER`'s
existing generation-scoped pattern rather than inventing a fourth one.

**Graph watermark sub-question resolved, from [Decide graph sync's role in
the decoupled architecture](10-decide-graph-sync-role-in-new-architecture.md)
(2026-08-11):** confirmed (not just proposed) — `GRAPH_ACTIVE_POINTER`'s
`graph_generation_id` *is* the graph completeness signal; it just needs to
advance per-event instead of per manual/batched run. Also confirmed a
fourth signal this ticket needs to design for, from [Decide MDM's role in
the decoupled architecture](06-decide-mdm-role-in-new-architecture.md): the
Decision Contract's Agent View needs its own explicit "MDM-resolved"
readiness gate, distinct from silver/gold/graph's signals. This ticket's
remaining scope is narrower now: formalize silver's and MDM-entity's
watermarks (graph's and the Agent-View gate are already answered) and
decide how the four signals compose for a consumer that needs "fully
caught up" across all of them.

## Answer

**Reuse `CONTEXT.md`'s existing Decision Watermark composite as-is — silver
completeness, graph generation id, gold/feature as-of, business date. No
new watermark shape, no fifth MDM component.** Decided 2026-08-11.

1. **Decision Watermark's four components are this ticket's answer.**
   `CONTEXT.md` already defines it precisely: "silver-derived parse/
   completeness claims (versions and section coverage), Relationship
   Generation Snapshot (or equivalent graph generation id), gold/feature
   as-of (run_id), and business date... a bundle is invalid for agent use
   if any required component is missing or the components are known to
   disagree." This ticket's job is making each component producible
   incrementally (async, per-accession per [ticket 04](04-decide-event-granularity.md))
   rather than only at synchronous run boundaries — not designing a new
   composite.
2. **MDM's readiness does not need a fifth component.** `CONTEXT.md`'s
   Decision Subject Universe — membership in "the platform tracked/active
   universe (MDM or company sync tracking status that marks the name as
   maintained)" — is a membership filter, not a freshness watermark axis.
   [Ticket 06](06-decide-mdm-role-in-new-architecture.md)'s Agent View
   readiness gate *is* this existing mechanism
   (`tracking_status='active'`): a company isn't in the Decision Subject
   Universe at all until MDM resolves it, rather than being in it with a
   staleness flag to check against a watermark.
3. **Gold's own `run_id`-scoped status (`edgartools_gold_status`/
   `SERVING_REFRESH_STATUS`) is a fourth instance of the same generalization
   pattern already applied three times elsewhere on this map** — silver's
   reducer ([ticket 09](09-decide-silver-write-storage-target.md)), MDM's
   export ([ticket 06](06-decide-mdm-role-in-new-architecture.md)), and
   graph's `GRAPH_ACTIVE_POINTER` ([ticket 10](10-decide-graph-sync-role-in-new-architecture.md))
   all independently converged on "generalize an existing one-shot-per-run
   mechanism to advance per-event." `edgartools_gold_status` needs the
   identical treatment: today one row per `run_id`; the async design needs
   it advancing per accession-batch instead, same shape as the other
   three.

**Net for the map:** all four Decision Watermark components now have a
concrete, already-decided path to becoming incrementally producible:
silver (ticket 09's reducer), graph (ticket 10's `GRAPH_ACTIVE_POINTER`),
gold (this ticket's `edgartools_gold_status` generalization), business date
(unchanged, already static per event). [Ticket 08](08-decide-gold-compute-location.md)
is the only remaining open ticket on this map.
