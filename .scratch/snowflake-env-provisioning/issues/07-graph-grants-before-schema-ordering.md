# Resolve graph grants running before the schema they grant on exists

Type: grilling
Status: open

## Question

Surfaced while implementing Ticket 05, which fixed a different ordering gap
(nothing installed the Neo4j Native App) and initially overclaimed that doing so
made the graph half of a brand-new go-live work. It does not.

`infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` grants
`USAGE`/`SELECT`/`CREATE TABLE` on `{{ database }}.NEO4J_GRAPH_MIGRATION` — but
never creates that schema. It is created by `mdm sync-graph`
(`edgar_warehouse/mdm/snowflake_graph.py:1188`, `CREATE SCHEMA IF NOT EXISTS`).

In `go-live.sh`'s sequence those two sit in the wrong order for a new
environment:

- **Stage 10** — "Snowflake Postgres / graph prerequisites" → runs the grants SQL
- **Stage 13** — "MDM + graph: connectivity, migrations, sync, verification" →
  runs `mdm sync-graph`, which creates the schema

On an established account this is invisible (the schema survives from prior
runs). On a brand-new account — the case this whole map exists to serve — stage
10 grants against a schema that does not exist yet. CLAUDE.md's dev go-live
blockers entry records the same failure class from the other direction: the
graph-review SQL failed in dev with `GRAPH_ACTIVE_POINTER does not exist`
because dev had never had a generation-scoped sync.

Resolve: which of these is right?

(a) **Split the grants stage.** The parts that don't depend on the schema
    (database-level `USAGE`, the compute-pool/warehouse grants, creating the
    database role) stay at stage 10; the schema-scoped grants move to a new
    stage after `mdm sync-graph`. Most faithful to what each grant actually
    needs, but splits one SQL file into two run points.

(b) **Move the whole grants stage after `mdm sync-graph`.** Simplest ordering
    change, but `sync-graph` itself may need grants already in place to write
    into the target database — that dependency needs checking before this can
    be chosen, not assumed.

(c) **Have the grants SQL create the schema itself** (`CREATE SCHEMA IF NOT
    EXISTS` at the top), making it self-sufficient and order-independent. Least
    disruptive to the stage list, but puts schema creation in two places
    (here and `snowflake_graph.py`), which is its own drift risk.

Worth checking before deciding: whether `mdm sync-graph` can actually run at all
without the grants (i.e. whether (b) is even viable), and whether the
`FUTURE TABLES`/`FUTURE VIEWS` grants in the current SQL were written precisely
so the ordering wouldn't matter — in which case the real gap may be narrower
than it looks and only the `ALL TABLES`/`ALL VIEWS` grants are misplaced.

## Notes

Not blocking Ticket 05's install stage, which is correct and independently
necessary — this is the second half of the same "brand-new account" ordering
story.
