# Agent Open Query Interface

Label: `wayfinder:map`

## Destination

An implementation-ready, decision-complete plan for the **Agent Query
Surface**: an open-query interface where an automated agent composes its
own query over MDM (Postgres), graph (Snowflake Neo4j Graph Analytics
Native App / Postgres mirror), and gold (Snowflake dynamic tables) data,
guided only by a published **Agent Query Catalog** of data definitions
and relationships. No pre-materialized bundle. No fixed set of
pre-approved questions.

## Notes

- Repo: `edgartools-platform`. Planning only unless a later Notes override
  carries implementation into the map. Produce decisions, not PRs, until
  the way is clear.
- Decision locked 2026-09-19 via `/wayfinder` + `/wait-what` grilling: the
  operator chose an open-query interface (Option A of three presented —
  arbitrary query vs. a widened pre-materialized contract vs. hardening
  the existing-but-undeployed MDM FastAPI surface alone) over the other
  two. Recorded in [ADR 0014](../../docs/adr/0014-agent-open-query-surface.md),
  which **partially supersedes** ADR 0001's locked v1 unit-of-read: a
  Decision Graph Bundle is no longer the *only* thing an agent may read.
- The existing [Snowflake Decision Contract](../agent-decision-contract/map.md)
  (v1) and [Mongo Decision Projection](../mongodb-v2-agent-interface/map.md)
  (v2) are **not** retired by this decision and keep serving their
  existing consumers unless a later ticket here explicitly retires them.
  Their fail-closed Agent-Grade Read guarantee is untouched for whatever
  still reads them.
- Predecessor input: the SPARQL/RDF query-language research this line of
  maps started from is now directly load-bearing, for a different reason
  than originally asked. SM3-Text-to-Query (NeurIPS 2024) found zero-shot
  LLM SPARQL query-generation accuracy at 3.3% vs. SQL's 47.05% on the
  same benchmark. An open-query interface's viability depends on the
  agent generating correct queries, so this argues toward SQL-over-
  Snowflake as a likely substrate and away from SPARQL — not decided,
  see Not yet specified. This closes the original SPARQL/RDF question
  with evidence: not ruled out by hosting availability alone
  ([mongodb-v2-agent-interface ticket 09](../mongodb-v2-agent-interface/issues/09-survey-relationship-edge-serving-options.md)),
  now also weak on the one axis (LLM query generation) that matters most
  for *this* destination.
- Existing but undeployed asset: `edgar_warehouse/mdm/api/` (FastAPI,
  `X-API-Key` auth via `require_api_key`) already exposes MDM Postgres
  read endpoints (entities, companies, advisers, persons, securities,
  funds, stewardship, rules) and graph reads off the Postgres mirror
  (`routers/graph.py`). No ECS service or task definition was found for
  it in Terraform or `infra/aws-prod-application.json`; Terraform has an
  explicit `removed` block for its API-key secret
  (`aws_secretsmanager_secret.mdm_api_keys`, `destroy = false`), checked
  live 2026-09-19. Covers **zero** gold data. Relevant prior art, not a
  decision-complete answer.
- Skills: `/grilling`, `/domain-modeling`, ADR 0001, ADR 0014,
  `CONTEXT.md` Agent decision support.
- Ask the operator one grilling question at a time.

## Decisions so far

- [Decide whether provenance metadata travels with Agent Query Surface results](issues/01-decide-provenance-metadata-travels.md) — No. Reversed from an initial "yes, by default": no graph generation id, gold `run_id`, silver-completeness flag, or any point-in-time identity travels with an Agent Query Surface result, by default or on request. Plain live reads only. Does not touch the Snowflake Decision Contract / Mongo Decision Projection's own Decision Watermark, which is unchanged.
- [Lock the Agent Query Surface's query substrate](issues/02-lock-query-substrate.md) — Gold/graph/MDM all reduce to plain SQL across exactly two backends (Snowflake, Postgres); no RDF/SPARQL/Cypher-only store was ever structurally required. Transport is an MCP server; the agent writes raw SQL directly (no text-to-SQL translation layer); results return as raw JSON (no typed response envelope).
- [Lock access control for the Agent Query Surface](issues/03-lock-access-control.md) — One shared service credential (same `X-API-Key` pattern as the existing MDM API), not per-caller. A dedicated read-only DB role (`SELECT`-only, same shape as `EDGARTOOLS_PROD_READER`) is the real enforcement boundary, not server-side parsing alone. Agent queries run on a separate warehouse/connection pool with a statement timeout so they cannot degrade production refresh or MDM's operational workload — exact numbers deferred.

## Not yet specified

- Whatever eventually forms a real Trading Decision from an Agent Query
  Surface read needs some safety/freshness story from *somewhere* —
  ticket 01 explicitly declined to put it on this surface, so it has to
  come from elsewhere (the existing Decision Contract path, a
  consuming agent's own logic, or something not yet named) if it's
  needed at all. Not yet a question anyone has asked; flagged so it
  isn't lost.
- Exact MCP tool surface: one unified `run_query(sql)` tool that routes
  to the right backend, versus two explicit per-backend tools (e.g.
  `query_snowflake` / `query_mdm_postgres`) the agent picks and joins
  across itself. Now sharper than the original "federated vs. per-store"
  framing (ticket 02 already fixed the substrate as SQL over exactly
  Snowflake + Postgres) but not yet locked.
- Whether/how the existing undeployed MDM FastAPI surface
  (`edgar_warehouse/mdm/api/`) is reused, replaced, or left as-is.
- Whether/when the v1 Snowflake Decision Contract and v2 Mongo Decision
  Projection get retired in favor of this surface, or continue
  indefinitely alongside it.

## Out of scope

- Writes to MDM, graph, or gold data through this surface (read-only,
  same boundary ADR 0001 already drew).
- SEC ingest, bronze capture, ledger doctrine (ADR 0002 / ADR 0006) —
  unaffected by this decision.
- Trading execution, market prices, product OAuth (carried over from
  ADR 0001's own scope; unchanged here).
