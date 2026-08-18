# Decide Consumer Cutover Order

Type: grilling
Status: resolved
Blocked by: none
Claimed by Claude on 2026-08-18.

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

## Answer

**Order: MDM's `ShardedSilverReader` first, then `gold_models.py`'s Python
builders, then the write path retires.**

**Blast radius, resolved as fact before asking the user to weigh in on it**
(this was investigable, not a judgment call): checked `gold_models.py`
directly — none of its ~20 builders reference `mdm_entity_id`,
`IS_INSIDER`, `MANAGES_FUND`, or any other MDM-derived field. The file's
only `ShardedSilverReader` touchpoint is a duck-typing comment (line 1413)
noting it accepts either a `SilverDatabase` or a `ShardedSilverReader`
because both expose a `._conn` attribute — pure storage-layer
interchangeability, not a data dependency. Every builder reads raw
silver-parsed columns (`owner_cik`, `owner_name`, `adviser_name`, etc.) and
dedupes on natural keys it computes itself. **MDM and gold-building are
genuinely decoupled today** — an MDM-first cutover carries zero risk of
gold reading a half-migrated entity/relationship set, because gold never
reads MDM's entity resolution output at the Python-builder layer at all.

**Why MDM first, given they're decoupled (so risk didn't decide it —
surface area and existing runway did):**
- Smaller, already-isolated surface: one class (`ShardedSilverReader`,
  `_TABLES` allowlist) vs. ~20 independent Python builder functions.
- The replacement infrastructure already exists and is unused: Ticket 05
  provisioned `EDGARTOOLS_PROD_MDM_SILVER_READER` with `FUTURE`-scoped
  grants specifically for this cutover, live in prod, sitting idle. Using
  it is completing already-sunk setup, not starting fresh.
- Matches this map's Phase 2 destination framing of a "first slice" —
  MDM's read path is the narrower, cheaper slice to prove the cutover
  pattern on before touching the larger gold-builder surface.

**Dual-write window: bounded by an explicit calendar deadline, not left
open-ended.** Gold-building's cutover must **start within 2 weeks of
MDM's cutover being verified live in prod**. Chosen over an
event-triggered bound ("whenever gold_models.py next gets touched
anyway") because event triggers have no guaranteed occurrence and this
map's own standing preference (Notes) is for locked, non-open-ended
decisions — a calendar deadline is checkable without inventing a new
metric.

**Stage 14's write-path race: explicitly kept out of this ticket's
scope.** The write path is structurally last in this order regardless of
which read-side consumer goes first, so a bridge fix for its current
`shard-0.duckdb` ETag conflict (Task #166 / Task #159's blocker) is an
operational unblock decision, not an architecture-sequencing one. Handle
it as its own call (resume-only / lower `MaxConcurrency` / add
retry-on-conflict — the three options already on the table from earlier
this session), independent of this ticket's answer.

**First slice, concretely:** MDM's three consumers of `ShardedSilverReader`
(`mdm run`'s entity resolution, `mdm-backfill-relationships`'s relationship
derivation, and `mdm/cli.py`'s other three call sites at lines
574/1153/1196) switch their read queries from the local DuckDB
shard/monolith to Snowflake, authenticating as
`EDGARTOOLS_PROD_MDM_SILVER_READER` against the `EDGARTOOLS_SILVER` dbt
schema. The write path is unchanged — still dual-writing to DuckDB (for
gold-building, not yet migrated) and Snowflake silver-landing (Ticket 07,
already live). Graduates into [Ticket 12](12-cutover-mdm-sharded-silver-reader-to-snowflake.md).
