# 20 — Decide `silver_store.py`'s DuckDB merge-engine fate

**Resolved (2026-09-12): reimplement, table-by-table, expand/migrate/contract.** See
"Decision" section below for the full record. This ticket's remaining scope is now the
grilling/design ticket for the replacement engine choice and schema shape — tracked as a
new wayfinder map, [silver-merge-engine-migration](../../silver-merge-engine-migration/map.md).

**What to build (ORIGINAL, superseded by the Decision below):** Ticket 12 (DuckDB
Retirement Cleanup) discovered its own premise doesn't hold: `SilverDatabase.
merge_financial_facts`/`merge_accounting_flags`/`merge_financial_derived`/
`mark_entity_facts_refreshed` (and the equivalent methods for `per-filing`/`thirteenf`/
`company-identity` modes) are the **live** merge/dedup engine for every
`bootstrap-fundamentals` write, executing real DuckDB-specific SQL: temp staging tables,
`QUALIFY ROW_NUMBER() OVER (...)` window functions, `ON CONFLICT ... DO NOTHING` upserts
(`silver_store.py:3147` region, `_merge_rows_bulk`). Confirmed live and current, not
legacy: this is the exact code path that OOM-crashed 3 times in `daily-incremental-
retry-1789236915` (2026-09-12) — see the Bootstrap-Fundamentals Crash-Resume map.

This ticket decides what happens to that engine, since deleting it (as Ticket 12
originally assumed) is not simply cleanup -- it requires either:

- (a) a real reimplementation of the merge/dedup logic on a different SQL engine (SQLite,
  Postgres, in-process Python) with equivalent QUALIFY/window-function/upsert semantics,
  or
- (b) a decision that DuckDB stays permanently as the local, per-task write/merge buffer
  (not the distributed canonical store -- that role is already retired per Ticket 10),
  since it is genuinely doing useful work (in-process SQL merge logic) that has no
  currently-designed replacement.

Also decide the fate of `merge_candidate_into_canonical`'s still-live caller in
`application/silver_event_reducer.py:165` -- does it get folded into whatever this ticket
decides, or does it stay as its own independent DuckDB consumer regardless of what
happens to `silver_store.py`'s bulk-merge engine?

Secondary, smaller finding from Ticket 12's implementation: `_read_fingerprint_sidecar`
(`warehouse_orchestrator.py`) now has zero callers -- its only two readers were inside
`_publish_shard_if_remote` (deleted, Ticket 12) and `_publish_silver_database_if_remote`
(already a no-op since Ticket 10). `_write_fingerprint_sidecar` still writes these
sidecars from `_hydrate_silver_database_from_storage`/`_hydrate_shard_for_window`, but
nothing reads them anymore. Low priority (harmless dead write, not a bug), but worth
folding into whatever this ticket's cleanup pass does.

**Blocked by:** none -- independent design decision, but affects the scope of any
eventual `duckdb` removal from `pyproject.toml`/`uv.lock` (Ticket 12's last checklist
item, deliberately not attempted until this is resolved).

**Status:** resolved (2026-09-12) — decision made; implementation split into a new map

## Decision (2026-09-12)

Before deciding (a) vs (b), re-verified whether DuckDB's merge output is actually
consumed by anything, since a lot had landed since this ticket was written (Tickets
14/17/18). Confirmed live: `bootstrap_fundamentals.py` wires a `LandingExportBuffer`
(Ticket 18, deployed, live-verified via a real S3 Parquet write for CIK 908311) that
mirrors every `merge_*`/`upsert_*`/`mark_*` write into the Snowflake landing zone in the
same process, before the task exits. So DuckDB's merge/dedup output is genuinely
load-bearing today, not orphaned — this is a real architectural fork, not cleanup.

Presented (a)/(b)/defer to the user; answer: **(a), scoped as a real migration
project** — reimplement the merge/dedup logic on another engine (most likely Postgres,
given the BookkeepingStore precedent), one merge method (table) at a time, following the
expand/migrate/contract pattern already approved for the `mark_entity_facts_refreshed`
crash-resume marker move (bootstrap-fundamentals-crash-resume map). Not a single big-bang
engine swap.

Implementation of this decision is tracked as its own map:
[silver-merge-engine-migration](../../silver-merge-engine-migration/map.md) — that map
owns the engine choice, per-table migration order, and schema/transaction design; this
ticket's job (deciding the fate) is done.

**Small, low-risk item folded in and shipped in this same pass:**
`_read_fingerprint_sidecar`/`_write_fingerprint_sidecar`/`_protected_fingerprint_sidecar_path`
(`warehouse_orchestrator.py`) deleted outright — confirmed zero live callers
(`_read_fingerprint_sidecar` had none at all; `_write_fingerprint_sidecar`'s two call
sites became pure dead writes once `_publish_silver_database_if_remote` became a
permanent no-op and `_publish_shard_if_remote` was deleted). `compute_silver_fingerprint`
itself untouched — it has its own separate, live role in
`PUBLICATION_SIGNIFICANT_OPERATIONAL_TABLES` fingerprinting. `/gof-refactor-reviewer`
consulted first (git history: only 2 touches ever, both additions — no repeated-change
evidence, straightforward dead-code deletion). Full suite green: 3435 passed, 5 skipped,
8 pre-existing unrelated Postgres-integration failures (documented throughout CLAUDE.md).

- [x] Decide (a) reimplement on another engine, or (b) keep DuckDB permanently as the
      local merge buffer — decided (a), scoped as a real migration project
- [ ] If (a): design + implement the replacement, with equivalent regression coverage to
      the existing merge tests (`test_silver_protection_scoped_merge.py`,
      `test_silver_financial_fact_retirement_provenance.py`,
      `test_silver_store_schema_migration.py`, etc. -- do not delete these to satisfy a
      "zero `import duckdb` in tests/" checklist item; they are the executable spec for
      this engine) — moved to the silver-merge-engine-migration map
- [x] `_read_fingerprint_sidecar`/`_write_fingerprint_sidecar`'s fate resolved: deleted,
      confirmed zero live callers
