# Agent Open Query Surface (partially supersedes the locked v1 unit-of-read)

**Status:** accepted
**Relationship to 0001:** **Partially supersedes** [0001-agent-decision-surface-first.md](0001-agent-decision-surface-first.md)'s Locked shape (v1) table — a Decision Graph Bundle is no longer the *only* unit an agent may read. Does **not** retire the Snowflake Decision Contract (v1) or the Mongo Decision Projection (v2, [0009-mongo-decision-projection.md](0009-mongo-decision-projection.md)); both continue operating for their existing consumers, and their fail-closed Agent-Grade Read guarantee is unchanged for whatever still reads them.

The platform now also exposes an **Agent Query Surface**: an open-query
interface over MDM, graph, and gold data. An agent composes its own
query against a published **Agent Query Catalog** — data definitions
and relationships (entities, fields, meanings, null semantics, foreign
keys, graph edges) — instead of reading a pre-materialized Decision
Graph Bundle. No Agent-Grade Read gate applies to an Agent Query Surface
result: there is no fixed bundle, so there is nothing to gate at read
time.

## Why

- Operator requirement: an agent must be able to ask any question over
  MDM, graph, and gold data, not only the sections ADR 0001 pre-selected
  into the Trading-Relevant Neighborhood.
- A pre-materialized contract can only expose what was anticipated and
  built in advance. The stated need is open-ended, not a fixed list of
  sections that can grow one ticket at a time.
- The platform already has a partial, undeployed precedent
  (`edgar_warehouse/mdm/api/`) for agent-facing reads outside the
  Decision Contract, covering MDM and graph but not gold — this ADR
  generalizes that direction rather than inventing an unrelated one.

## Considered options (rejected)

- **Widen the pre-materialized contract instead** (add more sections to
  the Decision Graph Bundle / Mongo Decision Projection, keep the
  Agent-Grade Read gate) — rejected: still cannot serve a question the
  operator didn't anticipate and materialize in advance.
- **Harden only the existing MDM FastAPI surface, unchanged in scope** —
  rejected as insufficient on its own: it never covered gold, and its
  routers serve the query shapes they were written for, not arbitrary
  questions. May still be reused as one access path; not decided here.
- **Attach provenance/watermark metadata to results without gating on
  it** (graph generation id, gold `run_id`, silver completeness,
  carried as inspectable fields) — considered, then explicitly declined
  by the operator (2026-09-19, reversing an initial "yes"): an Agent
  Query Surface result carries no freshness or point-in-time identity
  of any kind. See
  [Decide whether provenance metadata travels with Agent Query Surface results](../../.scratch/agent-open-query-interface/issues/01-decide-provenance-metadata-travels.md).
- **Retire the Snowflake Decision Contract / Mongo Decision Projection
  now that an open surface exists** — rejected for this ADR; both
  continue for their existing consumers. Retirement, if it ever happens,
  is a later, separate ticket, not a side effect of this decision.

## Consequences

- ADR 0001's "No Agent-Grade Read if watermark components misaligned"
  row no longer describes every agent read path — only reads through
  the Snowflake Decision Contract / Mongo Decision Projection.
- The Agent Query Surface's query substrate (raw SQL, an MCP server, a
  semantic layer), whether it federates all three stores or exposes them
  per-store, and its access-control model are not decided by this ADR —
  see `.scratch/agent-open-query-interface/map.md` Not yet specified.
- SM3-Text-to-Query (NeurIPS 2024) found zero-shot LLM SPARQL
  query-generation accuracy at 3.3% vs. SQL's 47.05% on the same
  benchmark — directly relevant now that this surface's viability
  depends on the agent generating correct queries. Argues toward SQL
  over Snowflake as a likely substrate and away from SPARQL; not locked.
- Whatever forms an actual Trading Decision still needs an answer to
  "was this read safe to trade on" — this ADR does not resolve whether
  that stays exclusively the Snowflake Decision Contract's job or
  whether the Agent Query Surface also needs a safety story for that
  specific consumer. Tracked as map fog, not decided here.

Detail: `.scratch/agent-open-query-interface/`. Glossary: `CONTEXT.md`
**Agent Query Surface**, **Agent Query Catalog**.
