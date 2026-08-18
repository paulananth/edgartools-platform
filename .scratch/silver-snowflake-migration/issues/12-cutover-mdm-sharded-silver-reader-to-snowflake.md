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

- Replace every `ShardedSilverReader` read call site in MDM with a
  Snowflake query against the `EDGARTOOLS_SILVER` dbt schema, authenticated
  as `EDGARTOOLS_PROD_MDM_SILVER_READER` (provisioned, `FUTURE`-scoped,
  idle since Ticket 05). Known call sites as of Ticket 09's resolution —
  re-verify current line numbers before editing, this session's grep is a
  starting point, not a guarantee nothing has shifted:
  - `edgar_warehouse/mdm/cli.py` (four `ShardedSilverReader(...)`
    instantiations — the `_build_silver_reader`-style helper plus two
    standalone call sites)
  - Any caller of `_TABLES`-scoped reads inside `mdm run` (entity
    resolution) and `mdm-backfill-relationships` (relationship derivation)
- Confirm `EDGARTOOLS_PROD_MDM_SILVER_READER`'s actual grants cover every
  table MDM's resolution/relationship logic reads — `ShardedSilverReader`'s
  `_TABLES` allowlist (`edgar_warehouse/silver_support/sharded_reader.py`)
  is the authoritative list of what must be covered; diff it against the
  role's live grants rather than assuming Ticket 05's provisioning already
  matches (that ticket provisioned the role and `FUTURE` grants, but
  `EDGARTOOLS_SILVER`'s 31 dbt-managed tables didn't fully exist yet at
  provisioning time — verify live, don't assume).
- **Write path is out of scope for this ticket** — `silver_store.py` /
  `_publish_shard_if_remote` keep writing to DuckDB (still needed by
  `gold_models.py`, not yet migrated) and to Snowflake silver-landing
  (already live, Ticket 07). Nothing about this ticket touches writes.
- **`gold_models.py` is out of scope** — its own cutover is a separate
  future ticket, bound by Ticket 09's 2-week deadline (starts within 2
  weeks of this ticket being verified live in prod).

## Deliverable

MDM's entity resolution and relationship derivation read live from
Snowflake (`EDGARTOOLS_SILVER`) in prod, with `ShardedSilverReader` and its
`_TABLES` allowlist either deleted or left dead/unused (decide which during
implementation — deleting closes the exact "silent gap" failure shape that
caused the `INSTITUTIONAL_HOLDS`/`EMPLOYED_BY` incident in CLAUDE.md;
leaving it unused as a fallback trades that safety for a rollback path —
this is an implementation-time call, not pre-decided here). Verified
end-to-end against real prod data (a real `mdm run` / `mdm-backfill-
relationships` execution, row counts compared against the prior
DuckDB-backed run), not just unit-tested in isolation — matching this
map's own standing discipline (Notes: "every fix ships with real
measurements against real data/infra").

Starts the 2-week clock on `gold_models.py`'s own cutover ticket (Ticket
09's dual-write-window bound) once this is verified live.
