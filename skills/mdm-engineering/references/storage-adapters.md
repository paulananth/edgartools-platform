# Storage on each database engine

MDM has one engine: the mastering tables (`edgar_warehouse/mastering/`, `mastering/schema/<dialect>.sql`), which every
merge writes on PostgreSQL and MySQL, and the rules it runs by, registered in the Rules Database
(`edgar_warehouse/rules/registry.py`). `mdm init` installs the mastering tables and, on PostgreSQL, one init stamp
(`mdm.migration`, the checksum of `mdm/migrations/schema.sql`). Nothing else is installed, and a table nothing reads or
writes is deleted from init with its code.

## Resolve the selected target

Read the operator's engine and environment separately. An all-engines request has one target per engine, each keeping
its chosen engine. Resolve private connections through their configured environment variables and check the actual
connection dialect before applying DDL or running a load:

| Selected engine | SQLAlchemy dialect |
|---|---|
| PostgreSQL | `postgresql` |
| MySQL | `mysql` |
| SQL Server Express | `mssql` |

`edgar_warehouse.database_connections.connect` builds an engine for one URL; with a runtime role, PostgreSQL sets it,
and MySQL and SQL Server must have logged in as it. A working connection proves reachability; the full caller path
proves storage and merge support. Record a dialect refusal as the exact missing operation.

## Keep computation shared

The shared Rust and Python Merge Stage decides matching, identity, survivorship, classification and links once for
every engine. Storage differences carry its inputs and effects; they never interpret a second business policy. Write
standard SQL first, measure, and use an engine-only statement only where its cost demands it.

Keep integers and decimals exact, null distinct from empty, timestamps at the contract's precision, and canonical bytes
and hashes stable through write and read. Verify collation and ordering where they affect key equality. A driver default
is not evidence: select representations by measured parity, including numeric and temporal boundaries.

## Qualify each engine

Run the shared behaviour checks on real databases with restricted runtime roles for every affected kind and source
(`scripts/dev/adapter_test.sh`, the CI matrix): identity decisions, field winners, links and their history, waiting and
rejected outcomes, grants, concurrent writes, rollback, interrupted recovery and unchanged replay. A passing type or lock
check alone does not qualify an engine. Report each engine separately: init state, the rules registered, the proof's
scope, and any missing operation.

## GoF review

Before recommending a structural change, use `gof-refactor-reviewer` on the code and its history. Keep business
computation shared; an adapter layer is justified only when a concrete storage API must fit the Merge Stage contract,
never by its name.
