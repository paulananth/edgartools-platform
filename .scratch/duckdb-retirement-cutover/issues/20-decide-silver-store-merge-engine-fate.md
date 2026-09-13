# 20 — Decide `silver_store.py`'s DuckDB merge-engine fate

**What to build:** Ticket 12 (DuckDB Retirement Cleanup) discovered its own premise
doesn't hold: `SilverDatabase.merge_financial_facts`/`merge_accounting_flags`/
`merge_financial_derived`/`mark_entity_facts_refreshed` (and the equivalent methods for
`per-filing`/`thirteenf`/`company-identity` modes) are the **live** merge/dedup engine for
every `bootstrap-fundamentals` write, executing real DuckDB-specific SQL: temp staging
tables, `QUALIFY ROW_NUMBER() OVER (...)` window functions, `ON CONFLICT ... DO NOTHING`
upserts (`silver_store.py:3147` region, `_merge_rows_bulk`). Confirmed live and current,
not legacy: this is the exact code path that OOM-crashed 3 times in `daily-incremental-
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

**Status:** open

- [ ] Decide (a) reimplement on another engine, or (b) keep DuckDB permanently as the
      local merge buffer
- [ ] If (a): design + implement the replacement, with equivalent regression coverage to
      the existing merge tests (`test_silver_protection_scoped_merge.py`,
      `test_silver_financial_fact_retirement_provenance.py`,
      `test_silver_store_schema_migration.py`, etc. -- do not delete these to satisfy a
      "zero `import duckdb` in tests/" checklist item; they are the executable spec for
      this engine)
- [ ] If (b): update CLAUDE.md/this map to state plainly that DuckDB is a permanent,
      intentional part of the architecture (a local compute engine, not a legacy
      leftover), so "DuckDB retirement" as a destination is corrected rather than left
      permanently "in progress"
- [ ] `_read_fingerprint_sidecar`/`_write_fingerprint_sidecar`'s fate resolved alongside
      whichever path is chosen
