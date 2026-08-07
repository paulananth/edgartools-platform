# Resolve graph grants running before the schema they grant on exists

Type: grilling
Status: resolved

## Question

Carried over from the snowflake-env-provisioning map's Ticket 07 (closed
there as out of scope for that map's narrower "stand up an empty infra
shell" destination; squarely in scope here, since this map's destination is
specifically about repopulating a brand-new account end to end).

`infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` grants
`USAGE`/`SELECT`/`CREATE TABLE` on `{{ database }}.NEO4J_GRAPH_MIGRATION` —
but never creates that schema. It is created by `mdm sync-graph`
(`edgar_warehouse/mdm/snowflake_graph.py:1188`, `CREATE SCHEMA IF NOT
EXISTS`).

In `go-live.sh`'s stage sequence those two sit in the wrong order for a
brand-new account:

- **Stage 10** — "Snowflake Postgres / graph prerequisites" → runs the
  grants SQL
- **Stage 13** — "MDM + graph: connectivity, migrations, sync,
  verification" → runs `mdm sync-graph`, which creates the schema

On an established account this is invisible (the schema survives from prior
runs). On a brand-new account — exactly the situation this map exists to
handle — stage 10 grants against a schema that does not exist yet.

Resolve: which of these is right?

(a) **Split the grants stage.** The parts that don't depend on the schema
    (database-level `USAGE`, the compute-pool/warehouse grants, creating the
    database role) stay at stage 10; the schema-scoped grants move to a new
    stage after `mdm sync-graph`. Most faithful to what each grant actually
    needs, but splits one SQL file into two run points.

(b) **Move the whole grants stage after `mdm sync-graph`.** Simplest
    ordering change, but `sync-graph` itself may need grants already in
    place to write into the target database — that dependency needs
    checking before this can be chosen, not assumed.

(c) **Have the grants SQL create the schema itself** (`CREATE SCHEMA IF NOT
    EXISTS` at the top), making it self-sufficient and order-independent.
    Least disruptive to the stage list, but puts schema creation in two
    places (here and `snowflake_graph.py`), which is its own drift risk.

Worth checking before deciding: whether `mdm sync-graph` can actually run at
all without the grants (i.e. whether (b) is even viable), and whether the
`FUTURE TABLES`/`FUTURE VIEWS` grants in the current SQL were written
precisely so the ordering wouldn't matter — in which case the real gap may
be narrower than it looks and only the `ALL TABLES`/`ALL VIEWS` grants are
misplaced.

## Notes

Not blocking the Neo4j Native App install stage itself (already correct and
independently necessary) — this is the schema/grants half of the same
"brand-new account" ordering story.

## Answer

**Decision: option (b), moved unsplit — but to a more precise location than
"after mdm sync-graph" in the abstract.** Traced live against the actual
code, not assumed:

