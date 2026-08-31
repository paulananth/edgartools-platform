# 14 — Repoint warehouse_orchestrator.py's Bookkeeping-Table Callers

**Split from the original Ticket 03 during implementation (2026-08-29)** —
see [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)'s own
split note for the full context. Isolated as its own ticket purely because
of size and review risk: `edgar_warehouse/application/
warehouse_orchestrator.py` alone has **50+ `db.<method>()` call sites**
against the 11 bookkeeping tables, spread across many independently-scoped
functions (each opens its own local `db = open_silver_shard(...)` /
`_open_silver_database(...)`), not one shared place — the original ticket's
"~15 call sites" estimate was really "~15 *files*"; this one file alone has
more individual call sites than that.

**What to build:**

- Every `db.<method>()` call in this file that targets one of the 11
  bookkeeping tables gets repointed at a `BookkeepingStore` instance,
  constructed via the `_bookkeeping_store()` convention
  [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md) settled,
  alongside the existing local `db = open_silver_shard(...)` /
  `_open_silver_database(...)` construction in each function that needs
  one. Most of these call `SilverDatabase`'s public methods by name already
  (not raw SQL) and Ticket 02 gave the new store class matching method
  signatures — spot-check each site's actual query shape against the
  target method before assuming a name match is a semantics match; a prior
  recon pass found the shapes line up but did not exhaustively verify
  every one of the 50+ sites.
- `get_table_counts` at `warehouse_orchestrator.py:665` (inside
  `_execute_warehouse_bronze_capture`, feeding `silver_table_counts` into
  the `bronze_silver_completed` diagnostic event): Ticket 02 built only a
  narrow, 11-table version of this method on the new store. The real
  method's original contract — one dict covering every silver table,
  bookkeeping and content mixed — needs rebuilding at this one call site:
  merge DuckDB's own (now content-table-only) counts with
  `bookkeeping.get_table_counts()`'s 11-table counts into one combined
  dict, preserving the original external contract this diagnostic event
  expects. **Resolve first, before writing this code**: does
  `SilverDatabase.get_table_counts` itself get trimmed to stop listing the
  11 bookkeeping table names in its `baseline_tables` set (so it always
  reports the DuckDB-side truth going forward), or does it keep listing
  them (always reporting 0 after cutover) with the merge silently
  overwriting those 0s with the bookkeeping store's real counts on
  key collision? Pick one and state which; don't leave two colliding
  same-named entries in the merged dict by accident. Re-check the
  `bronze_silver_completed` event schema/consumer expects a specific set
  of keys before finalizing the combined shape.
- `edgar_warehouse/silver_support/sharded_reader.py`'s `_TABLES` allowlist:
  7 of the 11 bookkeeping table names currently appear in this list
  (`discovery_checkpoint`, `pipeline_run_lease`, `pipeline_run`,
  `gold_manifest` are notably *not* in it at all already). Once nothing in
  this file's own read path queries the 7 present names via
  `ShardedSilverReader` anymore (confirm this is true after this ticket's
  repointing, not before), remove those 7 names from `_TABLES`.

**Note (2026-08-30, added while closing [Ticket 13](13-rewrite-cross-store-join-sites.md)):**
the `db.get_company_identity_ciks(...)` call site at
`warehouse_orchestrator.py`'s `"compute-identity-refresh-window"` branch
(~line 3091) is already fully repointed — Ticket 13 threaded a
`bookkeeping: BookkeepingStore` param through `get_company_identity_ciks`
itself and updated this call site to construct one via `_bookkeeping_store()`
and pass it in. Do not duplicate that work here. The sibling call one line
above it, `db.get_tracked_ciks("active")`, is untouched and still targets
`SilverDatabase`'s own DuckDB-backed method — that one, plus the other 50+
sites this ticket describes, remain this ticket's job.

**Blocked by:** [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)

**Status:** done except one explicitly-deferred item (2026-08-30)

- [x] Every `db.<method>()` call site in `warehouse_orchestrator.py`
      touching one of the 11 bookkeeping tables is repointed at
      `BookkeepingStore`, confirmed via grep that zero such calls remain
      against the file's local `SilverDatabase`/DuckDB connection for these
      11 tables. Implementation shape: `bookkeeping` mirrors `db`'s existing
      threading pattern exactly (added as a second parameter alongside `db`
      everywhere both are needed; swapped in outright, replacing `db`,
      wherever a function turned out to touch only bookkeeping tables --
      `_filter_ciks_to_universe`, `_seed_silver_tracking_status`,
      `_demote_deregistered_ciks`, `_read_bronze_if_cached`,
      `_resolve_submissions_main_checkpoint_only`/`_pagination_checkpoint_only`,
      `_capture_submission_bronze_snapshots`,
      `_resolve_submissions_main_cached_snapshot`/`_pagination_cached_snapshot`,
      `_capture_submissions_main`/`_capture_submissions_pagination`,
      `_capture_reconcile_snapshot`, `_load_daily_index_for_date`,
      `_capture_catch_up_daily_form_index`, `_resolve_bootstrap_target_ciks`,
      `_resolve_reconcile_ciks`). A `/gof-refactor-reviewer` consult before
      writing confirmed this mirrored-parameter approach over bundling
      `db`+`bookkeeping` into one context object -- real churn evidence
      exists for the threading pattern (13 historical commits touched
      `db: SilverDatabase` params), but bundling now would add migration
      risk to an already-fragile function for a ticket whose job is a
      mechanical repoint, not a restructure.
