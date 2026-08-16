# Decide the Local Dev/Test Replacement Strategy

Type: grilling
Status: open

## Question

Per this map's charting decision ("everywhere — DuckDB leaves the codebase
entirely"), the test suite's current fixture strategy goes away too: a
large number of unit tests build real `SilverDatabase`-backed DuckDB
instances directly (e.g. `tests/unit/test_bronze_recovery_no_db_row.py`,
`test_gold_models_streaming.py`, `test_sharding.py`, and — per this
session's own precedent in CLAUDE.md's "INSTITUTIONAL_HOLDS/EMPLOYED_BY"
5-whys — a hand-rolled stub was explicitly rejected in favor of "a real
`SilverDatabase`-backed DuckDB file" for exactly this kind of schema-
sensitive test). Removing DuckDB removes the cheap, fast, in-process
database those tests rely on.

Options to weigh (not exhaustive — this is a grilling ticket, not a
pre-decided menu): a real Snowflake test schema/account reachable from
CI (cost, credential provisioning, network dependency, speed); a different
local-first SQL engine as a stand-in (e.g. SQLite/Postgres-in-Docker) that
isn't literally DuckDB but still isn't Snowflake, and whether that
satisfies "DuckDB leaves the codebase" or just relocates the same
tradeoff; mocking/stubbing at a level where schema drift can't hide (the
same "hand-rolled stub drifted from real schema" failure mode CLAUDE.md
already documents as a real incident, cutting against a naive mock-based
answer). Also decide: does this apply uniformly to every current DuckDB-
backed test, or do some categories (e.g. tests specifically characterizing
DuckDB-specific behavior that's being deleted anyway) simply get deleted
rather than ported?

First step before deciding: grep `tests/` for `SilverDatabase(`,
`duckdb.connect(`, and `.duckdb` fixture paths to get a real inventory
count — don't estimate blast radius, measure it.

## Deliverable

A decided replacement fixture strategy, plus an inventory of how many
existing tests it affects and whether any category gets deleted instead of
ported.
