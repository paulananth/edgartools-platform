# Silver Retirement & Landing-Zone Data Integrity

Label: `wayfinder:map`

## Destination

A decision-complete plan for closing every known data-integrity gap in the
Ticket-33 (validity-interval retirement) columns' path from local DuckDB
capture through canonical silver publish to the Snowflake landing-zone/gold
collapse. Done when both open questions below have a locked resolution
(decided, or implemented) and no known-but-unticketed gap remains anywhere
in that path.

Two mechanical bugs in this path were found and fixed the same day this map
was charted (see Decisions so far) while verifying the change-propagation
map's Ticket 46 in prod. A third, genuine design decision (how a retirement
conflict should resolve during silver publish) and a fourth, pre-existing,
independently-discovered bug (a thin backfill write nulling out unrelated
columns downstream) remain open — this map exists to hold both to a real
resolution instead of leaving them as loose findings.

## Notes

- Domain: `edgar_warehouse/silver_store.py` (retirement writes, schema
  migrations), `edgar_warehouse/silver_protection.py` (canonical merge /
  same-key conflict resolution), `infra/snowflake/dbt/edgartools_gold/
  models/silver/` + `edgar_warehouse/serving/silver_landing_export.py`
  (Snowflake landing-zone append + dbt collapse).
- **Related, deliberately not duplicated here:**
  - The **silver-snowflake-migration** map (`.scratch/silver-snowflake-migration/`)
    explicitly names `silver_protection.py` as its own domain and plans to
    eventually retire this exact DuckDB merge machinery. Whoever resolves
    this map's Ticket 03 (retirement conflict-resolution policy) should
    make sure that decision is portable to (or explicitly reconsidered
    for) a future Snowflake-native silver layer — don't let policy logic
    get stranded in code that's slated for retirement without a note.
  - The **silver-sharded-writes** map (`.scratch/silver-sharded-writes/`)
    explicitly excludes `daily_incremental`/`bootstrap` from its own
    scope ("structurally cross-shard per run, needing genuinely new
    multi-shard-write engineering that doesn't exist anywhere in this
    codebase") — confirms no overlap with the change-propagation map's
    Ticket 46, the work that surfaced this map.
- Use `/grilling` + `/domain-modeling` for Tickets 03 and 04 — both are
  genuine policy decisions with real tradeoffs, not mechanical fixes.

## Decisions so far

- [01 — Fix migration 010's DuckDB commit-conflict crash](issues/01-fix-migration-010-duckdb-commit-conflict.md) — `ALTER TABLE ADD COLUMN ... DEFAULT <expr>` against a non-empty table, followed by a second `ALTER TABLE` on the same table inside one explicit transaction, trips a DuckDB 1.5.2 commit-time conflict check. Migration 010 now opts out of the shared transactional envelope (idempotent `ADD COLUMN IF NOT EXISTS` statements don't need it); `_backup_and_recreate_table`-based migrations left untouched, since they genuinely do. PR [#482](https://github.com/paulananth/edgartools-platform/pull/482), merged.
- [02 — Fix sec_financial_fact's first-publish false conflict](issues/02-fix-first-publish-false-conflict.md) — canonical learning about `valid_from`/`valid_to`/`is_current` for the first time backfilled them `NULL` instead of matching the candidate's own migration-backfilled defaults, false-conflicting on all 434,805 pre-existing rows. Fixed for `is_current` (reuse the candidate's own declared `DEFAULT`) and `valid_from` (added to `provenance_columns` — `DEFAULT NOW()` can never match across two independent evaluations, and it's write-once by design anyway). Deliberately left `valid_to`/`is_current` real conflict detection untouched — that's Ticket 03's job. PR [#483](https://github.com/paulananth/edgartools-platform/pull/483), merged.

## Not yet specified

- The exact canary/verification step for whichever retirement-conflict
  policy Ticket 03 lands on — depends on what the policy actually is.

## Out of scope

- Migrating `silver_protection.py`'s merge logic to a Snowflake-native
  implementation — that's the silver-snowflake-migration map's job.
- Any change to `daily_incremental`/`bootstrap`'s write architecture
  (sharding, concurrency) — that's the silver-sharded-writes map's job.