- [x] `get_table_counts()` at line 665 produces a combined dict (DuckDB
      content-table counts + the bookkeeping store's 11 counts) with no
      silently-colliding same-named entries, and the
      `SilverDatabase.get_table_counts`-trimming decision above is made
      and stated, not left ambiguous. Decision: `SilverDatabase.get_table_counts()`
      now explicitly excludes all `BOOKKEEPING_TABLES` names from both its
      `baseline_tables` set and the live `duckdb_tables()` result (not just
      the baseline set -- the physical tables still exist in DuckDB's own
      `_DDL`, so excluding only the baseline wouldn't have removed them from
      the live-table union). `_execute_warehouse_bronze_capture` merges
      `{**db.get_table_counts(), **bookkeeping.get_table_counts()}`. New
      regression test: `test_get_table_counts_excludes_bookkeeping_tables`
      (`tests/unit/test_silver_store_counts.py`), which inserts a row into
      `sec_company_sync_state` first to prove the exclusion is enforced
      explicitly, not just an artifact of the table being empty/absent.
- [ ] **Deferred, not done:** `sharded_reader.py`'s `_TABLES` still lists
      all 7 bookkeeping table names. Investigated: `edgar_warehouse/mdm/cli.py`
      still constructs `ShardedSilverReader` instances for reasons unrelated
      to this ticket (its own `_seed_mdm_from_silver` fallback, already fixed
      correctly in Ticket 13 to route `sec_company_sync_state` reads through
      `bookkeeping.get_all_company_sync_states()` instead of this class's
      UNION view) -- but a full audit of every `ShardedSilverReader` call
      path (including [Ticket 15](15-repoint-remaining-bookkeeping-callers.md)'s
      still-unfixed callers, which may route through this same class) is
      needed before it's safe to remove these 7 names, and that audit is
      outside this ticket's `warehouse_orchestrator.py` scope. Left as-is;
      whoever closes Ticket 15 should re-check this item once its callers
      are repointed too.
- [x] Full test suite green (confirmed via the full `uv run pytest` run this
      session; see commit for the exact pass count)

**Addendum (undisclosed-scope finding from the mandated Spec-axis code review,
2026-08-30):** repointing `_sync_reference_data`/`_run_submissions_bronze_then_silver`
in `warehouse_orchestrator.py` forced two files outside this ticket's stated
`warehouse_orchestrator.py` scope to change too, since both call those functions
directly: `edgar_warehouse/application/commands/bootstrap_fundamentals.py` (its
`execute()` now constructs its own `bookkeeping = _bookkeeping_store()` -- a
module-local copy, per the repo's established one-liner-per-module convention
also used by `mdm/cli.py`, not a cross-module import of
`warehouse_orchestrator`'s private one, which an earlier pass of this fix got
wrong and the GoF-axis review caught -- and threads it into both calls plus its
own `_resolve_fundamentals_ciks` helper, whose `db.get_tracked_ciks(...)` call
was an independent, not-forced bookkeeping-table read on the same file that
would have silently kept returning stale/frozen DuckDB data if left alone) and
`edgar_warehouse/application/workflows/silver_parse_pipeline.py` (a thin
`run_parse_pipeline` wrapper around `_run_parse_pipeline`, updated the same
way, though it currently has zero callers anywhere in the codebase). Neither
file was listed in this ticket's original scope statement or in
[Ticket 15](15-repoint-remaining-bookkeeping-callers.md)'s inventory -- noted
here after the fact so the record is accurate, not because the fix itself was
wrong.

**Also from code review:** three test files added their own local
`_bookkeeping_fixture()` copy instead of importing the new shared
`tests/support/bookkeeping_fixtures.py::bookkeeping_fixture()` this same
session built for exactly this purpose (`test_pipeline_tracking_state.py`,
`test_identity_refresh_window.py`, `test_sec_fetch_lease.py`), plus one inline
copy in `test_dual_path_capture_parity.py` -- all four collapsed to import the
shared helper instead, confirmed via re-running the affected files (117 passed).
