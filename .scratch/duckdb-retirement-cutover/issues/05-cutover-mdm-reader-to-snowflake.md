# 05 — Cut Over MDM's `ShardedSilverReader` to Snowflake

**What to build:** DuckDB Retirement's Ticket 02 decided this is a hard
cutover, no transition window: `ShardedSilverReader` (`edgar_warehouse/
silver_support/sharded_reader.py`) is replaced at all 6 call sites by a
Snowflake-backed implementation of the same minimal `SilverReader` Protocol
(`edgar_warehouse/mdm/resolvers/base.py:19`) — confirmed zero DuckDB-dialect
SQL in any MDM silver-read query, so this is a storage-target swap, not a
query rewrite.

Credential activation: reuse the existing shared `EDGARTOOLS_PROD_LOADER`
secret as a secondary role for MDM's reads, rather than provisioning a
dedicated reader role — the operator's explicit choice, knowingly
reintroducing some write-role read overlap (Ticket 02's answer).

"Resolution matches" for the new reader means Ticket 07's row-level digest
standard (wayfinder decision, not this ticket set's own Ticket 09 below) — same
match decision and confidence score per input row as the old DuckDB-backed
reader produced, not identical `entity_id` values (entity IDs are assigned
independently per resolver run and aren't expected to be byte-identical).

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] All 6 call sites of `ShardedSilverReader` now use the new
      Snowflake-backed `SilverReader` implementation
- [ ] MDM reads authenticate via `EDGARTOOLS_PROD_LOADER`'s secondary role
      (no new dedicated role provisioned)
- [ ] A parity test proves the new reader produces the same match
      decision + confidence score per input row as the old reader, on a
      real (not synthetic) sample of company/adviser/person/fund/security
      records
- [ ] `edgar_warehouse/silver_support/sharded_reader.py`'s DuckDB-backed
      implementation is either deleted or left dead pending
      [Ticket 12](12-duckdb-retirement-cleanup.md)'s final sweep — not
      silently kept as an unused parallel path
- [ ] Full MDM test suite green
