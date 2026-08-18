# Cut Over MDM's ShardedSilverReader to Snowflake

Type: task
Status: open
Blocked by: none

## Question

[Decide Consumer Cutover Order](09-decide-consumer-cutover-order.md)
resolved: MDM's `ShardedSilverReader` moves off DuckDB first, as this
migration's first real slice. This ticket carries out that cutover — per
this map's Phase 2 mode override (Notes), resolving it means shipping the
migration, not just deciding it further.

**Scope:**

- Gate every `ShardedSilverReader` read call site in MDM behind a new
  `MDM_SILVER_READ_TARGET=duckdb|snowflake` env var (default `duckdb` until
  cutover is verified, then flipped via deploy — no image rebuild to
  revert). Per [Ticket 10](10-decide-cutover-rollback-mechanics.md)'s
  resolved mechanics: **do not delete `ShardedSilverReader`** as part of
  this ticket — it stays as the `duckdb` branch's implementation until
  gold-building's own later cutover retires the write path entirely; only
  then does deleting it become correct. Known call sites as of Ticket 09's
  resolution — re-verify current line numbers before editing, this
  session's grep is a starting point, not a guarantee nothing has shifted:
  - `edgar_warehouse/mdm/cli.py` (four `ShardedSilverReader(...)`
    instantiations — the `_build_silver_reader`-style helper plus two
    standalone call sites)
  - Any caller of `_TABLES`-scoped reads inside `mdm run` (entity
    resolution) and `mdm-backfill-relationships` (relationship derivation)
- The `snowflake` branch reads `EDGARTOOLS_SILVER` (dbt schema),
  authenticated as `EDGARTOOLS_PROD_MDM_SILVER_READER` (provisioned,
  `FUTURE`-scoped, idle since Ticket 05).
- Confirm `EDGARTOOLS_PROD_MDM_SILVER_READER`'s actual grants cover every
  table MDM's resolution/relationship logic reads — `ShardedSilverReader`'s
  `_TABLES` allowlist (`edgar_warehouse/silver_support/sharded_reader.py`)
  is the authoritative list of what must be covered; diff it against the
  role's live grants rather than assuming Ticket 05's provisioning already
  matches (that ticket provisioned the role and `FUTURE` grants, but
  `EDGARTOOLS_SILVER`'s 31 dbt-managed tables didn't fully exist yet at
  provisioning time — verify live, don't assume).
- Build a new `mdm verify-silver-parity`-style command (Ticket 10, item 2):
  runs MDM's entity resolution/relationship derivation against both
  sources for the same real CIK slice and diffs row counts per table plus
  resolved `entity_id` assignments (not just counts). Run it and confirm a
  clean parity result **before** flipping `MDM_SILVER_READ_TARGET` to
  `snowflake` in prod — this is the correctness gate the flip depends on,
  not an optional afterthought.
- New CloudWatch alarm (Ticket 10, item 3) on post-flip divergence —
  exact metric TBD at implementation time based on what
  `mdm verify-silver-parity` emits, mirroring ticket 81's alarm-coverage
  pattern (CLAUDE.md).
- **Write path is out of scope for this ticket** — `silver_store.py` /
  `_publish_shard_if_remote` keep writing to DuckDB (still needed by
  `gold_models.py`, not yet migrated) and to Snowflake silver-landing
  (already live, Ticket 07). Nothing about this ticket touches writes.
- **`gold_models.py` is out of scope** — its own cutover is a separate
  future ticket, bound by Ticket 09's 2-week deadline (starts within 2
  weeks of this ticket being verified live in prod).
- **No rollback-write-unwind logic needed** (Ticket 10, item 4) — a bad
  flip's downstream writes self-correct on the next resolution pass under
  this repo's existing idempotent-upsert posture. Don't build anything
  extra here on that account.

## Deliverable

MDM's entity resolution and relationship derivation read live from
Snowflake (`EDGARTOOLS_SILVER`) in prod via `MDM_SILVER_READ_TARGET=snowflake`,
gated on a clean `mdm verify-silver-parity` result, with the alarm live and
the `duckdb` branch (`ShardedSilverReader`, unmodified) kept in place as
the rollback path — flip the env var back, no redeploy, per Ticket 10.
Verified end-to-end against real prod data (a real `mdm run` /
`mdm-backfill-relationships` execution under the `snowflake` target, row
counts and entity_id assignments compared against the prior DuckDB-backed
run via the new parity command), not just unit-tested in isolation —
matching this map's own standing discipline (Notes: "every fix ships with
real measurements against real data/infra").

Starts the 2-week clock on `gold_models.py`'s own cutover ticket (Ticket
09's dual-write-window bound) once this is verified live.
