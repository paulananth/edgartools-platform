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

## Decisions so far

- [Decide silver_store.py's DuckDB merge-engine fate](../duckdb-retirement-cutover/issues/20-decide-silver-store-merge-engine-fate.md) — reimplement on another engine (not keep DuckDB permanently), scoped as a real per-table migration project, not a single engine swap. Decided 2026-09-12.
- [Choose the replacement engine and migration order](issues/01-choose-replacement-engine-and-migration-order.md) — REOPENED 2026-09-13. Original answer (Postgres; absorb the `mark_entity_facts_refreshed` marker here) partly reverted: the marker move doesn't belong on this map at all (already solved by the pipeline-resumability map's resume-ledger pattern — sent back to the crash-resume map as a task, not a design question). Engine choice itself is now suspect: evidence found that dbt's `sec_financial_fact` silver model already independently re-implements the identical dedup logic against raw (undeduped) landing rows, meaning DuckDB's local merge may be dead compute rather than something to port. See the ticket's own correction for the one open question (does anything in-process read the local merged table?) that decides between "delete the merge" and "port it."

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
