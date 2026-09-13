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
- `mark_entity_facts_refreshed`'s move (schema design + implementation) is absorbed into this
  map as Tickets 02/03, moved here from the crash-resume map's own Tickets 02/03 per Ticket
  01's scope-convergence decision — see that map's Decisions-so-far for the pointer back.
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
- [Choose the replacement engine and migration order](issues/01-choose-replacement-engine-and-migration-order.md) — REOPENED, pending user confirmation 2026-09-12. Original answer (Postgres; absorb the `mark_entity_facts_refreshed` marker here) reverted: the marker move belongs on the crash-resume map (already solved by the pipeline-resumability map's resume-ledger pattern), not here. The engine-choice question itself is now answered by evidence, not opinion: DuckDB Retirement Cutover's Ticket 10 (atomic write-path cutover, live 2026-09-12) already severed every code path — legacy and the newer, not-yet-scheduled Acquisition Ledger path alike — from ever reading back what the local merge computes; combined with dbt's `sec_financial_fact` model independently re-implementing the same dedup against raw landing rows, the local merge/dedup engine is confirmed dead compute everywhere, not just on one path. Recommendation on file: delete the local merge calls rather than port them to Postgres. Awaiting user sign-off before writing the final Answer (this is a `grilling`/HITL ticket).

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
- The entity-facts trio's own migration design (schema shape for 3 tables with real dedup
  logic, not just a marker) — not yet ticketed; graduates once Tickets 02/03 are resolved and
  the basic pattern is proven.
- Per-filing/thirteenf/company-identity modes' own merge-method specifics — not yet
  investigated at all; order was set in Ticket 01, but nobody has read these modes' actual
  merge code yet to know what each one requires.

## Out of scope

<!-- none yet -->
