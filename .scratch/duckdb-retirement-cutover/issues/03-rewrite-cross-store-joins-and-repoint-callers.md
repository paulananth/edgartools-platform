# 03 — Rewrite Cross-Store Joins and Repoint Every Caller

**Split from the original Ticket 02 during implementation (2026-08-28)** —
see [Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md)'s own
split note for the full context. This ticket is the part the original
ticket's "repoint every reader/writer" line silently assumed would be
mechanical. It isn't, for 3 of the ~15 call sites.

**The real blocker, found while implementing: 3 call sites run a single
SQL statement joining a real SEC-content table against
`sec_company_sync_state` in one query.** Once that table lives in a
separate Postgres instance, none of these can execute as written — cross-
database SQL joins don't work that way.

1. `edgar_warehouse/mdm/coverage.py:51` —
   `SELECT COUNT(DISTINCT c.cik) FROM sec_company c JOIN
   sec_company_sync_state s ON s.cik = c.cik WHERE s.tracking_status =
   'active'`, run through `silver_reader.fetch(sql)`.
2. `edgar_warehouse/mdm/cli.py:1451` and `:1492` — two near-identical
   fallback queries: `sec_company_ticker t LEFT JOIN sec_company_sync_state
   s ON s.cik = t.cik`, run via `reader._conn.execute(query, params)`
   directly against a `ShardedSilverReader`.
3. `edgar_warehouse/mdm/pipeline.py:440` — `SELECT cik, tracking_status
   FROM sec_company_sync_state`, currently fetched separately via
   `self.silver.fetch(...)` and already joined against `sec_company` rows
   in Python (mirrors the existing `ticker_by_cik = _first_per_key(...)`
   pattern a few lines above it) — the closest thing to a template for how
   the other two sites should be rewritten.

**Important correction to how this was first read:** `pipeline.py`'s
existing `try`/`except` around this fetch, with its comment about
`MDM_SILVER_READ_TARGET=snowflake` degrading `tracking_by_cik` to empty, is
**not** a working solution to copy — it's a documented silent
correctness-loss path (every company resolves with `tracking = None`).
Confirmed this degrade path is not live in prod today:
`MDM_SILVER_READ_TARGET` defaults to `"duckdb"` (`mdm/cli.py:698`), and
flipping it to `snowflake` is explicitly gated behind a not-yet-passed
correctness gate elsewhere in that file. But this ticket's own change makes
the *same* failure mode live under the **default** `duckdb` target too,
not just the not-yet-flipped `snowflake` one — `sec_company_sync_state` is
leaving DuckDB's connection entirely, regardless of which target MDM reads
from. Do not preserve or extend the silent-`None`-degrade pattern for these
3 sites; replace it with a real two-step fetch (query the new bookkeeping
store separately, join in Python), which the existing `_first_per_key`
usage in `pipeline.py` already shows is the intended shape here.

**What to build:**

- Rewrite all 3 sites as: fetch the content-table rows from silver as
  today, separately fetch `tracking_status` (or whatever the join needs)
  from [Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md)'s
  new store, join the two result sets in Python (dict keyed by `cik`,
  matching the `_first_per_key` pattern already in `pipeline.py`).
- For `mdm/coverage.py`'s count query specifically: this needs a set
  intersection (distinct CIKs present in both `sec_company` and an
  "active" bookkeeping lookup) rather than a row-level join — implement as
  two count/fetch calls plus a Python set operation, not a fabricated SQL
  join string.
- Every other caller of the 11 tables (`silver_protection.py`,
  `mdm/silver_parity.py`, `silver_support/sharded_reader.py`,
  `application/warehouse_orchestrator.py`, `application/commands/
  verify_pipeline_run.py`, `application/commands/validate_data_quality.py`,
  `application/commands/migrate_silver_shards.py`,
  `infrastructure/dataset_path_catalog.py`, `infrastructure/silver_once.py`,
  `acquisition/discovery.py`, `application/workflows/
  drive_filing_discovery.py`, `scripts/build_relationship_release_manifest.py`
  — confirmed via grep, re-verify this list is still complete before
  starting) — repointed to call the new store's methods instead of
  `SilverDatabase`'s. Most of these call `SilverDatabase`'s public methods
  by name already (not raw SQL), so this should be close to mechanical
  given Ticket 02 gave the new store class matching method signatures;
  confirm each site actually is method-based before assuming it's
  mechanical, the way the 3 join sites above turned out not to be.
- `silver_protection.py`'s `PROTECTED_TABLE_REGISTRY`/
  `EXCLUDED_OPERATIONAL_TABLES` handling for these 11 tables needs
  re-checked: once they're not in `SilverDatabase`'s own DuckDB connection
  at all, does the merge-conflict machinery in that file still reference
  them meaningfully, or does their registry entry become dead code this
  ticket should remove? Decide by reading `silver_protection.py`'s actual
  usage, not by assumption.

**Blocked by:** [Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md)

**Status:** blocked

- [ ] All 3 cross-store join sites are rewritten to a two-step
      fetch-then-Python-join, with a test proving each produces the same
      result as the original single-SQL join against a fixture with real
      overlapping and non-overlapping CIKs
- [ ] The silent-`None`-degrade pattern in `mdm/pipeline.py` is removed for
      `sec_company_sync_state` specifically, replaced by a real fetch from
      the new store (confirm no other table's degrade path in this file is
      accidentally touched)
- [ ] Every remaining caller from the list above is repointed at the new
      store; grep confirms zero references to any of the 11 table names
      inside `edgar_warehouse/silver_store.py`'s own connection scope for
      these tables (the table names may still appear in the new store's
      own module, which is expected)
- [ ] `silver_protection.py`'s registry entries for these 11 tables are
      either confirmed still meaningful or removed as dead code, with the
      reasoning stated in the commit, not left ambiguous
- [ ] Full test suite green