**1. `mdm sync-graph` needs zero grants from this file to succeed — (b) is
fully viable, resolving the ticket's flagged unknown.** Its write path
(`render_graph_tables()` in `edgar_warehouse/mdm/snowflake_graph.py:1173`,
called from `SnowflakeGraphSyncExecutor.sync()`) issues its own
`CREATE SCHEMA IF NOT EXISTS {target_database}.{target_schema}` followed by
`CREATE TABLE IF NOT EXISTS` for `GRAPH_GENERATION` etc. — all under
`sync-graph`'s own Snowflake connection privileges, not the Native App's
`NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE`. Confirmed by reading every reference
to `native_app_database_role`/`native_app_user_role`/`native_app_admin_role`
in that file: all three are used exclusively inside `_verify_native_app()`
(verify-graph's own check function, line 501+) — never inside `sync()`'s
write path. Sync and verify are fully decoupled from the grants.

**2. `mdm verify-graph`'s native-app checks genuinely need the grants
in place — confirming the other half of the ordering constraint.**
`_verify_native_app()` runs `SHOW GRANTS...` queries against exactly what
the grants file creates (`app_user_role_grant`, `database_role_privileges`,
etc.), each with an explicit remediation message naming
`infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`. So the grants
stage must run after the schema exists AND before any verify-graph call
that cares about native-app status.

**3. Splitting the file (option a) buys almost nothing.** Every statement
in the file except the two account-level grants (lines 17-20,
`CREATE COMPUTE POOL`/`CREATE WAREHOUSE ON ACCOUNT`) references
`{{ database }}.NEO4J_GRAPH_MIGRATION` as a schema — `USE DATABASE` doesn't,
but `GRANT USAGE ON SCHEMA`, all four `ALL`/`FUTURE TABLES`/`VIEWS` grants,
`GRANT CREATE TABLE ON SCHEMA`, and the two `EDGARTOOLS_GRAPH_APP_USER`
schema grants all do. This is not "only the ALL TABLES/VIEWS grants are
misplaced" as the ticket speculated — it's essentially the whole file.
A two-run-point split would save two lines.

**4. Option (c) (self-creating schema) works but duplicates real design
intent.** `render_graph_tables()`'s `CREATE SCHEMA IF NOT EXISTS` sits
directly above a substantial comment block explaining the
generation-scoped `GRAPH_GENERATION`/`GRAPH_ACTIVE_POINTER` design (07-05,
RSYNC-01/02/05) — copying schema creation into the grants SQL too means
that design intent now lives in two files that must be kept in sync by
hand. Rejected in favor of (b), which needs no duplication.

**5. The schema is actually created earlier than "mdm sync-graph" in the
wizard's own command list suggests — inside `bronze_seed_silver_gold`'s
internal Step Function chain, not the wizard's explicit stage.** Traced
`write_bronze_seed_silver_gold_definition()` in
`infra/scripts/deploy-aws-application.sh:3718+`: its `MdmSync` step
(line 3914) runs `mdm sync-graph` inside the SFN itself, several go-live.sh
stages before the wizard's own explicit `mdm sync-graph` call in the "MDM +
graph: connectivity, migrations, sync, verification" stage
(`go-live.sh:786`). That SFN's own `MdmVerify` step is deliberately
fault-tolerant — `mdm_verify["Catch"] = [{"ErrorEquals": ["States.ALL"],
... "Next": "GoldRefresh"}]` (line 3916), with a comment confirming
"verify-graph is validation-only ... must never block gold-refresh" — so a
missing-grants failure there doesn't halt the SFN, it just makes that one
verify pass report native-app checks as failed. But the wizard's own final
explicit `mdm verify-graph` call (`go-live.sh:787`) has no such Catch — a
hard failure there is a real risk to `deploy --apply`, not just a cosmetic
miss.

**Where the fix goes:** remove the
`snow sql ... neo4j_graph_analytics_app_grants.sql` line from the
"Snowflake Postgres / graph prerequisites" stage (`go-live.sh:715-719`),
leaving only `bootstrap-prod-mdm.sh` there (that stage's Postgres
provisioning is entirely unrelated to the graph schema — confirmed via
Ticket 03 of this map, still open, but the code separation is already
clear: `bootstrap-prod-mdm.sh` only touches Postgres credentials/migration).
Re-add the grants command as the **first line of the existing "MDM + graph:
connectivity, migrations, sync, verification" stage**
(`go-live.sh:779-787`, ahead of `mdm check-connectivity`) — not a new
stage. This guarantees the grants run after `bronze_seed_silver_gold`
(stage order already places it earlier, at `go-live.sh:721`, and that
stage's `MdmSync` step unconditionally creates the schema regardless of
whether its own soft-failing `MdmVerify` passes) and before the wizard's
own hard-failing `mdm verify-graph` call in the same stage.

**One residual unknown, not blocking this decision:** whether `snow sql`
aborts its whole `--filename` run on the first failed `GRANT ... ON SCHEMA
<nonexistent>` statement, or continues past failed statements and only
exits non-zero at the end. Under `go-live.sh`'s `set -euo pipefail`, either
behavior means today's stage-10 placement is a real failure risk on a
brand-new account, not just a silent no-op — but it doesn't change what the
fix is. Worth confirming empirically the first time this stage actually
runs against a fresh account (Ticket 06 of this map, the go-live runbook
assembly, is where that live exercise happens).
