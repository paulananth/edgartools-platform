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
- `mark_entity_facts_refreshed` itself may already be mid-move via the crash-resume map's own
  Ticket 03 (open, blocked by its Ticket 02) — check that map's live status before assuming this
  map needs to design that one from scratch; the two efforts should converge on one answer for
  that specific marker, not compete.

## Decisions so far

- [Decide silver_store.py's DuckDB merge-engine fate](../duckdb-retirement-cutover/issues/20-decide-silver-store-merge-engine-fate.md) — reimplement on another engine (not keep DuckDB permanently), scoped as a real per-table migration project, not a single engine swap. Decided 2026-09-12.

## Not yet specified

- Which specific engine replaces DuckDB for the merge/dedup logic (Postgres, given the
  BookkeepingStore precedent, is the leading candidate — but per-task connection/round-trip
  cost against a remote Postgres instance for what's currently local in-process SQL hasn't been
  weighed against DuckDB's actual value-add here, and isn't yet a sharp enough question to
  ticket).
- Migration order across the ~4+ affected merge methods (`merge_financial_facts`,
  `merge_accounting_flags`, `merge_financial_derived`, `mark_entity_facts_refreshed`, plus the
  per-filing/thirteenf/company-identity equivalents) — which goes first, and what "done" means
  per table (equivalent regression coverage, live-verified against a real production write).
- Whether `merge_candidate_into_canonical`'s still-live caller in
  `application/silver_event_reducer.py:165` is folded into this same migration or stays an
  independent DuckDB consumer regardless of what happens to the bulk-merge engine (DuckDB
  Retirement Cutover Ticket 20's own open question, not yet resolved here).
- What "equivalent semantics" actually requires proving for each table — DuckDB's
  `QUALIFY ROW_NUMBER() OVER (...)` window-function dedup and `ON CONFLICT ... DO NOTHING`
  upsert behavior need a concrete correctness contract before any replacement can be judged
  against it, not just "looks similar."

## Out of scope

<!-- none yet -->
