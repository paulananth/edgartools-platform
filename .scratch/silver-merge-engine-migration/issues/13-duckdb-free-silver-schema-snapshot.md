# 13 — Commit a DuckDB-free silver schema snapshot

**Type:** task

**Status:** open

## Question

Every landing-only writer goes through `_record_landing_passthrough`, which gets its NOT NULL
set from `_required_columns` and its column order from `_table_columns` — both read DuckDB's
`information_schema` on the live local store. Nothing else in Ticket 09 can go until these have a
DuckDB-free source.

Validated 2026-09-14: a script that opens `SilverDatabase(":memory:")` and dumps
`{table: {columns: [...], required: [...]}}` from `information_schema` is deterministic and covers
`PROTECTED_TABLE_REGISTRY | EXCLUDED_OPERATIONAL_TABLES` exactly (45 tables, none without a
required column). A text parse of `_DDL` is **not** enough: the live schema is `_DDL` plus the
`_schema_migrations()` ALTERs (`retirement_state_observed_at`, `bronze_path`), and one PK clause
spans two lines. Generate from the live connection.

**Do:**
- Add `edgar_warehouse/silver_schema.py` (name TBD): the generated snapshot, scoped to the tables
  the passthrough writes (33) plus the three `_IN_RUN_LOOKUP_TABLES` (already among them). Check
  whether any of the other 12 (operational/bookkeeping) tables is still read through this path
  before including it; each included table is hand-maintained drift surface afterwards.
- Point `_required_columns` and `_table_columns` at it; keep DuckDB for everything else this slice.
- Test, while DuckDB still exists: the snapshot equals what a live `SilverDatabase(":memory:")`
  produces. Decide now what replaces that test in Ticket 17, when `_DDL` goes: the natural successor
  is parity against `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql` (33 CREATE
  TABLEs). This repo has lost a schema's generator twice already (the landing DDL, the MDM mirror);
  the successor test is the guard against a third.
- The snapshot's table list also takes over `PROTECTED_TABLE_REGISTRY`'s second job as the
  landing-scope list in `tests/unit/test_silver_landing_export.py`, so Ticket 15 does not strand it.

**Blocked by:** none — frontier.
