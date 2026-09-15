# 17 — Delete the engine, drop `duckdb`, rebuild the deps images

**Type:** task

**Status:** open

## Question

With Tickets 13–16 done: delete `silver_store.py`'s DuckDB engine, `_DDL` and
`_schema_migrations()`, `silver_protection.py` (`merge_candidate_into_canonical`, the registries),
`silver.py` (the shim), the file-backed `open_silver_database`, and the `SilverDatabase` alias; swap
Ticket 13's live-schema parity test for its decided successor; remove `duckdb>=1.0.0` from
`pyproject.toml` and `uv.lock`; rebuild both deps images and the warehouse/MDM images (CLAUDE.md's
"When to rebuild which image" table: a `uv.lock` change means both deps images); deploy; delete
the two `expire-retired-silver-*` lifecycle rules once the S3 objects are gone (cutover Ticket 21).
Resolves [Ticket 09](09-remove-duckdb-dependency.md), the destination.

**Blocked by:** [Ticket 13](13-duckdb-free-silver-schema-snapshot.md),
[Ticket 14](14-move-write-path-off-silver-database.md),
[Ticket 15](15-delete-dead-duckdb-readers-and-tools.md),
[Ticket 16](16-retire-remaining-local-store-couplings.md).
