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
- [Choose the replacement engine and migration order](issues/01-choose-replacement-engine-and-migration-order.md) — resolved 2026-09-13 (second grilling round, after two "confirmed dead compute" claims were each found incomplete — see the ticket's own history). `sec_financial_fact` (`merge_financial_facts`) has no confirmed in-process reader: delete its local DuckDB write, passthrough to `landing_export` unchanged (Ticket 02). `sec_accounting_flag`/`sec_financial_derived` are genuinely load-bearing in-process (`backfill_accounting_flags` reads the derived rows back and depends on the flag row's existence) — full DuckDB removal is required regardless (operator's explicit call), so these move to a new, dedicated Postgres-backed scratch store reusing the bookkeeping Postgres instance/connection, upserted by business key, never purged (Ticket 03). `mark_entity_facts_refreshed` stays off this map entirely. `per-filing`/`thirteenf` modes confirmed this session to NOT share the read-back shape — likely simple delete-and-passthrough like Ticket 02, to be individually confirmed per table.

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
- `retire_financial_facts_not_in_snapshot`/`retire_accounting_flags_not_in_snapshot`'s fate
  once Tickets 02/03 land (surfaced by Ticket 01's Final Answer, not yet ticketed) — these
  Ticket-33 retirement writes operate on exactly the tables Tickets 02/03 move off local
  DuckDB; their only caller is dormant/unscheduled today, which may lower urgency but doesn't
  settle the question.

## Out of scope

<!-- none yet -->
