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

**Status:** blocked

- [ ] Every `db.<method>()` call site in `warehouse_orchestrator.py`
      touching one of the 11 bookkeeping tables is repointed at
      `BookkeepingStore`, confirmed via grep that zero such calls remain
      against the file's local `SilverDatabase`/DuckDB connection for these
      11 tables
- [ ] `get_table_counts()` at line 665 produces a combined dict (DuckDB
      content-table counts + the bookkeeping store's 11 counts) with no
      silently-colliding same-named entries, and the
      `SilverDatabase.get_table_counts`-trimming decision above is made
      and stated, not left ambiguous
- [ ] `sharded_reader.py`'s `_TABLES` no longer lists the 7 bookkeeping
      table names it currently does, once confirmed nothing reads them via
      that path anymore
- [ ] Full test suite green
