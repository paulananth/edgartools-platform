# Decide the DDL Generator's Non-DuckDB Schema Source

Type: grilling
Status: open
Blocked by: 01

## Question

`infra/scripts/generate_silver_landing_ddl.py` (built during the closed
silver-snowflake-migration map's Ticket 05) generates the Snowflake
landing-zone DDL by introspecting a *live DuckDB database* — chosen
specifically because `silver_store.py`'s schema isn't SQLAlchemy, so
DuckDB introspection was the pragmatic source of truth available at the
time. Per this map's charting decision ("DuckDB leaves the codebase
entirely"), that source of truth goes away — you can't introspect a
DuckDB instance that no longer exists once [Ticket 01](
01-decide-write-path-cutover-sequence.md)'s cutover completes (hence this
ticket is blocked by it — the generator's replacement design depends on
knowing what, if anything, of `silver_store.py`'s schema-defining code
survives the cutover).

Decide: does `silver_store.py`'s schema move to a different explicit
representation (e.g. SQLAlchemy models, matching how `mdm/database.py`
already represents its 25-table Postgres schema) that both the DDL
generator and any remaining code can introspect without a live DuckDB
instance? Or does DDL generation stop being regenerated at all after
cutover (the landing-zone schema is now Snowflake's own source of truth,
managed directly via committed SQL, with `silver_store.py`'s DDL string
either deleted or kept only as documentation)? Also confirm: does anything
else in the codebase besides this one generator introspect DuckDB schema
today (grep before assuming it's just this one caller)?

## Deliverable

A decided replacement schema-source for DDL generation (or an explicit
decision that DDL generation retires entirely post-cutover), plus
confirmation of every current caller that needs migrating.
