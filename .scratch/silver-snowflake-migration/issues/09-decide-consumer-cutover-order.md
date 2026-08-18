# Decide Consumer Cutover Order

Type: grilling
Status: open
Blocked by: none

## Question

Phase 2's working assumption (locked by the user when this map was
reopened) is a **phased**, consumer-by-consumer cutover — not a single flip
that retires DuckDB everywhere at once. The landing zone already dual-writes
live in prod (Ticket 07) and dbt silver models already exist (Ticket 01), so
the next real decision is: **which consumer moves off DuckDB first, and in
what order do the rest follow?**

There are three distinct DuckDB consumers, per
[Decide the Replacement Path for Direct Silver Consumers](03-decide-direct-silver-consumer-replacement.md)'s
already-settled retirement targets:

1. **MDM's `ShardedSilverReader`** (`edgar_warehouse/silver_support/sharded_reader.py`)
   — reads silver for entity resolution and relationship derivation.
   Ticket 03 already decided its replacement: Snowflake-native GRANTs on a
   dedicated reader role instead of the `_TABLES` allowlist (the exact
   mechanism whose gap caused the `INSTITUTIONAL_HOLDS`/`EMPLOYED_BY`
   incident in CLAUDE.md).
2. **`gold_models.py`'s ~20 Python gold builders** — read a DuckDB `conn`
   directly via raw SQL (confirmed live this session:
   `_build_dim_company(conn: Any)` etc. all take a DuckDB connection).
   Ticket 03 decided these retire in favor of dbt gold `ref()`-ing dbt
   silver directly.
3. **The write path** (`silver_store.py`, `silver_protection.py`,
   `_publish_shard_if_remote` in `warehouse_orchestrator.py`) — stops
   writing to `silver.duckdb`/S3 shards entirely once nothing reads them.
   This is necessarily last: it can only retire after both read-side
   consumers (1 and 2) have moved, otherwise there's nothing to read from.

So the real open question is narrower than "pick an order": **does MDM or
gold-building cut over first between them**, since the write path's
position (last) is already implied by the other two both depending on it.

Considerations for this session's grilling round:

- **Blast radius if wrong.** MDM entity resolution feeds gold (`IS_INSIDER`
  etc. are read during gold-refresh) — does an MDM-first cutover risk gold
  reading a half-migrated entity/relationship set, or are they decoupled
  enough (separate ECS tasks, separate DuckDB connections) that this isn't
  a real risk?
- **Which is smaller as a first slice.** MDM's `ShardedSilverReader` is a
  single, already-isolated chokepoint (one class, `_TABLES` allowlist) —
  narrower surface than "~20 Python gold builders," which suggests MDM
  might be the safer, smaller first migration slice per this map's Phase 2
  destination ("execution of the first real migration slice").
- **Dual-write duration.** Whichever consumer moves first, the write path
  keeps writing to *both* DuckDB (for the not-yet-migrated consumer) and
  Snowflake silver (already true today, Ticket 07) until the second
  consumer also cuts over — bound this window's cost/risk, not leave it
  open-ended.
- **Today's motivating evidence** (see map Notes): the DuckDB write path's
  sharded-publish race is real and recurring. Does that argue for
  prioritizing the *write path's* retirement sooner (even though it's
  structurally last), e.g. by accepting a temporary workaround for Stage
  14 (lower `MaxConcurrency`, add retry) as a bridge while this ticket's
  chosen read-side migration proceeds — or is that a separate, unrelated
  decision this ticket shouldn't fold in?

Use `/grilling` and `/domain-modeling` per this map's Notes. Resolve with a
concrete named order (e.g. "MDM first, then gold-building, then retire the
write path") and what the first slice concretely delivers, so it can
graduate into a real migration ticket per the map's "Not yet specified."
