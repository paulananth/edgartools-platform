# Decide the DDL Generator's Non-DuckDB Schema Source

Type: grilling
Status: resolved
Blocked by: 01 (resolved)

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

## Answer

**Grounding, checked directly:** the premise needed a correction first —
`generate_silver_landing_ddl.py` does not introspect a *live* production
DuckDB instance at all. `_reflect_landing_tables()` opens a fresh
`duckdb.connect(":memory:")`, executes `silver_store._DDL` (the raw
`CREATE TABLE` SQL **string**, plain Python source) against it, then reads
the result back via `information_schema.columns`/`duckdb_constraints()`.
DuckDB here is used purely as an ephemeral SQL-parsing/type-resolution
engine to turn a hand-written DDL string into a structured
(name, type, nullable, constraints) shape — not a runtime data dependency.
A second caller with the identical pattern was found and needs the same
treatment: `generate_silver_dbt_models.py` (generates the 30 dbt silver
model `.sql` files) uses the exact same `duckdb.connect(":memory:")` +
`silver_store._DDL` + `information_schema` technique
(`_reflect_tables()`). No other caller introspects DuckDB schema anywhere
in the codebase (grepped for `duckdb_constraints()`/
`information_schema.columns` combined with `duckdb.connect` — these two
scripts are the only hits).

- **Both generators retire entirely; the schema they produce becomes
  hand-maintained going forward, no successor generator built.** Checked
  `infra/snowflake/sql/bootstrap/`: 13 of its 14 files are already
  hand-authored and committed directly — `11_silver_landing_schema.sql`
  (this generator's output) was the one exception, built as a convenience
  when DuckDB was still the write-time schema source of truth. Once
  `silver_store.py`/DuckDB retire per Ticket 01, there's no live source of
  truth left to introspect at all — not "the source moved," but "the
  reason this generator existed stops applying." Future schema changes
  (e.g. a new parsed column landing in Snowflake) become a direct hand-edit
  to the committed SQL/dbt files, matching how every other schema change in
  this repo already works, rather than adding new modeling machinery
  (SQLAlchemy or otherwise) whose only consumer would be a DDL-emission
  tool with no other benefit — these 30 tables are write-only Parquet
  targets with zero ORM query usage anywhere in the codebase.
- **Explicitly does not extend to the 12 bookkeeping tables' schema
  representation** — [Ticket 08](08-decide-operational-bookkeeping-storage-
  target.md) already independently decided those move to Snowflake native
  Postgres, reusing MDM's SQLAlchemy-modeled pattern (`mdm/database.py`).
  That's a different table set, a different target platform, and a
  genuine ORM-query use case (the bookkeeping store is read-then-upsert on
  a hot path) — SQLAlchemy earns its cost there in a way it wouldn't for
  the 30 write-only content tables. This ticket's answer and Ticket 08's
  are complementary, not overlapping.
- **`silver_store.py`'s `_DDL` string and both generator scripts
  (`generate_silver_landing_ddl.py`, `generate_silver_dbt_models.py`) get
  deleted** as part of the write-path cutover implementation, not kept as
  documentation — the committed SQL/dbt files they already produced remain
  as the durable, human-readable record; a stale generator nobody runs
  anymore is a liability (drifts silently, per this repo's own
  well-documented pattern of provisioning steps that weren't
  committed/re-runnable scripts biting it before — CLAUDE.md's "MDM
  Snowflake mirror schema lost on cutover" 5-whys), not a safety net.
