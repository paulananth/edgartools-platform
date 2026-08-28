# 05 — Retire the DuckDB-Backed DDL Generator Scripts

**What to build:** DuckDB Retirement's Ticket 06 corrected its own premise
first: `infra/scripts/generate_silver_landing_ddl.py` never introspected a
live DuckDB instance — it only ever used an ephemeral `:memory:` DuckDB
connection, seeded from the `silver_store._DDL` string, purely as a
SQL-parsing engine to emit Snowflake DDL. A second caller with the identical
pattern was found: `generate_silver_dbt_models.py`.

Delete both scripts entirely — no successor generator. 13 of the 14
Snowflake bootstrap SQL files in `infra/snowflake/sql/bootstrap/` are
already hand-maintained; these two generators were the one exception.
Future schema changes to the bookkeeping/landing tables become a direct
hand-edit, matching every other bootstrap SQL file in this repo.

This is distinct from Ticket 08's bookkeeping-table SQLAlchemy models
(different tables — the 11 tables moving to Snowflake Postgres — different
platform, and a genuine ORM use case there, unlike this ticket's
ephemeral-parser use case).

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `infra/scripts/generate_silver_landing_ddl.py` is deleted
- [ ] `infra/scripts/generate_silver_dbt_models.py` is deleted
- [ ] `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql` (the
      most recent output of the first script) is confirmed still correct
      and is now the hand-maintained source of truth going forward — no
      regeneration step referenced anywhere in docs/CLAUDE.md
- [ ] CLAUDE.md's references to running these generators are removed or
      corrected
- [ ] Grep confirms no other script or CI step invokes either deleted file
