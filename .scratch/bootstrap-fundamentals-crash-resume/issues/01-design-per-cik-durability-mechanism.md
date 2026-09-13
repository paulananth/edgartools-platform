# 01 — Where should the per-CIK durability marker live?

**Type:** grilling

**Status:** resolved

## Question

`bootstrap-fundamentals`'s `entity-facts` mode already writes a per-CIK
completion marker (`db.mark_entity_facts_refreshed(int(cik))`,
`fundamentals_ingest.py:531`), deliberately as the last statement for that
CIK so a crash mid-CIK never falsely marks it done. But it writes into the
task's local, ephemeral `SilverDatabase` (DuckDB) file, which is only
uploaded to durable storage once, after the entire CIK window's loop
finishes (`bootstrap_fundamentals.py:409`, `_publish_silver_database_if_remote`).
A mid-window crash (observed live 2026-09-12: 3 consecutive OOM kills on
`bootstrap-fundamentals --mode entity-facts`) loses every already-processed
CIK's marker, so a retry re-fetches the whole window from SEC again.

Two candidate fixes:
(a) periodically re-upload the local SilverDatabase file every N CIKs, or
(b) move the per-CIK marker into `BookkeepingStore`/Postgres, decoupling
"fetched+parsed this CIK" from "uploaded silver.duckdb yet."

Which should this effort build on?

## Blocked by:

None — can start immediately.

## Answer

**(b) — move the marker into `BookkeepingStore`/Postgres.** Decided
2026-09-12. Postgres commits are cheap per-row; re-uploading the whole
local SilverDatabase file every N CIKs would scale cost with file size x
flush count, and fights the post-DuckDB-retirement direction where
Postgres bookkeeping is already the durable source of truth for tracking
state (see DuckDB Retirement Cutover Ticket 14's repointing of
`sec_company_sync_state` and friends onto `BookkeepingStore`). This does
not replace `mark_entity_facts_refreshed`'s local DuckDB write outright —
[Ticket 02](02-design-bookkeeping-schema-and-retry-contract.md) resolves
exactly how the two coexist.
