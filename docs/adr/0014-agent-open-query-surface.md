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
- Query substrate is locked (2026-09-19,
  [ticket 02](../../.scratch/agent-open-query-interface/issues/02-lock-query-substrate.md)):
  gold, graph, and MDM all reduce to plain SQL across exactly two
  backends (Snowflake, Postgres) — no RDF/SPARQL/Cypher-only store was
  ever structurally required. The agent reaches them through an **MCP
  server**, writes **raw SQL** directly (no text-to-SQL translation
  layer), and gets **raw JSON** results (no typed response envelope).
  The exact tool surface (one unified query tool vs. per-backend tools)
  remains open — see `.scratch/agent-open-query-interface/map.md` Not
  yet specified.
- SM3-Text-to-Query (NeurIPS 2024) found zero-shot LLM SPARQL
  query-generation accuracy at 3.3% vs. SQL's 47.05% on the same
  benchmark — the deciding evidence behind SQL as the locked substrate
  above and against SPARQL.
- Access control is locked (2026-09-19,
  [ticket 03](../../.scratch/agent-open-query-interface/issues/03-lock-access-control.md)):
  one shared service credential (the same `X-API-Key` pattern as the
  existing MDM API), not per-caller — consistent with ADR 0001's
  Deferred Access Control. A dedicated read-only DB role (`SELECT`-only,
  the same shape as `EDGARTOOLS_PROD_READER`) is the real enforcement
  boundary, not server-side statement parsing alone. Agent queries run
  on a separate warehouse/connection pool with a statement timeout so
  they cannot degrade production refresh or MDM's operational
  workload — exact timeout/row-cap numbers are implementation detail,
  deferred.
- Whatever forms an actual Trading Decision still needs an answer to
  "was this read safe to trade on" — this ADR does not resolve whether
  that stays exclusively the Snowflake Decision Contract's job or
  whether the Agent Query Surface also needs a safety story for that
  specific consumer. Tracked as map fog, not decided here.

Detail: `.scratch/agent-open-query-interface/`. Glossary: `CONTEXT.md`
**Agent Query Surface**, **Agent Query Catalog**.
