# Lock the Agent Query Surface's query substrate

Type: grilling
Status: resolved
Blocked by: none

## Question

Gold, graph, and MDM all reduce to plain SQL across exactly two
backends: Snowflake (gold tables, `MDM_GRAPH_NODES`/`MDM_GRAPH_EDGES`,
and the Neo4j Graph Analytics Native App's algorithms, all reached with
ordinary `SELECT`/`CALL` statements) and Postgres (MDM's operational
entities and its `mdm_relationship_instance` graph mirror). No RDF/
SPARQL/Cypher-only store is structurally required.

Two things are still genuinely open:

1. **Transport**: does the agent get an MCP server exposing read-only
   query tools (e.g. `run_query(sql)`, `describe_schema()`), or a more
   direct path (raw Snowflake/Postgres connection credentials, or a thin
   passthrough HTTP API)?
2. **Translation layer**: does the agent write raw SQL itself, informed
   by the Agent Query Catalog as schema/relationship context — or does a
   text-to-SQL / semantic layer sit between the agent's natural-language
   question and the SQL that actually runs?
3. **Response format** (raised by the operator's answer, not asked
   above): does a query tool's result come back as raw JSON — whatever
   shape the SQL naturally produces — or wrapped in a typed/structured
   response envelope the way the Decision Graph Bundle is?

## Comments

- 2026-09-19 answered in one pass: **MCP server** (Q1) exposing a
  **raw SQL** query tool (Q2), returning **raw JSON** results (Q3,
  volunteered by the operator, not originally asked). No translation
  layer, no typed response envelope — consistent with the whole
  direction of ADR 0014: open query in, open data out, nothing
  pre-shaped on either side.

## Answer

The Agent Query Surface is an **MCP server** exposing at least a
`run_query(sql)`-shaped tool (exact tool surface — one tool vs. several,
per-backend vs. unified — is separate fog, see this map's Federated vs.
per-store item). The agent writes **raw SQL** directly against the Agent
Query Catalog's schema; there is no text-to-SQL/semantic-layer
translation step between the agent's question and the SQL that runs.
Results come back as **raw JSON** — whatever shape the query naturally
produces — not wrapped in a typed/structured response envelope. No
Decision Graph Bundle-style section/coverage-flag shape applies here;
that vocabulary stays scoped to the Snowflake Decision Contract / Mongo
Decision Projection (ADR 0001 / ADR 0009), unchanged by this ADR 0014
surface.
