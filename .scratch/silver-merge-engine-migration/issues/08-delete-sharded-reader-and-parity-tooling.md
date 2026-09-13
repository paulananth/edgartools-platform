# 08 — Delete `ShardedSilverReader` and `verify-resolver-input-parity`

**Type:** task

## Question

`silver_support/sharded_reader.py` survives only for `mdm verify-resolver-input-parity`
(`mdm/silver_parity.py`), which diffs DuckDB against Snowflake. Once no writer produces DuckDB
rows there is nothing to diff. Delete the reader, the parity command, and the `RESOLVER_INPUT_TABLES`
exclude-column machinery CLAUDE.md's "verify-resolver-input-parity 100% false-positive" entry
describes; `silver_support/session.py`'s `open_silver_shard` and `mdm/cli.py`'s six references
go with it.

**Blocked by:** [Ticket 05](05-thirteenf-tables-landing-only.md),
[Ticket 06](06-submissions-and-artifact-tables-landing-only.md).
