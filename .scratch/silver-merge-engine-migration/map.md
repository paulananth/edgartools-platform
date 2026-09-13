# Silver Merge-Engine Migration

## Destination

`silver_store.py`'s DuckDB-specific merge/dedup engine (`SilverDatabase.merge_financial_facts`/
`merge_accounting_flags`/`merge_financial_derived`/`mark_entity_facts_refreshed`, and the
equivalent methods for `per-filing`/`thirteenf`/`company-identity` modes — temp staging tables,
`QUALIFY ROW_NUMBER() OVER (...)` window functions, `ON CONFLICT ... DO NOTHING` upserts) is
reimplemented on a non-DuckDB engine, table by table, until no production write path depends on
DuckDB for merge/dedup compute. Reaching the destination means `duckdb` can finally come out of
`pyproject.toml`/`uv.lock` (DuckDB Retirement Cutover Ticket 20's last deferred checklist item),
and "DuckDB retirement" as an effort is actually complete rather than permanently "in progress."

## Notes

This effort **carries execution into the map**, per wayfinder's override — the destination
is a code migration (per-table, expand/migrate/contract), not a design document to hand off,
so tickets past the engine/order decision (Ticket 01) are build slices, not open decisions,
except where a table's specifics genuinely need a fresh design pass.

- Parent decision: [DuckDB Retirement Cutover Ticket 20](../duckdb-retirement-cutover/issues/20-decide-silver-store-merge-engine-fate.md)
  — confirmed live (via `bootstrap_fundamentals.py`'s `LandingExportBuffer`, Ticket 18) that the
  DuckDB merge engine's output is genuinely load-bearing, not orphaned. Decided: reimplement,
  not keep permanently — but as a real migration project, not a single big-bang engine swap.
- Explicit precedent to follow, not reinvent: the bootstrap-fundamentals-crash-resume map's
  `mark_entity_facts_refreshed` → BookkeepingStore/Postgres move — expand (new mechanism lands
  alongside the old), migrate (callers switch table by table), contract (old DuckDB path
  removed once nothing depends on it). This map generalizes that same pattern from one marker
  to the full merge/dedup engine.
- Consult `/gof-refactor-reviewer` before any production-code edit (CLAUDE.md hard rule).
- Run the full 3-axis `/code-review` (Standards/Spec/GoF) before any PR is ready (CLAUDE.md
  hard rule).
- `mark_entity_facts_refreshed` stays on the bootstrap-fundamentals-crash-resume map — the
  scope-convergence idea noted here previously was tried and reverted the same day (see
  Ticket 01's own CORRECTION section); this map's own Tickets 02/03 are unrelated new
  tickets (the merge-engine build slices), not the marker.
- **Overlap discovered 2026-09-12: this map's destination question was largely already
  decided at a higher level.** The `duckdb-retirement` wayfinder map (`.scratch/duckdb-
  retirement/`, decision-only, resolved/handed off 2026-08-28) already decided the write
  path retires to "Snowflake landing zone only" — no replacement local merge engine of any
  kind — and its implementation arm, `duckdb-retirement-cutover`, already shipped that
  cutover live (Ticket 10, 2026-09-12). This map (spawned from `duckdb-retirement-cutover`'s
  own Ticket 20) was chartered without checking whether its parent map had already settled
  the question one level up. If Ticket 01's "delete, don't port" recommendation is confirmed,
  this map's remaining scope shrinks to cleanup (deleting now-dead merge calls table by
  table) rather than a genuine engine migration — worth revisiting whether this map should
  keep existing separately or fold into `duckdb-retirement-cutover`'s own remaining tickets.

## Decisions so far

- [Decide silver_store.py's DuckDB merge-engine fate](../duckdb-retirement-cutover/issues/20-decide-silver-store-merge-engine-fate.md) — reimplement on another engine (not keep DuckDB permanently), scoped as a real per-table migration project, not a single engine swap. Decided 2026-09-12.
- [Choose the replacement engine and migration order](issues/01-choose-replacement-engine-and-migration-order.md) — resolved 2026-09-13 after three rounds (two "confirmed dead compute" claims and one Postgres-scratch-store answer were each found wrong before code was written — see the ticket's own history). Final shape: the whole entity-facts trio (`sec_financial_fact`, `sec_financial_derived`, `sec_accounting_flag`) is delete-and-passthrough to `landing_export`; the one in-process reader (`backfill_accounting_flags`) only ever re-read data the same per-CIK loop iteration had just produced from a full-history companyfacts payload, so its scoring moved in-memory instead of onto a store. No Postgres scratch store, no new Snowflake table. `mark_entity_facts_refreshed` stays off this map. `per-filing`/`thirteenf` confirmed to NOT share a read-back shape — delete-and-passthrough each, to be confirmed per table.
- [Delete `merge_financial_facts`'s local DuckDB write](issues/02-delete-merge-financial-facts-local-write.md) — resolved 2026-09-13. Landing-only via a shared `_record_landing_passthrough`; NOT NULL enforced by raising; `ingested_at` + validity trio stamped per write; acceptance read-back deleted (VERIFIED on record); DuckDB DDL kept.
- [Score accounting flags in memory; flags/derived landing-only](issues/03-postgres-scratch-store-for-derived-and-flags.md) — resolved 2026-09-13. Pure `score_accounting_flags` inside `run_bootstrap_entity_facts`'s per-CIK loop replaces `backfill_accounting_flags`/`update_accounting_flag_scores`; `retire_*_not_in_snapshot` deleted. Not yet live-verified.

## Not yet specified

- Whether `merge_candidate_into_canonical`'s still-live caller in
  `application/silver_event_reducer.py:165` is folded into this same migration or stays an
  independent DuckDB consumer regardless of what happens to the bulk-merge engine (DuckDB
  Retirement Cutover Ticket 20's own open question, not yet resolved here).
- What "equivalent semantics" actually requires proving for each table — DuckDB's
  `QUALIFY ROW_NUMBER() OVER (...)` window-function dedup and `ON CONFLICT ... DO NOTHING`
  upsert behavior need a concrete correctness contract before any replacement can be judged
  against it, not just "looks similar." Will likely graduate into its own design ticket once
  Tickets 02/03 (the marker move) prove out the basic Postgres-merge pattern.
- Per-filing/thirteenf modes' own merge-method specifics — confirmed 2026-09-13 that neither
  shares the entity-facts trio's in-process read-back shape (both only ever write via
  `db.merge_*`, nothing reads it back within the same run) — likely a delete-and-passthrough
  ticket each, same shape as Ticket 02, but not yet ticketed pending Tickets 02/03 landing
  first per Ticket 01's migration order.
- `company-identity` mode's own merge-method specifics — not yet investigated at all.
- Company-facts retirement against Snowflake silver: `retire_financial_facts_not_in_snapshot`/
  `retire_accounting_flags_not_in_snapshot` were deleted with Tickets 02/03 (they could only
  find rows in local DuckDB, and their sole caller never reached Snowflake anyway). The Ticket
  35 Silver Landing Retirement Record mechanism (`silver_landing_retirement` + the
  `silver_not_retired` dbt macro, already live for the reference catalog) is the natural
  home, but it needs the prior snapshot's membership read from Snowflake silver — not
  specified. Same fog covers wiring `drive_company_facts_discovery.py` to a landing export at
  all (it has none today, so its writes go nowhere).
- Live verification of Tickets 02/03: a prod entity-facts run after deploy showing
  `SEC_FINANCIAL_FACT`/`SEC_FINANCIAL_DERIVED`/`SEC_ACCOUNTING_FLAG` landing rows (scores
  populated) — the "done" bar both tickets still owe.

## Out of scope

<!-- none yet -->
